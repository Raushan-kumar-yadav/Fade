import React, { memo, useCallback, useEffect, useRef, useState } from 'react';
import { useTimeline } from './TimelineContext';
import { type Track, type Clip, MIN_TRACK_H, MAX_TRACK_H } from './types';
import TimelineClip from './TimelineClip';
import { addClipToTimeline, addSvgClipToTimeline, addCompClipToTimeline, addWebCompClipToTimeline, type AssetItem } from '../../api/useApi';
import { useTool, isCreationTool, isShapeTool, shapeTypeOf } from '../../context/toolContext';
import { useSelection } from '../../context/selectionContext';
import { textApi, shapeApi, penApi, transitionApi, type TransitionInfo } from '../../api/toolsApi';
import TransitionWidget from './TransitionWidget';

interface Props {
  track: Track;
  trackIndex: number;
  scrollLeft?: number;
}

//   helpers  

function xToFrame(clientX: number, rowEl: HTMLDivElement, scrollLeft: number, zoomX: number): number {
  const rect  = rowEl.getBoundingClientRect();
  const localX = clientX - rect.left;
  return Math.max(0, Math.round((localX + scrollLeft) / zoomX));
}

const DEFAULT_DURATION = 150;  

//   Component  

const TrackRow = memo(function TrackRow({ track, trackIndex, scrollLeft = 0 }: Props) {
  const { state, dispatch } = useTimeline();
  const { activeTool } = useTool();
  const { setSelected } = useSelection();

  const resizingRef = useRef(false);
  const startYRef = useRef(0);
  const startHRef = useRef(0);
  const rowRef = useRef<HTMLDivElement>(null);

  const [dropOver, setDropOver]  = useState(false);
  const [placing, setPlacing] = useState(false);
  const [cursorPct, setCursorPct] = useState(50); // for guide line
  const [transitions, setTransitions] = useState<TransitionInfo[]>([]);
 
 
  const clipIdsRef = useRef<Set<string>>(new Set(track.clips.map(c => c.id)));
  useEffect(() => {
    clipIdsRef.current = new Set(track.clips.map(c => c.id));
  }, [track.clips]);

  const fetchTransitions = useCallback(() => {
    transitionApi.listAll().then(r => {
      setTransitions(r.transitions.filter(tr => clipIdsRef.current.has(tr.clipA_id)));
    }).catch(() => {});
  }, []); // no deps — always reads from ref

  React.useEffect(() => {
    fetchTransitions();
    window.addEventListener('fade:transition-changed', fetchTransitions);
    return () => window.removeEventListener('fade:transition-changed', fetchTransitions);
  }, [fetchTransitions]);

  
  const onRowClick = useCallback(async (e: React.MouseEvent<HTMLDivElement>) => {
    const bg = (e.target as HTMLElement).classList.contains('tl-track-row__bg')
            || (e.target as HTMLElement) === rowRef.current;

  
    if (isCreationTool(activeTool) && bg) {
      e.stopPropagation();
      if (track.locked) return;

      const frame = xToFrame(e.clientX, rowRef.current!, scrollLeft, state.zoomX);
      await placeClip(frame);
      return;
    }

    if (bg) {
      dispatch({ type: 'CLEAR_SELECTION' });
      setSelected(null);
    }
  }, [activeTool, dispatch, track, trackIndex, scrollLeft, state.zoomX]);

   
  const placeClip = useCallback(async (frame: number) => {
    setPlacing(true);
    const tool = activeTool;

    try {
      let result: any = null;

      if (tool === 'text') {
        result = await textApi.add(frame, DEFAULT_DURATION, {
          text: 'New Text',
          fontFamily: 'Arial',
          fontSize: 48,
          color: [1, 1, 1, 1],
        });
      } else if (tool === 'solid') {
        result = await shapeApi.add(frame, DEFAULT_DURATION, {
          shapeType:  'rect',
          width: 1920,
          height: 1080,
          fillColor:  [0.15, 0.15, 0.22, 1.0],
        });
      } else if (tool === 'adjustment') {
        // Adjustment 
        result = await shapeApi.add(frame, DEFAULT_DURATION, {
          shapeType: 'rect',
          width: 1920,
          height: 1080,
          fillColor: [0.2, 0.6, 1.0, 0.08],
          strokeColor:[0.3, 0.7, 1.0, 0.3],
          strokeWidth: 2,
        });
      } else if (tool === 'shape:path') {
        result = await penApi.add(frame, DEFAULT_DURATION, [], false, {
          strokeColor: [1, 1, 1, 1],
          strokeWidth: 2,
          fillOpacity: 0,
        });
      } else if (isShapeTool(tool)) {
        const sType = shapeTypeOf(tool)!;
        result = await shapeApi.add(frame, DEFAULT_DURATION, {
          shapeType:  sType as any,
          width: 200,
          height: 150,
          radiusX: 100,
          radiusY: 70,
          outerRadius: 80,
          innerRadius: 32,
          numPoints: 5,
          numSides: 6,
          polygonRadius: 80,
          arcRadius: 80,
          fillColor: [0.4, 0.4, 1.0, 1.0],
        });
      }

      if (result) {
        // Add to timeline state optimistically
        const newClip: Clip = {
          id: result.clipId ?? `tmp-${Date.now()}`,
          name: clipLabel(tool),
          startFrame: frame,
          duration:   DEFAULT_DURATION,
          type: clipVisualType(tool),
          isSelected: false,
        };
        dispatch({ type: 'ADD_CLIP', trackId: track.id, clip: newClip });
      }
    } catch (err) {
      console.error('[TrackRow] place clip error:', err);
    } finally {
      setPlacing(false);
    }
  }, [activeTool, track.id, dispatch]);

  // Resize handle  
  const onResizeMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    resizingRef.current = true;
    startYRef.current = e.clientY;
    startHRef.current = track.height;

    const onMove = (ev: MouseEvent) => {
      if (!resizingRef.current) return;
      const proposed = Math.max(MIN_TRACK_H, Math.min(MAX_TRACK_H,
        startHRef.current + (ev.clientY - startYRef.current)));
      dispatch({ type: 'RESIZE_TRACK', trackId: track.id, height: proposed });
    };
    const onUp = () => {
      resizingRef.current = false;
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }, [track.id, track.height, dispatch]);

  // Drag-from-library or transitions  
  const onDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    if (e.dataTransfer.types.includes('application/fade-asset') ||
        e.dataTransfer.types.includes('application/fade-transition') ||
        e.dataTransfer.types.includes('application/fade-comp') ||
        e.dataTransfer.types.includes('application/fade-webcomp') ||
        e.dataTransfer.types.includes('application/fade-scene-hit') ||
        e.dataTransfer.types.includes('text/fade-scene-hit')) {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'copy';
      setDropOver(true);
    }
  }, []);

  const onDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    // Only clear dropOver  
    if (rowRef.current && rowRef.current.contains(e.relatedTarget as Node)) return;
    setDropOver(false);
  }, []);

  const onDrop = useCallback(async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDropOver(false);

    const rowRect  = (e.currentTarget as HTMLDivElement).getBoundingClientRect();
    const localX = e.clientX - rowRect.left;
    const frame = Math.max(0, Math.round((localX + scrollLeft) / state.zoomX));

    //   Handle Transition Drop  
    const transTypeId = e.dataTransfer.getData('application/fade-transition');
    if (transTypeId) {
      // Gather ALL clips across ALL tracks  
      const allClips: Array<Clip & { _trackId: string }> = [];
      for (const t of state.tracks) {
        for (const c of t.clips) {
          allClips.push({ ...c, _trackId: t.id });
        }
      }

      // Find the outgoing clip  
      const SNAP_FRAMES = 90;  
      let bestA: (Clip & { _trackId: string }) | null = null;
      let bestADist = Infinity;
      for (const c of allClips) {
        const endF = c.startFrame + c.duration;
        const dist = Math.abs(endF - frame);
        if (dist < bestADist) { bestADist = dist; bestA = c; }
      }

       
      // and is NOT the same clip
      let bestB: (Clip & { _trackId: string }) | null = null;
      let bestBDist = Infinity;
      if (bestA) {
        const aEnd = bestA.startFrame + bestA.duration;
        for (const c of allClips) {
          if (c.id === bestA.id) continue;
          const dist = Math.abs(c.startFrame - aEnd);
          if (dist < bestBDist) { bestBDist = dist; bestB = c; }
        }
      }

      if (bestA && bestB && bestADist < SNAP_FRAMES && bestBDist < SNAP_FRAMES) {
        try {
          await transitionApi.add({
            typeId:   transTypeId,
            duration: 30,
            clipA_id: bestA.id,
            clipB_id: bestB.id,
            trackId:  bestA._trackId,
          });
          // Dispatch both events so the transition list  
          window.dispatchEvent(new CustomEvent('fade:transition-changed'));
          window.dispatchEvent(new CustomEvent('fade:tracks-changed'));
        } catch (err) {
          console.error('[TrackRow] Add transition error:', err);
        }
      } else {
        console.warn('[TrackRow] No eligible clip boundary found near frame', frame);
      }
      return;
    }

    // Handle Comp Drop  
    const rawComp = e.dataTransfer.getData('application/fade-comp');
    if (rawComp) {
      let compMeta;
      try { compMeta = JSON.parse(rawComp); }
      catch { return; }

      const duration = 90;
      const optimisticClip: Clip = {
        id: `tmp-${Date.now()}`,
        name: compMeta.name,
        startFrame: frame,
        duration,
        type: 'comp',
        isSelected: false,
      };
      dispatch({ type: 'ADD_CLIP', trackId: track.id, clip: optimisticClip });

      try {
        const result = await addCompClipToTimeline(compMeta.compId, trackIndex, frame, duration);
        if (result) {
          const realClip: Clip = {
            id: result.clipId,
            name: compMeta.name,
            startFrame: result.startFrame,
            duration: result.duration,
            type: 'comp',
            isSelected: false,
          };
          dispatch({ type: 'ADD_CLIP', trackId: track.id, clip: realClip });
        } else {
          dispatch({ type: 'DELETE_CLIP', clipId: optimisticClip.id });
        }
      } catch (err) {
        console.error('[TrackRow] Failed to drop comp', err);
        dispatch({ type: 'DELETE_CLIP', clipId: optimisticClip.id });
      }
      return;
    }

    // Handle WebComp Drop
    const rawWebComp = e.dataTransfer.getData('application/fade-webcomp');
    if (rawWebComp) {
      let wcMeta: { assetId: string; name: string; durationFrames?: number };
      try { wcMeta = JSON.parse(rawWebComp); }
      catch { return; }

      const duration = wcMeta.durationFrames || 150;
      const optimisticClip: Clip = {
        id: `tmp-${Date.now()}`,
        name: wcMeta.name,
        startFrame: frame,
        duration,
        type: 'webcomp',
        isSelected: false,
      };
      dispatch({ type: 'ADD_CLIP', trackId: track.id, clip: optimisticClip });

      try {
        const result = await addWebCompClipToTimeline(wcMeta.assetId, trackIndex, frame, duration);
        if (result) {
          const realClip: Clip = {
            id: result.clipId,
            name: wcMeta.name,
            startFrame: result.startFrame,
            duration: result.duration,
            type: 'webcomp',
            isSelected: false,
          };
          dispatch({ type: 'DELETE_CLIP', clipId: optimisticClip.id });
          dispatch({ type: 'ADD_CLIP', trackId: track.id, clip: realClip });
          // Signal useWebCompSync to create  
          window.dispatchEvent(new CustomEvent('fade:tracks-changed'));
        } else {
          dispatch({ type: 'DELETE_CLIP', clipId: optimisticClip.id });
        }
      } catch (err) {
        console.error('[TrackRow] Failed to drop webcomp', err);
        dispatch({ type: 'DELETE_CLIP', clipId: optimisticClip.id });
      }
      return;
    }

     
    //   Handle Scene-Hit Drop  
    const rawSceneHit =
      e.dataTransfer.getData('application/fade-scene-hit') ||
      e.dataTransfer.getData('text/fade-scene-hit');  // Electron fallback
    if (rawSceneHit) {
      let hit: { assetId: string; filename: string; type: string; inFrames: number; duration: number };
      try { hit = JSON.parse(rawSceneHit); }
      catch { return; }

      const optimisticClip: Clip = {
        id: `tmp-${Date.now()}`,
        name: hit.filename,
        startFrame: frame,
        duration:   hit.duration,
        type: hit.type === 'image' ? 'image' : 'video',
        isSelected: false,
      };
      dispatch({ type: 'ADD_CLIP', trackId: track.id, clip: optimisticClip });

      try {
        const result = await addClipToTimeline(
          hit.assetId, trackIndex, frame, hit.duration, hit.inFrames,
        );
        if (result) {
          // Replace optimistic with real clip
          dispatch({ type: 'DELETE_CLIP', clipId: optimisticClip.id });
          dispatch({ type: 'ADD_CLIP', trackId: track.id, clip: {
            id: result.clipId,
            name: hit.filename,
            startFrame: result.startFrame,
            duration: result.duration,
            type: optimisticClip.type,
            isSelected: false,
          }});
          window.dispatchEvent(new CustomEvent('fade:tracks-changed'));
        } else {
          // API returned null — rollback
          dispatch({ type: 'DELETE_CLIP', clipId: optimisticClip.id });
          console.warn('[TrackRow] addClipToTimeline returned null for scene hit', hit.assetId);
        }
      } catch (err) {
        console.error('[TrackRow] Failed to drop scene hit', err);
        dispatch({ type: 'DELETE_CLIP', clipId: optimisticClip.id });
      }
      return;
    }

    // Handle Asset Drop
    const rawAsset = e.dataTransfer.getData('application/fade-asset');
    if (!rawAsset) return;

    let asset: AssetItem;
    try { asset = JSON.parse(rawAsset); }
    catch { return; }

    const duration = 150;  
    const optimisticClip: Clip = {
      id: `tmp-${Date.now()}`,
      name: asset.filename,
      startFrame: frame,
      duration,
      type: asset.type === 'audio' ? 'audio'
                : asset.type === 'image' ? 'image'
                : asset.type === 'svg'   ? 'shape'
                : 'video',
      isSelected: false,
    };
    dispatch({ type: 'ADD_CLIP', trackId: track.id, clip: optimisticClip });

    try {
      let result: { clipId: string; startFrame: number; duration: number } | null = null;
      if (asset.type === 'svg') {
        result = await addSvgClipToTimeline(asset.filepath, trackIndex, frame, duration);
      } else {
        result = await addClipToTimeline(asset.assetId, trackIndex, frame, duration);
      }
      // Remove optimistic placeholde 
      dispatch({ type: 'DELETE_CLIP', clipId: optimisticClip.id });
      if (result) {
        const realClip: Clip = {
          id: result.clipId,
          name: asset.filename,
          startFrame: result.startFrame,
          duration: result.duration,    
          type: optimisticClip.type,
          isSelected: false,
        };
        dispatch({ type: 'ADD_CLIP', trackId: track.id, clip: realClip });
      }
      // Always notify so AudioEngine reloads its clip list 
      window.dispatchEvent(new CustomEvent('fade:tracks-changed'));
    } catch (err) {
      console.error('[TrackRow] addClipToTimeline failed:', err);
      dispatch({ type: 'DELETE_CLIP', clipId: optimisticClip.id });
    }
  }, [track.id, track.clips, trackIndex, scrollLeft, state.zoomX, dispatch]);

  // Cursor guide for creation tools  
  const onMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (!rowRef.current || !isCreationTool(activeTool)) return;
    const rect = rowRef.current.getBoundingClientRect();
    const pct  = ((e.clientX - rect.left) / rect.width) * 100;
    setCursorPct(Math.max(0, Math.min(100, pct)));
  }, [activeTool]);

  // Cursor for creation tools  
  const rowCursor = isCreationTool(activeTool) && !track.locked ? 'crosshair' : undefined;

  const isEven = trackIndex % 2 === 0;

  return (
    <div
      ref={rowRef}
      className={[
        'tl-track-row',
        isEven ? 'tl-track-row--even' : 'tl-track-row--odd',
        track.locked  ? 'tl-track-row--locked'  : '',
        dropOver ? 'tl-track-row--dropover' : '',
        placing ? 'tl-track-row--placing'  : '',
        isCreationTool(activeTool) && !track.locked ? 'tl-track-row--creation' : '',
      ].join(' ')}
      style={{
        height: track.height,
        position: 'relative',
        cursor: rowCursor,
        // CSS var drives  
        ['--tbx-cursor-x' as any]: `${cursorPct}%`,
      }}
      onClick={onRowClick}
      onMouseMove={onMouseMove}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      aria-label={`Track: ${track.name}`}
    >
      <div className="tl-track-row__bg" style={{ position: 'absolute', inset: 0 }} />
      <div className="tl-track-row__sep" />

      {track.clips.map(clip => (
        <TimelineClip
          key={clip.id}
          clip={clip}
          track={track}
          trackIndex={trackIndex}
          trackHeight={track.height}
        />
      ))}

      {/* Render Transitions  */}
      {transitions.map(tr => {
        const ca = track.clips.find(c => c.id === tr.clipA_id);
        if (!ca) return null;  
        const centerFrame = ca.startFrame + ca.duration;
        return (
          <TransitionWidget
            key={tr.transId}
            transition={tr}
            trackId={track.id}
            zoomX={state.zoomX}
            centerFrame={centerFrame}
          />
        );
      })}

      {/* Live guide line  */}
      {isCreationTool(activeTool) && !track.locked && !placing && (
        <div className="tl-track-row__guide" />
      )}

      {/* Drop hint */}
      {dropOver && (
        <div className="tl-track-row__drop-hint">Drop to add clip</div>
      )}

      {/* Click to add */}
      {isCreationTool(activeTool) && !track.locked && !placing && (
        <div className="tl-track-row__create-hint">
          Click to add {clipLabel(activeTool)}
        </div>
      )}

      {placing && (
        <div className="tl-track-row__placing-hint">Adding…</div>
      )}

      {/* Resize handle */}
      <div
        className="tl-track-row__resize"
        onMouseDown={onResizeMouseDown}
        aria-label="Resize track height"
        title="Drag to resize"
      />
    </div>
  );
});

// Helpers 

function clipLabel(tool: string): string {
  const map: Record<string, string> = {
    text: 'Text',
    solid: 'Solid',
    adjustment: 'Adjustment',
    'shape:rect': 'Rectangle',
    'shape:circle': 'Circle',
    'shape:ellipse':'Ellipse',
    'shape:star': 'Star',
    'shape:polygon':'Polygon',
    'shape:line': 'Line',
    'shape:arc': 'Arc',
    'shape:path': 'Pen Path',
  };
  return map[tool] ?? 'Clip';
}

function clipVisualType(tool: string): Clip['type'] {
  if (tool === 'text') return 'image';
  return 'image';
}

export default TrackRow;
