import React, { memo, useCallback, useRef, useEffect, useState, useLayoutEffect } from "react";
import ReactDOM from "react-dom";
import { useSelection } from "../../context/selectionContext";
import {
  useTimeline,
  mapBackendTrack,
  mapBackendTracksPreservingOrder,
} from "./TimelineContext";
import { moveClip, trimClip, fetchTimeline, splitClip } from "../../api/useApi";
import { waveformApi, effectsApi } from "../../api/toolsApi";
import {
  type Clip,
  type Track,
  type InteractionMode,
  CLIP_COLORS,
  EDGE_TOLERANCE,
} from "./types";

interface Props {
  clip: Clip;
  track: Track;
  trackIndex: number;
  trackHeight: number;
}

const TimelineClip = memo(function TimelineClip({
  clip,
  track,
  trackIndex,
  trackHeight,
}: Props) {
  const { state, dispatch } = useTimeline();
  const { setSelected } = useSelection();
  const { zoomX, selectedTool, interaction } = state;

  const clipRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [peaks, setPeaks]             = useState<number[]>([]);
  const [waveLoading, setWaveLoading] = useState(false);

  // Derived geometry  
  const x = clip.startFrame * zoomX;
  const width = Math.max(clip.duration * zoomX, 4);
  const color = CLIP_COLORS[clip.type];

  // Only video and audio clips produce waveforms
  const wantsWaveform = clip.type === 'video' || clip.type === 'audio';

  // Fetch waveform asynchronously  
  useEffect(() => {
    if (!wantsWaveform || !clip.assetId) return;
    let cancelled = false;
    setWaveLoading(true);
    waveformApi.get(clip.assetId, 1000)
      .then(d => {
        if (!cancelled) {
          setPeaks(d.peaks);
          setWaveLoading(false);
        }
      })
      .catch(() => { if (!cancelled) setWaveLoading(false); });
    return () => { cancelled = true; };
  }, [clip.assetId, wantsWaveform]);

   
  const drawWaveform = useCallback((canvas: HTMLCanvasElement | null) => {
    if (!canvas || peaks.length === 0) return;
    canvas.width  = Math.max(1, Math.round(width));
    canvas.height = Math.max(1, trackHeight - 10);
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const W = canvas.width;
    const H = canvas.height;
    ctx.clearRect(0, 0, W, H);
    const grad = ctx.createLinearGradient(0, 0, 0, H);
    grad.addColorStop(0,   'rgba(255,255,255,0.55)');
    grad.addColorStop(0.5, 'rgba(255,255,255,0.30)');
    grad.addColorStop(1,   'rgba(255,255,255,0.55)');
    ctx.fillStyle = grad;
    const barW = W / peaks.length;
    for (let i = 0; i < peaks.length; i++) {
      const h = Math.max(1, peaks[i] * H);
      ctx.fillRect(i * barW, (H - h) / 2, Math.max(1, barW - 0.5), h);
    }
  }, [peaks, width, trackHeight]);

  // ref-callback 
  const canvasRefCallback = useCallback((el: HTMLCanvasElement | null) => {
    canvasRef.current = el;
    drawWaveform(el);
  }, [drawWaveform]);

  // Redraw  
  useLayoutEffect(() => {
    drawWaveform(canvasRef.current);
  }, [drawWaveform]);



  const isMeMoving =
    interaction?.mode === "move" && interaction.clipId === clip.id;

  // Right-click context menu  
  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number } | null>(null);

  const onContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setCtxMenu({ x: e.clientX, y: e.clientY });
  }, []);

  useEffect(() => {
    if (!ctxMenu) return;
    const close = () => setCtxMenu(null);
    window.addEventListener('mousedown', close, { once: true });
    return () => window.removeEventListener('mousedown', close);
  }, [ctxMenu]);

  const handleDelete = useCallback(async () => {
    setCtxMenu(null);
    try {
      const port = (window as any).__FADE_PORT__ ?? 8000;
      await fetch(`http://127.0.0.1:${port}/timeline/clips/${clip.id}`, { method: 'DELETE' });
      dispatch({ type: 'DELETE_CLIP', clipId: clip.id });
      window.dispatchEvent(new CustomEvent('fade:tracks-changed'));
    } catch (err) {
      console.error('[TimelineClip] delete failed', err);
    }
  }, [clip.id, dispatch]);

  const handleSplit = useCallback(() => {
    setCtxMenu(null);
    const frame = state.currentFrame;
    if (frame <= clip.startFrame || frame >= clip.startFrame + clip.duration) return;
    splitClip(clip.id, frame).then((result) => {
      if (!result) return;
      fetchTimeline().then((data) => {
        if (data) dispatch({ type: 'SET_TRACKS', tracks: mapBackendTracksPreservingOrder(state.tracks, data.tracks ?? []) });
      });
    });
  }, [clip.id, clip.startFrame, clip.duration, state.currentFrame, state.tracks, dispatch]);

  const onDoubleClick = useCallback((e: React.MouseEvent) => {
    if (clip.type !== 'comp' || !clip.compId) return;
    e.stopPropagation();
    dispatch({ type: 'ENTER_COMP', compId: clip.compId, compName: clip.name });
  }, [clip.type, clip.compId, clip.name, dispatch]);

  // Cursor based on tool
  const getCursor = useCallback(
    (localX: number): string => {
      if (selectedTool === "razor") return "crosshair";
      if (selectedTool === "slip") return "ew-resize";
      if (selectedTool === "hand") return "grab";
      if (localX <= EDGE_TOLERANCE || localX >= width - EDGE_TOLERANCE)
        return "ew-resize";
      return "grab";
    },
    [selectedTool, width],
  );

  // Mouse down
  const onMouseDown = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (e.button !== 0) return;
      if (track.locked) return;
      e.preventDefault();
      e.stopPropagation();

      const rect = e.currentTarget.getBoundingClientRect();
      const localX = e.clientX - rect.left;

      if (selectedTool === "razor") {
        const splitFrame = Math.max(
          0,
          Math.round(clip.startFrame + localX / zoomX),
        );
        splitClip(clip.id, splitFrame).then((result) => {
          if (!result) return;
          fetchTimeline().then((data) => {
            if (data)
              dispatch({
                type: "SET_TRACKS",
                tracks: mapBackendTracksPreservingOrder(
                  state.tracks,
                  data.tracks ?? [],
                ),
              });
          });
        });
        return;
      }

      // Selection — ctrl/shift+click toggles individual clips  
      const isMulti = e.ctrlKey || e.shiftKey || e.metaKey;
      if (isMulti && clip.isSelected) {
        // ctrl+click on already-selected clip → deselect it
        dispatch({ type: "DESELECT_CLIP", clipId: clip.id });
      } else {
        dispatch({
          type: "SELECT_CLIP",
          clipId: clip.id,
          trackId: track.id,
          multi: isMulti,
        });
      }
      // Update InspectorPanel
      setSelected({
        type: 'clip',
        clipId: clip.id,
        clipName: clip.name,
        clipType: clip.type,
        trackIndex,
      });

      let mode: InteractionMode = "move";
      if (selectedTool === "slip") {
        mode = "slip";
      } else if (localX <= EDGE_TOLERANCE) {
        mode = "trimLeft";
      } else if (localX >= width - EDGE_TOLERANCE) {
        mode = "trimRight";
      }

      dispatch({
        type: "START_INTERACTION",
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
      if (mode === "move") {
        const rect = clipRef.current?.getBoundingClientRect();
        dispatch({
          type: "SET_GHOST",
          ghost: {
            clip,
            x: rect?.left ?? e.clientX,
            y: rect?.top ?? e.clientY,
            width: rect?.width ?? width,
            height: rect?.height ?? trackHeight - 10,
          },
        });
      }

      // mouse handlers
      _trimLastX = 0;
      _trimAccum = 0;
      let _trimTotalFrames = 0;

      const onMouseMove = (ev: MouseEvent) => {
        const dx = ev.clientX - e.clientX;

        if (mode === "move") {
          const frameDelta = Math.round(dx / zoomX);
          const trackDelta = Math.round((ev.clientY - e.clientY) / trackHeight);
          dispatch({
            type: "UPDATE_INTERACTION",
            pendingFrameDelta: frameDelta,
            pendingTrackDelta: trackDelta,
            accumPx: 0,
          });

          // Move ghost
          const rect = clipRef.current?.getBoundingClientRect();
          const ghostX = (rect?.left ?? e.clientX) + dx;
          const ghostY = (rect?.top ?? e.clientY) + (ev.clientY - e.clientY);
          dispatch({
            type: "SET_GHOST",
            ghost: {
              clip,
              x: ghostX,
              y: ghostY,
              width: rect?.width ?? width,
              height: rect?.height ?? trackHeight - 10,
            },
          });
        } else if (mode === "trimLeft" || mode === "trimRight") {
          const pixelStep = ev.clientX - e.clientX - _trimLastX;
          _trimLastX = ev.clientX - e.clientX;
          _trimAccum += pixelStep;
          const frameDelta = Math.round(_trimAccum / zoomX);
          if (frameDelta !== 0) {
            _trimAccum -= frameDelta * zoomX;
            _trimTotalFrames += frameDelta;
            dispatch({
              type: "TRIM_CLIP",
              clipId: clip.id,
              trackId: track.id,
              side: mode === "trimLeft" ? "left" : "right",
              frameDelta,
            });
          }
        } else if (mode === "slip") {
          const pixelStep = ev.clientX - e.clientX - _trimLastX;
          _trimLastX = ev.clientX - e.clientX;
          _trimAccum += pixelStep;
          const frameDelta = Math.round(_trimAccum / zoomX);
          if (frameDelta !== 0) {
            _trimAccum -= frameDelta * zoomX;
            _trimTotalFrames += frameDelta;
            dispatch({
              type: "TRIM_CLIP",
              clipId: clip.id,
              trackId: track.id,
              side: "left",
              frameDelta,
            });
          }
        }
      };

      const onMouseUp = (ev: MouseEvent) => {
        if (mode === "move") {
          dispatch({ type: "COMMIT_MOVE" });
          const dx = ev.clientX - e.clientX;
          const frameDelta = Math.round(dx / zoomX);
          const trackDelta = Math.round((ev.clientY - e.clientY) / trackHeight);
          const newStart = Math.max(0, clip.startFrame + frameDelta);
          const dstIdx = Math.max(0, trackIndex + trackDelta);

          moveClip(clip.id, newStart, dstIdx).then(() => {
            fetchTimeline().then((data) => {
              if (data)
                dispatch({
                  type: "SET_TRACKS",
                  tracks: mapBackendTracksPreservingOrder(
                    state.tracks,
                    data.tracks ?? [],
                  ),
                });
            });
          });
        } else {
          dispatch({ type: "END_INTERACTION" });
          if (
            _trimTotalFrames !== 0 &&
            (mode === "trimLeft" || mode === "trimRight" || mode === "slip")
          ) {
            const side = mode === "trimRight" ? "right" : "left";
            trimClip(clip.id, side, _trimTotalFrames).then(() => {
              fetchTimeline().then((data) => {
                if (data)
                  dispatch({
                    type: "SET_TRACKS",
                    tracks: (data.tracks ?? []).map((t: any) =>
                      mapBackendTrack(t),
                    ),
                  });
              });
            });
          }
        }
        window.removeEventListener("mousemove", onMouseMove);
        window.removeEventListener("mouseup", onMouseUp);
      };

      window.addEventListener("mousemove", onMouseMove);
      window.addEventListener("mouseup", onMouseUp);
    },
    [
      clip,
      track,
      trackIndex,
      trackHeight,
      zoomX,
      selectedTool,
      width,
      dispatch,
    ],
  );

  // Effect drop support 
  const [effectDropOver, setEffectDropOver] = useState(false);

  const handleEffectDragOver = useCallback((e: React.DragEvent) => {
    if (e.dataTransfer.types.includes('application/fade-effect')) {
      e.preventDefault();
      e.stopPropagation();
      setEffectDropOver(true);
    }
  }, []);

  const handleEffectDragLeave = useCallback(() => setEffectDropOver(false), []);

  const handleEffectDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setEffectDropOver(false);
    const effectType = e.dataTransfer.getData('application/fade-effect');
    if (!effectType || !clip.id) return;
    try {
      await effectsApi.add(clip.id, effectType);
      // Select this clip so inspector shows the new effect
      dispatch({ type: 'SELECT_CLIP', clipId: clip.id, trackId: track.id, multi: false });
      setSelected({ type: 'clip', clipId: clip.id, clipName: clip.name, clipType: clip.type, trackIndex });
      window.dispatchEvent(new CustomEvent('fade:effects-changed', { detail: clip.id }));
    } catch (err) {
      console.error('[TimelineClip] effect drop failed', err);
    }
  }, [clip.id, clip.name, clip.type, track.id, trackIndex, dispatch, setSelected]);

  // Render
  const isSelected = clip.isSelected;
  const dimForGhost = isMeMoving;

  return (
    <>
    <div
      ref={clipRef}
      className={`tl-clip ${isSelected ? "tl-clip--selected" : ""} ${dimForGhost ? "tl-clip--ghost-dim" : ""} ${effectDropOver ? "tl-clip--effect-drop" : ""}`}
      style={{
        left: x,
        width,
        top: 5,
        height: trackHeight - 10,
        background: color,
        borderColor: isSelected ? lighten(color, 0.4) : lighten(color, 0.2),
      }}
      onMouseDown={onMouseDown}
      onDoubleClick={onDoubleClick}
      onContextMenu={onContextMenu}
      onMouseMove={(e) => {
        const localX = e.clientX - e.currentTarget.getBoundingClientRect().left;
        e.currentTarget.style.cursor = getCursor(localX);
      }}
      onDragOver={handleEffectDragOver}
      onDragLeave={handleEffectDragLeave}
      onDrop={handleEffectDrop}
      title={clip.name}
      role="button"
      aria-label={`Clip: ${clip.name}`}
    >
      <div className="tl-clip__trim tl-clip__trim--left" />
      <div className="tl-clip__trim tl-clip__trim--right" />

      {/* Waveform loading shimmer  */}
      {wantsWaveform && waveLoading && peaks.length === 0 && (
        <div style={{
          position: 'absolute', inset: 0, pointerEvents: 'none',
          background: 'linear-gradient(90deg, transparent 25%, rgba(255,255,255,0.08) 50%, transparent 75%)',
          backgroundSize: '200% 100%',
          animation: 'tl-wave-shimmer 1.4s ease-in-out infinite',
        }} />
      )}

      {/* Waveform canvas  */}
      {peaks.length > 0 && (
        <canvas
          ref={canvasRefCallback}
          style={{ position: 'absolute', inset: 0, pointerEvents: 'none', opacity: 0.65 }}
        />
      )}

      {effectDropOver && (
        <div className="tl-clip__effect-drop-hint">+ Drop Effect</div>
      )}

      <span className="tl-clip__label">
        {clip.type === 'comp' && <span style={{ marginRight: 4, opacity: 0.8 }}>⊞</span>}
        {clip.name}
      </span>
    </div>

    {/* Right-click context menu */}
    {ctxMenu && ReactDOM.createPortal(
      <div
        style={{
          position: 'fixed',
          left: ctxMenu.x,
          top: ctxMenu.y,
          zIndex: 9999,
          background: '#1e1e2e',
          border: '1px solid #333',
          borderRadius: 6,
          boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
          minWidth: 160,
          overflow: 'hidden',
          fontSize: 12,
        }}
        onMouseDown={e => e.stopPropagation()}
      >
        {clip.type === 'comp' && (
          <button
            style={CTX_ITEM_STYLE}
            onClick={() => { setCtxMenu(null); dispatch({ type: 'ENTER_COMP', compId: clip.compId!, compName: clip.name }); }}
          >⊞ Enter Composition</button>
        )}
        <button
          style={CTX_ITEM_STYLE}
          onClick={handleSplit}
        >✂ Split at Playhead</button>
        <div style={{ height: 1, background: '#333', margin: '2px 0' }} />
        <button
          style={{ ...CTX_ITEM_STYLE, color: '#ff5f5f' }}
          onClick={handleDelete}
        >🗑 Delete Clip</button>
      </div>,
      document.body
    )}
    </>
  );
});


// Helpers

const CTX_ITEM_STYLE: React.CSSProperties = {
  display: 'block',
  width: '100%',
  padding: '7px 14px',
  background: 'transparent',
  border: 'none',
  color: '#e0e0e0',
  textAlign: 'left',
  cursor: 'pointer',
  fontSize: 12,
  whiteSpace: 'nowrap',
};

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
