import { useEffect, useRef } from 'react';

interface WcClip {
  clipId: string;
  webcompId: string;
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

/** Frames ahead to prefetch during playback */
const PREFETCH_AHEAD = 5;
/** Prefetch loop interval in ms */
const PREFETCH_INTERVAL = 50;

export function useWebCompSync() {
  const api = (window as any).electronAPI;

  const knownIdsRef  = useRef<Set<string>>(new Set());
  const wcClipsRef   = useRef<WcClip[]>([]);
  const curFrameRef  = useRef<number>(0);              // updated by 'fade:frame' event
  const pushedRef    = useRef<Map<string, Set<number>>>(new Map());

  /* Track current playhead via the 'fade:frame' DOM event */
  useEffect(() => {
    const onFrame = (e: Event) => {
      curFrameRef.current = (e as CustomEvent).detail ?? 0;
    };
    window.addEventListener('fade:frame', onFrame);
    return () => window.removeEventListener('fade:frame', onFrame);
  }, []);

  /* Reset pushed cache on seek/stop so frames are re-pushed */
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

  /* Proactive prefetch loop */
  useEffect(() => {
    if (!api?.webcompPushToNative) return;

    let running = true;

    const tick = async () => {
      if (!running) return;
      const clips = wcClipsRef.current;
      if (clips.length === 0) return;

      const cur = curFrameRef.current;

      for (const clip of clips) {
        const pushed = pushedRef.current.get(clip.webcompId)!;

        for (let delta = 0; delta <= PREFETCH_AHEAD; delta++) {
          const absFrame = cur + delta;
          const srcFrame = absFrame - clip.startFrame;
          if (srcFrame < 0 || srcFrame >= clip.duration) continue;
          if (pushed.has(srcFrame)) continue;

          try {
            const ok = await api.webcompPushToNative(
              clip.webcompId,
              srcFrame,
              clip.width,
              clip.height,
            );
            if (ok) {
              pushed.add(srcFrame);
              /* Keep cache bounded: evict oldest when > 90 entries */
              if (pushed.size > 90) {
                pushed.delete(pushed.values().next().value);
              }
            }
          } catch { /* non-fatal */ }

          if (!running) return;
        }
      }
    };

    const id = setInterval(tick, PREFETCH_INTERVAL);
    return () => {
      running = false;
      clearInterval(id);
    };
  }, []);

  /* Fetch timeline state and sync offscreen windows */
  const syncWindows = async () => {
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
            clipId:     clip.clipId,
            webcompId:  assetId,
            startFrame: clip.startFrame,
            duration:   clip.duration,
            width:      asset.width  ?? 1920,
            height:     asset.height ?? 1080,
            fps:        asset.fps    ?? 30,
            htmlUrl,
          });
        }
      }
    } catch { return; }

    wcClipsRef.current = clips;
    const newIds = new Set(clips.map(c => c.webcompId));

    /* Create windows for new IDs */
    for (const clip of clips) {
      if (knownIdsRef.current.has(clip.webcompId)) continue;
      try {
        await api.webcompCreate({
          webcompId: clip.webcompId,
          htmlUrl:   clip.htmlUrl,
          width:     clip.width,
          height:    clip.height,
          fps:       clip.fps,
        });
        knownIdsRef.current.add(clip.webcompId);
        pushedRef.current.set(clip.webcompId, new Set());
        console.log('[WebCompSync] Created offscreen window for', clip.webcompId);
      } catch (e) {
        console.error('[WebCompSync] webcompCreate failed', e);
      }
    }

    /* Destroy windows no longer needed */
    for (const id of Array.from(knownIdsRef.current)) {
      if (!newIds.has(id)) {
        api.webcompDestroy?.(id);
        knownIdsRef.current.delete(id);
        pushedRef.current.delete(id);
        console.log('[WebCompSync] Destroyed offscreen window for', id);
      }
    }
  };

  /* Initial sync + re-sync on track changes */
  useEffect(() => {
    syncWindows();
    const handler = () => { syncWindows(); };
    window.addEventListener('fade:tracks-changed', handler);
    return () => window.removeEventListener('fade:tracks-changed', handler);
  }, []);

  /* Cleanup all windows on unmount */
  useEffect(() => {
    return () => {
      if (!api?.webcompDestroy) return;
      for (const id of Array.from(knownIdsRef.current)) api.webcompDestroy(id);
      knownIdsRef.current.clear();
      wcClipsRef.current = [];
      pushedRef.current.clear();
    };
  }, []);
}
