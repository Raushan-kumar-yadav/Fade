/**
 * useWebCompSync.ts
 *
 * Manages offscreen BrowserWindows for WebComp clips and prefetches frames
 * into the native render engine's cache.
 *
 * KEY FIX — params-change glitch:
 *   When params change the offscreen DOM needs time to react.  We introduce a
 *   "generation" counter: every params change bumps it and sets a brief
 *   "settle" window (PARAMS_SETTLE_MS) during which the prefetch loop will NOT
 *   capture anything.  Any in-flight captures that complete during/after the
 *   settle window are discarded (they carry the old generation and are stale).
 *
 * KEY FIX — duplicate pushes:
 *   A "pending" Set tracks frames currently being captured.  We only await one
 *   capture per (webcompId, srcFrame) at a time.  The interval-based loop is
 *   replaced by a single async loop with a controlled sleep to avoid overlapping
 *   ticks.
 */

import { useEffect, useRef } from 'react';

interface WcClip {
  clipId:     string;
  webcompId:  string;
  startFrame: number;
  duration:   number;
  width:      number;
  height:     number;
  fps:        number;
  htmlUrl:    string;
}

function base(): string {
  return `http://127.0.0.1:${(window as any).__FADE_PORT__ ?? 8000}`;
}

/** Frames ahead to prefetch during playback */
const PREFETCH_AHEAD   = 6;
/** How long to pause captures after a params change (ms) — lets DOM settle */
const PARAMS_SETTLE_MS = 300;
/** Sleep between tick iterations (ms) */
const TICK_SLEEP_MS    = 30;

function sleep(ms: number) {
  return new Promise<void>(r => setTimeout(r, ms));
}

export function useWebCompSync() {
  const api = (window as any).electronAPI;

  const knownIdsRef   = useRef<Set<string>>(new Set());
  const wcClipsRef    = useRef<WcClip[]>([]);
  const curFrameRef   = useRef<number>(0);

  /**
   * pushedRef: frames already successfully cached in the native engine.
   * pendingRef: frames whose capture is currently in flight (to prevent dups).
   * generationRef: bumped on every params change; stale captures are dropped.
   * settleUntilRef: timestamp before which no captures should fire.
   */
  const pushedRef     = useRef<Map<string, Set<number>>>(new Map());
  const pendingRef    = useRef<Map<string, Set<number>>>(new Map());
  const generationRef = useRef<number>(0);
  const settleUntilRef = useRef<number>(0);

  /* ── Track playhead ────────────────────────────────────────────────────── */
  useEffect(() => {
    const onFrame = (e: Event) => {
      curFrameRef.current = (e as CustomEvent).detail ?? 0;
    };
    window.addEventListener('fade:frame', onFrame);
    window.addEventListener('fade:seek',  onFrame);
    return () => {
      window.removeEventListener('fade:frame', onFrame);
      window.removeEventListener('fade:seek',  onFrame);
    };
  }, []);

  /* ── On seek/stop: clear pushed so frames are re-verified ─────────────── */
  useEffect(() => {
    const onReset = () => {
      for (const set of pushedRef.current.values()) set.clear();
      // Don't clear pending — those captures are still in flight; they'll check
      // generation and discard themselves if needed.
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

  /* ── Params change: bump generation + set settle window ───────────────── */
  useEffect(() => {
    const onParamsChange = (e: Event) => {
      const { webcompId } = (e as CustomEvent<{ webcompId: string }>).detail ?? {};
      generationRef.current++;
      settleUntilRef.current = Date.now() + PARAMS_SETTLE_MS;

      // Clear pushed cache for this webcomp so we re-capture with new params
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

  /* ── Prefetch loop ─────────────────────────────────────────────────────── */
  useEffect(() => {
    if (!api?.webcompPushToNative) return;

    let running = true;

    const loop = async () => {
      while (running) {
        await sleep(TICK_SLEEP_MS);
        if (!running) break;

        // Respect params-change settle window
        if (Date.now() < settleUntilRef.current) continue;

        const clips = wcClipsRef.current;
        if (clips.length === 0) continue;

        const cur = curFrameRef.current;
        const myGen = generationRef.current;

        for (const clip of clips) {
          if (!running) break;

          const pushed  = pushedRef.current.get(clip.webcompId)!;
          const pending = pendingRef.current.get(clip.webcompId)!;

          for (let delta = 0; delta <= PREFETCH_AHEAD; delta++) {
            if (!running) break;
            if (Date.now() < settleUntilRef.current) break; // re-check settle

            const absFrame = cur + delta;
            const srcFrame = absFrame - clip.startFrame;
            if (srcFrame < 0 || srcFrame >= clip.duration) continue;

            // Skip if already cached or already in flight
            if (pushed.has(srcFrame) || pending.has(srcFrame)) continue;

            // Mark in-flight immediately to prevent duplicate captures
            pending.add(srcFrame);

            // Fire capture without blocking the loop — but track it
            const capGen = myGen;
            api.webcompPushToNative(
              clip.webcompId,
              srcFrame,
              clip.width,
              clip.height,
            ).then((ok: boolean) => {
              pending.delete(srcFrame);

              // Discard if params changed while we were capturing
              if (generationRef.current !== capGen) {
                console.log(`[WebCompSync] discard stale capture f=${srcFrame} (gen mismatch ${capGen}≠${generationRef.current})`);
                return;
              }

              if (ok) {
                pushed.add(srcFrame);
                // Keep pushed set bounded
                if (pushed.size > 120) {
                  const oldest = pushed.values().next().value;
                  if (oldest !== undefined) pushed.delete(oldest);
                }
              }
            }).catch(() => {
              pending.delete(srcFrame);
            });
          }
        }
      }
    };

    loop();
    return () => { running = false; };
  }, []);

  /* ── Sync offscreen windows with timeline state ────────────────────────── */
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
        pushedRef.current.set(clip.webcompId,  new Set());
        pendingRef.current.set(clip.webcompId, new Set());
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
        pendingRef.current.delete(id);
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
      wcClipsRef.current   = [];
      pushedRef.current.clear();
      pendingRef.current.clear();
    };
  }, []);
}
