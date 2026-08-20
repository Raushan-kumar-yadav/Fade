import React, { memo, useCallback, useRef, useState } from 'react';
import { useTimeline } from './TimelineContext';
import { type Track, type Clip, MIN_TRACK_H, MAX_TRACK_H } from './types';
import TimelineClip from './TimelineClip';
import { addClipToTimeline, type AssetItem } from '../../api/useApi';
import { useTool, isCreationTool, isShapeTool, shapeTypeOf } from '../../context/toolContext';
import { useSelection } from '../../context/selectionContext';
import { textApi, shapeApi, penApi } from '../../api/toolsApi';

interface Props {
  track:       Track;
  trackIndex:  number;
  scrollLeft?: number;
}

// ── helpers ────────────────────────────────────────────────────────────────

function xToFrame(clientX: number, rowEl: HTMLDivElement, scrollLeft: number, zoomX: number): number {
  const rect  = rowEl.getBoundingClientRect();
  const localX = clientX - rect.left;
  return Math.max(0, Math.round((localX + scrollLeft) / zoomX));
}

const DEFAULT_DURATION = 150; // 5 s @ 30 fps

// ── Component ──────────────────────────────────────────────────────────────

const TrackRow = memo(function TrackRow({ track, trackIndex, scrollLeft = 0 }: Props) {
  const { state, dispatch } = useTimeline();
  const { activeTool }      = useTool();
  const { setSelected }     = useSelection();

  const resizingRef = useRef(false);
  const startYRef   = useRef(0);
  const startHRef   = useRef(0);
  const rowRef      = useRef<HTMLDivElement>(null);

  const [dropOver,  setDropOver]  = useState(false);
  const [placing,   setPlacing]   = useState(false);
  const [cursorPct, setCursorPct] = useState(50); // for guide line

  // ── Clear selection on empty-row click (pointer mode) ───────────────────
  const onRowClick = useCallback(async (e: React.MouseEvent<HTMLDivElement>) => {
    const bg = (e.target as HTMLElement).classList.contains('tl-track-row__bg')
            || (e.target as HTMLElement) === rowRef.current;

    // ── Creation-tool: add clip at clicked position ──────────────────────
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

  // ── Place a clip based on the active creation tool ───────────────────────
  const placeClip = useCallback(async (frame: number) => {
    setPlacing(true);
    const tool = activeTool;

    try {
      let result: any = null;

      if (tool === 'text') {
        result = await textApi.add(frame, DEFAULT_DURATION, {
          text:       'New Text',
          fontFamily: 'Arial',
          fontSize:   48,
          color:      [1, 1, 1, 1],
        });
      } else if (tool === 'solid') {
        result = await shapeApi.add(frame, DEFAULT_DURATION, {
          shapeType:  'rect',
          width:      1920,
          height:     1080,
          fillColor:  [0.15, 0.15, 0.22, 1.0],
        });
      } else if (tool === 'adjustment') {
        // Adjustment: solid rect that acts as adjustment layer
        result = await shapeApi.add(frame, DEFAULT_DURATION, {
          shapeType:  'rect',
          width:      1920,
          height:     1080,
          fillColor:  [0.2, 0.6, 1.0, 0.08],
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
          width:       200,
          height:      150,
          radiusX:     100,
          radiusY:     70,
          outerRadius: 80,
          innerRadius: 32,
          numPoints:   5,
          numSides:    6,
          polygonRadius: 80,
          arcRadius:   80,
          fillColor:   [0.4, 0.4, 1.0, 1.0],
        });
      }

      if (result) {
        // Add to timeline state optimistically
        const newClip: Clip = {
          id:         result.clipId ?? `tmp-${Date.now()}`,
          name:       clipLabel(tool),
          startFrame: frame,
          duration:   DEFAULT_DURATION,
          type:       clipVisualType(tool),
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

  // ── Resize handle ────────────────────────────────────────────────────────
  const onResizeMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    resizingRef.current = true;
    startYRef.current   = e.clientY;
    startHRef.current   = track.height;

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

  // ── Drag-from-library ────────────────────────────────────────────────────
  const onDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    if (!e.dataTransfer.types.includes('application/fade-asset')) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
    setDropOver(true);
  }, []);

  const onDragLeave = useCallback(() => setDropOver(false), []);

  const onDrop = useCallback(async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDropOver(false);

    const raw = e.dataTransfer.getData('application/fade-asset');
    if (!raw) return;

    let asset: AssetItem;
    try { asset = JSON.parse(raw); }
    catch { return; }

    const rowRect  = (e.currentTarget as HTMLDivElement).getBoundingClientRect();
    const localX   = e.clientX - rowRect.left;
    const frame    = Math.max(0, Math.round((localX + scrollLeft) / state.zoomX));
    const duration = 150;

    const optimisticClip: Clip = {
      id:         `tmp-${Date.now()}`,
      name:       asset.filename,
      startFrame: frame,
      duration,
      type:       asset.type === 'audio' ? 'audio'
                : asset.type === 'image' ? 'image'
                : 'video',
      isSelected: false,
    };
    dispatch({ type: 'ADD_CLIP', trackId: track.id, clip: optimisticClip });

    const result = await addClipToTimeline(asset.assetId, trackIndex, frame, duration);
    if (result) {
      const realClip: Clip = {
        id:         result.clipId,
        name:       asset.filename,
        startFrame: result.startFrame,
        duration:   result.duration,
        type:       optimisticClip.type,
        isSelected: false,
      };
      dispatch({ type: 'ADD_CLIP', trackId: track.id, clip: realClip });
    }
  }, [track.id, trackIndex, scrollLeft, state.zoomX, dispatch]);

  // ── Cursor guide for creation tools ─────────────────────────────────────
  const onMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (!rowRef.current || !isCreationTool(activeTool)) return;
    const rect = rowRef.current.getBoundingClientRect();
    const pct  = ((e.clientX - rect.left) / rect.width) * 100;
    setCursorPct(Math.max(0, Math.min(100, pct)));
  }, [activeTool]);

  // ── Cursor for creation tools ────────────────────────────────────────────
  const rowCursor = isCreationTool(activeTool) && !track.locked ? 'crosshair' : undefined;

  const isEven = trackIndex % 2 === 0;

  return (
    <div
      ref={rowRef}
      className={[
        'tl-track-row',
        isEven        ? 'tl-track-row--even'    : 'tl-track-row--odd',
        track.locked  ? 'tl-track-row--locked'  : '',
        dropOver      ? 'tl-track-row--dropover' : '',
        placing       ? 'tl-track-row--placing'  : '',
        isCreationTool(activeTool) && !track.locked ? 'tl-track-row--creation' : '',
      ].join(' ')}
      style={{
        height: track.height,
        position: 'relative',
        cursor: rowCursor,
        // CSS var drives the guide-line X position
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

      {/* Live guide line — follows cursor in creation mode */}
      {isCreationTool(activeTool) && !track.locked && !placing && (
        <div className="tl-track-row__guide" />
      )}

      {/* Drop hint */}
      {dropOver && (
        <div className="tl-track-row__drop-hint">Drop to add clip</div>
      )}

      {/* "Click to add …" label */}
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

// ── Helpers ─────────────────────────────────────────────────────────────────

function clipLabel(tool: string): string {
  const map: Record<string, string> = {
    text:           'Text',
    solid:          'Solid',
    adjustment:     'Adjustment',
    'shape:rect':   'Rectangle',
    'shape:circle': 'Circle',
    'shape:ellipse':'Ellipse',
    'shape:star':   'Star',
    'shape:polygon':'Polygon',
    'shape:line':   'Line',
    'shape:arc':    'Arc',
    'shape:path':   'Pen Path',
  };
  return map[tool] ?? 'Clip';
}

function clipVisualType(tool: string): Clip['type'] {
  if (tool === 'text') return 'image';
  return 'image';
}

export default TrackRow;
