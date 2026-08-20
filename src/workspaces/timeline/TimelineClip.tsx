import React, { memo, useCallback, useRef } from 'react';
import { useTimeline, mapBackendTrack } from './TimelineContext';
import { moveClip, trimClip, fetchTimeline, splitClip } from '../../api/useApi';
import {
  type Clip, type Track, type InteractionMode,
  CLIP_COLORS, EDGE_TOLERANCE,
} from './types';

interface Props {
  clip: Clip;
  track: Track;
  trackIndex: number;
  trackHeight: number;
}

 
const TimelineClip = memo(function TimelineClip({ clip, track, trackIndex, trackHeight }: Props) {
  const { state, dispatch } = useTimeline();
  const { zoomX, selectedTool, interaction } = state;

  const clipRef = useRef<HTMLDivElement>(null);
  const isMeMoving  = interaction?.mode === 'move' && interaction.clipId === clip.id;

  // Derived geometry  
  const x     = clip.startFrame * zoomX;
  const width = Math.max(clip.duration * zoomX, 4);
  const color = CLIP_COLORS[clip.type];

  // Cursor based on tool  
  const getCursor = useCallback((localX: number): string => {
    if (selectedTool === 'razor') return 'crosshair';
    if (selectedTool === 'slip')  return 'ew-resize';
    if (selectedTool === 'hand')  return 'grab';
    if (localX <= EDGE_TOLERANCE || localX >= width - EDGE_TOLERANCE) return 'ew-resize';
    return 'grab';
  }, [selectedTool, width]);

  // Mouse down 
  const onMouseDown = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    if (track.locked) return;
    e.preventDefault();
    e.stopPropagation();

    const rect = e.currentTarget.getBoundingClientRect();
    const localX = e.clientX - rect.left;

    if (selectedTool === 'razor') {
      const splitFrame = Math.max(0, Math.round(clip.startFrame + localX / zoomX));
      splitClip(clip.id, splitFrame).then(() => {
        fetchTimeline().then(data => {
          if (data) dispatch({ type: 'SET_TRACKS', tracks: (data.tracks ?? []).map((t: any) => mapBackendTrack(t)) });
        });
      });
      return;
    }

    // Selection
    const isMulti = e.ctrlKey || e.shiftKey || e.metaKey;
    dispatch({ type: 'SELECT_CLIP', clipId: clip.id, trackId: track.id, multi: isMulti });

    let mode: InteractionMode = 'move';
    if (selectedTool === 'slip') {
      mode = 'slip';
    } else if (localX <= EDGE_TOLERANCE) {
      mode = 'trimLeft';
    } else if (localX >= width - EDGE_TOLERANCE) {
      mode = 'trimRight';
    }

    dispatch({
      type: 'START_INTERACTION',
      interaction: {
        clipId: clip.id,
        trackId: track.id,
        mode,
        startMouseX: e.clientX,
        startMouseY: e.clientY,
        startClipFrame: clip.startFrame,
        startTrackIndex: trackIndex,
        pendingFrameDelta: 0,
        pendingTrackDelta: 0,
        accumPx: 0,
      },
    });

    // Set ghost   
    if (mode === 'move') {
      const rect = clipRef.current?.getBoundingClientRect();
      dispatch({
        type: 'SET_GHOST',
        ghost: {
          clip,
          x: rect?.left ?? e.clientX,
          y: rect?.top  ?? e.clientY,
          width: rect?.width  ?? width,
          height: rect?.height ?? (trackHeight - 10),
        },
      });
    }

    // mouse handlers  
    _trimLastX = 0;
    _trimAccum = 0;
    let _trimTotalFrames = 0;

    const onMouseMove = (ev: MouseEvent) => {
      const dx = ev.clientX - e.clientX;

      if (mode === 'move') {
        const frameDelta = Math.round(dx / zoomX);
        const trackDelta = Math.round((ev.clientY - e.clientY) / trackHeight);
        dispatch({ type: 'UPDATE_INTERACTION', pendingFrameDelta: frameDelta, pendingTrackDelta: trackDelta, accumPx: 0 });

        // Move ghost
        const rect = clipRef.current?.getBoundingClientRect();
        const ghostX = (rect?.left ?? e.clientX) + dx;
        const ghostY = (rect?.top  ?? e.clientY) + (ev.clientY - e.clientY);
        dispatch({ type: 'SET_GHOST', ghost: { clip, x: ghostX, y: ghostY, width: rect?.width ?? width, height: rect?.height ?? (trackHeight - 10) } });

      } else if (mode === 'trimLeft' || mode === 'trimRight') {
        const pixelStep = (ev.clientX - e.clientX) - _trimLastX;
        _trimLastX = ev.clientX - e.clientX;
        _trimAccum += pixelStep;
        const frameDelta = Math.round(_trimAccum / zoomX);
        if (frameDelta !== 0) {
          _trimAccum -= frameDelta * zoomX;
          _trimTotalFrames += frameDelta;
          dispatch({ type: 'TRIM_CLIP', clipId: clip.id, trackId: track.id, side: mode === 'trimLeft' ? 'left' : 'right', frameDelta });
        }

      } else if (mode === 'slip') {
        const pixelStep = (ev.clientX - e.clientX) - _trimLastX;
        _trimLastX = ev.clientX - e.clientX;
        _trimAccum += pixelStep;
        const frameDelta = Math.round(_trimAccum / zoomX);
        if (frameDelta !== 0) {
          _trimAccum -= frameDelta * zoomX;
          _trimTotalFrames += frameDelta;
          dispatch({ type: 'TRIM_CLIP', clipId: clip.id, trackId: track.id, side: 'left', frameDelta });
        }
      }
    };

    const onMouseUp = (ev: MouseEvent) => {
      if (mode === 'move') {
        dispatch({ type: 'COMMIT_MOVE' });
        const dx = ev.clientX - e.clientX;
        const frameDelta = Math.round(dx / zoomX);
        const trackDelta = Math.round((ev.clientY - e.clientY) / trackHeight);
        const newStart = Math.max(0, clip.startFrame + frameDelta);
        const dstIdx = Math.max(0, trackIndex + trackDelta);
        
        moveClip(clip.id, newStart, dstIdx).then(() => {
          fetchTimeline().then(data => {
            if (data) dispatch({ type: 'SET_TRACKS', tracks: (data.tracks ?? []).map((t: any) => mapBackendTrack(t)) });
          });
        });
      } else {
        dispatch({ type: 'END_INTERACTION' });
        if (_trimTotalFrames !== 0 && (mode === 'trimLeft' || mode === 'trimRight' || mode === 'slip')) {
          const side = mode === 'trimRight' ? 'right' : 'left';
          trimClip(clip.id, side, _trimTotalFrames).then(() => {
            fetchTimeline().then(data => {
              if (data) dispatch({ type: 'SET_TRACKS', tracks: (data.tracks ?? []).map((t: any) => mapBackendTrack(t)) });
            });
          });
        }
      }
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  }, [clip, track, trackIndex, trackHeight, zoomX, selectedTool, width, dispatch]);

  // Render  
  const isSelected = clip.isSelected;
  const dimForGhost = isMeMoving;

  return (
    <div
      ref={clipRef}
      className={`tl-clip ${isSelected ? 'tl-clip--selected' : ''} ${dimForGhost ? 'tl-clip--ghost-dim' : ''}`}
      style={{
        left: x,
        width,
        top: 5,
        height: trackHeight - 10,
        background: color,
        borderColor: isSelected ? lighten(color, 0.4) : lighten(color, 0.2),
      }}
      onMouseDown={onMouseDown}
      onMouseMove={(e) => {
        const localX = e.clientX - e.currentTarget.getBoundingClientRect().left;
        e.currentTarget.style.cursor = getCursor(localX);
      }}
      title={clip.name}
      role="button"
      aria-label={`Clip: ${clip.name}`}
    >
       <div className="tl-clip__trim tl-clip__trim--left" />
      <div className="tl-clip__trim tl-clip__trim--right" />

      {/* Label */}
      <span className="tl-clip__label">{clip.name}</span>
    </div>
  );
});

// Helpers  

 let _trimAccum = 0;
let _trimLastX = 0;



 function lighten(hex: string, amount: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  const nr = Math.round(r + (255 - r) * amount);
  const ng = Math.round(g + (255 - g) * amount);
  const nb = Math.round(b + (255 - b) * amount);
  return `rgb(${nr},${ng},${nb})`;
}

export default TimelineClip;
