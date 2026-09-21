 
import { useEffect, useRef } from 'react';

interface WcClip {
  clipId: string;
  webcompId:  string;
  startFrame: number;
  duration: number;
  width: number;
  height: number;
  fps: number;
  htmlUrl: string;
}

function base(): string {
  return `http://127.0.0.1:${(window as any).__FADE_PORT__ ?? 8000}`;
}

 
const PREFETCH_AHEAD = 6;
const PREWARM_AHEAD = 90;   
const PREWARM_FRAMES = 12;
const PARAMS_SETTLE_MS = 300;
const TICK_SLEEP_MS    = 30;

function sleep(ms: number) {
  return new Promise<void>(r => setTimeout(r, ms));
}

export function useWebCompSync() {
  const api = (window as any).electronAPI;

  const knownIdsRef = useRef<Set<string>>(new Set());
  const wcClipsRef = useRef<WcClip[]>([]);
  const curFrameRef = useRef<number>(0);

  
  const pushedRef = useRef<Map<string, Set<number>>>(new Map());
  const pendingRef = useRef<Map<string, Set<number>>>(new Map());
  const generationRef = useRef<number>(0);
  const settleUntilRef = useRef<number>(0);

 
  useEffect(() => {
    const onFrame = (e: Event) => {
      const newFrame = (e as CustomEvent).detail ?? 0;
      const oldFrame = curFrameRef.current;
      curFrameRef.current = newFrame;

      // Detect seek/loop 
      const delta = newFrame - oldFrame;
      if (delta < 0 || delta > PREFETCH_AHEAD + 2) {
        // Playhead jumped  
        for (const set of pushedRef.current.values()) set.clear();
        for (const set of pendingRef.current.values()) set.clear();

         
        if (api?.webcompPushToNative) {
          for (const clip of wcClipsRef.current) {
            const srcFrame = newFrame - clip.startFrame;
            if (srcFrame < 0 || srcFrame >= clip.duration) continue;
            const pushed  = pushedRef.current.get(clip.webcompId);
            const pending = pendingRef.current.get(clip.webcompId);
            if (!pushed || !pending) continue;
            if (pushed.has(srcFrame) || pending.has(srcFrame)) continue;
            pending.add(srcFrame);
            const capSrc = srcFrame;
            api.webcompPushToNative(clip.webcompId, capSrc, clip.width, clip.height)
              .then((ok: boolean) => {
                pending.delete(capSrc);
                if (ok) pushed.add(capSrc);
              })
              .catch(() => { pending.delete(capSrc); });
          }
        }
      }
    };
    window.addEventListener('fade:frame', onFrame);
    window.addEventListener('fade:seek',  onFrame);
    return () => {
      window.removeEventListener('fade:frame', onFrame);
      window.removeEventListener('fade:seek',  onFrame);
    };
  }, []);

  /*   On seek/stop */
  useEffect(() => {
    const onReset = () => {
      for (const set of pushedRef.current.values()) set.clear();
    
    };
    window.addEventListener('fade:seek',  onReset);
    window.addEventListener('fade:stop',  onReset);
    window.addEventListener('fade:reset', onReset);
    return () => {
      window.removeEventListener('fade:seek',  onReset);
      window.removeEventListener('fade:stop',  onReset);
      window.removeEventListener('fade:reset', onReset);
    };
  }, []);

  /* Params change */
  useEffect(() => {
    const onParamsChange = (e: Event) => {
      const { webcompId } = (e as CustomEvent<{ webcompId: string }>).detail ?? {};
      generationRef.current++;
      settleUntilRef.current = Date.now() + PARAMS_SETTLE_MS;

      // Clear pushed cache  
      if (webcompId) {
        pushedRef.current.get(webcompId)?.clear();
        pendingRef.current.get(webcompId)?.clear();
      } else {
        // Params change without a specific ID — clear all
        for (const s of pushedRef.current.values())  s.clear();
        for (const s of pendingRef.current.values()) s.clear();
      }

      console.log(`[WebCompSync] params changed (gen=${generationRef.current}), settle ${PARAMS_SETTLE_MS}ms`);
    };
    window.addEventListener('fade:webcomp-params-changed', onParamsChange);
    return () => window.removeEventListener('fade:webcomp-params-changed', onParamsChange);
  }, []);

 
  const perClipLoopsRef = useRef<Map<string, AbortController>>(new Map());

  const spawnLoopForClip = (webcompId: string) => {
    if (!api?.webcompPushToNative) return;
    if (perClipLoopsRef.current.has(webcompId)) return; // already running

    const ctrl = new AbortController();
    perClipLoopsRef.current.set(webcompId, ctrl);

    const loop = async () => {
      while (!ctrl.signal.aborted) {
        await sleep(TICK_SLEEP_MS);
        if (ctrl.signal.aborted) break;

        // Respect params-change settle window
        if (Date.now() < settleUntilRef.current) continue;

       
        const clips = wcClipsRef.current.filter(c => c.webcompId === webcompId);
        if (clips.length === 0) { await sleep(200); continue; }

        const pushed  = pushedRef.current.get(webcompId);
        const pending = pendingRef.current.get(webcompId);
        if (!pushed || !pending) continue;

        const cur = curFrameRef.current;
        const myGen  = generationRef.current;

 
        for (const clip of clips) {
 
          for (let delta = 0; delta <= PREFETCH_AHEAD; delta++) {
            if (ctrl.signal.aborted) break;
            if (Date.now() < settleUntilRef.current) break;

            const absFrame = cur + delta;
            const srcFrame = absFrame - clip.startFrame;
            if (srcFrame < 0 || srcFrame >= clip.duration) continue;

            if (pushed.has(srcFrame) || pending.has(srcFrame)) continue;

            pending.add(srcFrame);


            const capGen = myGen;
            api.webcompPushToNative(
              webcompId,
              srcFrame,   // localFrame ← cache key the compositor uses
              clip.width,
              clip.height,
            ).then((ok: boolean) => {
              pending.delete(srcFrame);
              if (generationRef.current !== capGen) {
                console.log(`[WebCompSync:${webcompId.slice(-4)}] discard stale f=${srcFrame}`);
                return;
              }
              if (ok) {
                pushed.add(srcFrame);
                if (pushed.size > 120) {
                  const oldest = pushed.values().next().value;
                  if (oldest !== undefined) pushed.delete(oldest);
                }
              }
            }).catch(() => { pending.delete(srcFrame); });
          }

           
          const timeUntilClip = clip.startFrame - cur;
          if (timeUntilClip > 0 && timeUntilClip <= PREWARM_AHEAD) {
            for (let f = 0; f < Math.min(PREWARM_FRAMES, clip.duration); f++) {
              if (ctrl.signal.aborted) break;
              if (pushed.has(f) || pending.has(f)) continue;

              pending.add(f);
              const capGen = myGen;
              api.webcompPushToNative(
                webcompId, f, clip.width, clip.height,
              ).then((ok: boolean) => {
                pending.delete(f);
                if (generationRef.current !== capGen) return;
                if (ok) {
                  pushed.add(f);
                  if (pushed.size > 120) {
                    const oldest = pushed.values().next().value;
                    if (oldest !== undefined) pushed.delete(oldest);
                  }
                }
              }).catch(() => { pending.delete(f); });
            }
          }
        }
      }
      perClipLoopsRef.current.delete(webcompId);
      console.log(`[WebCompSync] loop stopped for ${webcompId.slice(-4)}`);
    };

    loop();
    console.log(`[WebCompSync] loop started for ${webcompId.slice(-4)}`);
  };

  const stopLoopForClip = (webcompId: string) => {
    perClipLoopsRef.current.get(webcompId)?.abort();
    perClipLoopsRef.current.delete(webcompId);
  };

  // Cleanup all loops on unmount
  useEffect(() => {
    return () => {
      for (const ctrl of perClipLoopsRef.current.values()) ctrl.abort();
      perClipLoopsRef.current.clear();
    };
  }, []);

  /* Sync offscreen windows with timeline state   */
  const syncBusyRef = useRef<boolean>(false);
  const syncQueuedRef = useRef<boolean>(false);

  const syncWindows = async () => {
 
    if (syncBusyRef.current) {
      syncQueuedRef.current = true;
      return;
    }
    syncBusyRef.current = true;

    try {
      if (!api?.webcompCreate) return;

      let clips: WcClip[] = [];
      try {
        const [stateRes, listRes] = await Promise.all([
          fetch(`${base()}/timeline/state`),
          fetch(`${base()}/timeline/webcomp/list`),
        ]);
        if (!stateRes.ok || !listRes.ok) return;

        const stateData = await stateRes.json();
        const listData  = await listRes.json();

        const assetMap = new Map<string, any>();
        for (const a of (listData.webcomps ?? [])) assetMap.set(a.assetId, a);

        for (const track of (stateData.tracks ?? [])) {
          for (const clip of (track.clips ?? [])) {
            if (clip.type !== 'webcomp') continue;
            const assetId = clip.webcompId ?? clip.assetId;
            if (!assetId) continue;
            const asset = assetMap.get(assetId);
            if (!asset?.folderPath) continue;
            const htmlUrl = 'file:///' + asset.folderPath.replace(/\\/g, '/') + '/index.html';
            clips.push({
              clipId: clip.clipId,
              webcompId: assetId,
              startFrame: clip.startFrame,
              duration: clip.duration,
              width: asset.width  ?? 1920,
              height: asset.height ?? 1080,
              fps: asset.fps    ?? 30,
              htmlUrl,
            });
          }
        }
      } catch { return; }

      wcClipsRef.current = clips;
      const newIds = new Set(clips.map(c => c.webcompId));

 
      for (const clip of clips) {
        if (knownIdsRef.current.has(clip.webcompId)) continue;

 
        knownIdsRef.current.add(clip.webcompId);
        pushedRef.current.set(clip.webcompId,  new Set());
        pendingRef.current.set(clip.webcompId, new Set());

        try {
          await api.webcompCreate({
            webcompId: clip.webcompId,
            htmlUrl: clip.htmlUrl,
            width: clip.width,
            height: clip.height,
            fps: clip.fps,
          });
          spawnLoopForClip(clip.webcompId);
          console.log('[WebCompSync] Created offscreen window + loop for', clip.webcompId.slice(-8));
        } catch (e) {
          console.error('[WebCompSync] webcompCreate failed', e);
  
          knownIdsRef.current.delete(clip.webcompId);
          pushedRef.current.delete(clip.webcompId);
          pendingRef.current.delete(clip.webcompId);
        }
      }

      /* Destroy windows no longer needed */
      for (const id of Array.from(knownIdsRef.current)) {
        if (!newIds.has(id)) {
          stopLoopForClip(id);          
          api.webcompDestroy?.(id);
          knownIdsRef.current.delete(id);
          pushedRef.current.delete(id);
          pendingRef.current.delete(id);
          console.log('[WebCompSync] Destroyed offscreen window for', id.slice(-8));
        }
      }
    } finally {
      syncBusyRef.current = false;
 
      if (syncQueuedRef.current) {
        syncQueuedRef.current = false;
        syncWindows();
      }
    }
  };

  /* Initial sync   */
  useEffect(() => {
    syncWindows();
    // Debounce 
    let timer: ReturnType<typeof setTimeout> | null = null;
    const handler = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => { syncWindows(); }, 100);
    };
    window.addEventListener('fade:tracks-changed',   handler);
    window.addEventListener('fade:timeline-changed',  handler);  // SSE from backend
    return () => {
      if (timer) clearTimeout(timer);
      window.removeEventListener('fade:tracks-changed',   handler);
      window.removeEventListener('fade:timeline-changed',  handler);
    };
  }, []);

  /* Cleanup all windows on unmount */
  useEffect(() => {
    return () => {
      if (!api?.webcompDestroy) return;
      for (const id of Array.from(knownIdsRef.current)) api.webcompDestroy(id);
      knownIdsRef.current.clear();
      wcClipsRef.current = [];
      pushedRef.current.clear();
      pendingRef.current.clear();
    };
  }, []);
}
