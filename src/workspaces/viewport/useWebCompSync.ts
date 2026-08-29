 
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

export function useWebCompSync() {
  const api = (window as any).electronAPI;
  const knownIdsRef = useRef<Set<string>>(new Set());  // webcompIds with open windows
  const wcClipsRef  = useRef<WcClip[]>([]);             // latest snapshot of wc clips

  //  Fetch timeline state and sync offscreen windows  
  const syncWindows = async () => {
    if (!api?.webcompCreate) return;

    let clips: WcClip[] = [];
    try {
      // Two parallel batch requests instead of N per-clip calls
      const [stateRes, listRes] = await Promise.all([
        fetch(`${base()}/timeline/state`),
        fetch(`${base()}/timeline/webcomp/list`),
      ]);
      if (!stateRes.ok || !listRes.ok) return;

      const stateData = await stateRes.json();
      const listData  = await listRes.json();

      // assetId 
      const assetMap = new Map<string, any>();
      for (const a of (listData.webcomps ?? [])) {
        assetMap.set(a.assetId, a);
      }

      // Walk all tracks 
      for (const track of (stateData.tracks ?? [])) {
        for (const clip of (track.clips ?? [])) {
          if (clip.type !== 'webcomp') continue;

          const assetId = clip.webcompId ?? clip.assetId;
          if (!assetId) continue;

          const asset = assetMap.get(assetId);
          if (!asset?.folderPath) continue;

          // Convert Windows path separator to URL slashes
          const htmlUrl = 'file:///' + asset.folderPath.replace(/\\/g, '/') + '/index.html';

          clips.push({
            clipId: clip.clipId,
            webcompId:  assetId,
            startFrame: clip.startFrame,
            duration: clip.duration,
            width: asset.width  ?? 1920,
            height: asset.height ?? 1080,
            fps: asset.fps ?? 30,
            htmlUrl,
          });
        }
      }
    } catch { return; }

    wcClipsRef.current = clips;

    const newIds = new Set(clips.map(c => c.webcompId));

    // Create windows for new webcompIds
    for (const clip of clips) {
      if (knownIdsRef.current.has(clip.webcompId)) continue;
      try {
        await api.webcompCreate({
          webcompId: clip.webcompId,
          htmlUrl:  clip.htmlUrl,
          width: clip.width,
          height: clip.height,
          fps: clip.fps,
        });
        knownIdsRef.current.add(clip.webcompId);
        console.log('[WebCompSync] Created offscreen window for', clip.webcompId);
      } catch (e) {
        console.error('[WebCompSync] webcompCreate failed', e);
      }
    }

    // Destroy windows for webcompIds no longer in timeline
    for (const id of Array.from(knownIdsRef.current)) {
      if (!newIds.has(id)) {
        api.webcompDestroy?.(id);
        knownIdsRef.current.delete(id);
        console.log('[WebCompSync] Destroyed offscreen window for', id);
      }
    }
  };

  // Push frames on every compositor frame-ready event  
  const busyRef = useRef(false);

  useEffect(() => {
    if (!api?.onFrameReady || !api?.webcompPushToNative) return;

    const cleanup = api.onFrameReady(async (frameNum: number) => {
      // Skip if a previous push is still in-flight to prevent backlog
      if (busyRef.current) return;

      const clips = wcClipsRef.current;
      const active = clips.filter(
        c => frameNum >= c.startFrame && frameNum < c.startFrame + c.duration
      );
      if (active.length === 0) return;

      busyRef.current = true;
      try {
        for (const clip of active) {
          await api.webcompPushToNative(
            clip.webcompId,
            frameNum - clip.startFrame,
            clip.width,
            clip.height,
          );
        }
      } catch (e) {
        // Non-fatal 
      } finally {
        busyRef.current = false;
      }
    });

    return cleanup;
  }, []);  // runs once  

  //  Sync windows on mount  
  useEffect(() => {
    syncWindows();   // initial sync

    const handler = () => syncWindows();
    window.addEventListener('fade:tracks-changed', handler);
    return () => window.removeEventListener('fade:tracks-changed', handler);
  }, []);

  // Cleanup all windows on unmount  
  useEffect(() => {
    return () => {
      if (!api?.webcompDestroy) return;
      for (const id of Array.from(knownIdsRef.current)) {
        api.webcompDestroy(id);
      }
      knownIdsRef.current.clear();
      wcClipsRef.current = [];
    };
  }, []);
}
