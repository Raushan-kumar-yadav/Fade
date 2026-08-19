import React, { useEffect, useRef, useState, useCallback } from 'react';
import { TimelineProvider, useTimeline, totalWidth, totalTrackHeight } from './TimelineContext';
import { HEADER_WIDTH, RULER_HEIGHT, BOTTOM_BAR_H, CLIP_COLORS } from './types';
import TimelineRuler   from './TimelineRuler';
import TrackHeaders    from './TrackHeaders';
import TrackRow        from './TrackRow';
import Playhead        from './Playhead';
import BottomBar       from './BottomBar';
import './timeline.css';

// ─── Ghost clip — floats at fixed screen position during move ─────────────────
function GhostClip() {
  const { state } = useTimeline();
  const { ghost } = state;
  if (!ghost) return null;

  const color = CLIP_COLORS[ghost.clip.type];
  return (
    <div
      className="tl-ghost-clip"
      style={{
        left:   ghost.x,
        top:    ghost.y,
        width:  ghost.width,
        height: ghost.height,
        background: color,
        borderColor: color,
      }}
    >
      <span className="tl-clip__label">{ghost.clip.name}</span>
    </div>
  );
}

// ─── Toolbar ──────────────────────────────────────────────────────────────────
const TOOLS = [
  { id: 'pointer' as const, icon: '↖', title: 'Pointer (V)' },
  { id: 'razor'   as const, icon: '✂', title: 'Razor (C)'   },
  { id: 'ripple'  as const, icon: '⟨⟩',title: 'Ripple (R)'  },
  { id: 'slip'    as const, icon: '⇄', title: 'Slip (Y)'    },
  { id: 'hand'    as const, icon: '✋', title: 'Hand (H)'    },
];

function Toolbar() {
  const { state, dispatch } = useTimeline();
  return (
    <div className="tl-toolbar">
      {TOOLS.map(t => (
        <button
          key={t.id}
          id={`tl-tool-${t.id}`}
          className={`tl-toolbar__btn ${state.selectedTool === t.id ? 'tl-toolbar__btn--active' : ''}`}
          title={t.title}
          onClick={() => dispatch({ type: 'SET_TOOL', tool: t.id })}
        >
          {t.icon}
        </button>
      ))}

      <div className="tl-toolbar__sep" />

      {/* Play / Pause */}
      <button
        id="tl-play-pause"
        className="tl-toolbar__btn tl-toolbar__btn--play"
        title={state.isPlaying ? 'Pause (Space)' : 'Play (Space)'}
        onClick={() => dispatch({ type: 'TOGGLE_PLAY' })}
      >
        {state.isPlaying ? '⏸' : '▶'}
      </button>

      {/* Timecode display */}
      <span className="tl-toolbar__timecode" aria-label="Current timecode">
        {formatTimecode(state.currentFrame, state.fps)}
      </span>
    </div>
  );
}

function formatTimecode(frame: number, fps: number) {
  const f  = Math.floor(frame);
  const mm = Math.floor(f / (fps * 60));
  const ss = Math.floor((f / fps) % 60);
  const ff = f % fps;
  return `${String(mm).padStart(2,'0')}:${String(ss).padStart(2,'0')}:${String(ff).padStart(2,'0')}`;
}

// ─── Inner timeline (needs context) ──────────────────────────────────────────
function TimelineInner() {
  const { state, dispatch } = useTimeline();

  const contentRef = useRef<HTMLDivElement>(null);
  const [scrollLeft, setScrollLeft] = useState(0);
  const [scrollTop,  setScrollTop]  = useState(0);
  const [viewWidth,  setViewWidth]  = useState(800);

  const tw = totalWidth(state);
  const th = totalTrackHeight(state);

  // ── Measure content area width ─────────────────────────────────────────
  useEffect(() => {
    const el = contentRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setViewWidth(el.clientWidth));
    ro.observe(el);
    setViewWidth(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  // ── Sync scroll state ──────────────────────────────────────────────────
  const onContentScroll = useCallback(() => {
    const el = contentRef.current;
    if (!el) return;
    setScrollLeft(el.scrollLeft);
    setScrollTop(el.scrollTop);
  }, []);

  // ── Wheel: zoom X (Ctrl) | zoom Y (Shift) | horizontal pan (Alt) | vertical scroll ──
  useEffect(() => {
    const el = contentRef.current;
    if (!el) return;
    const handler = (e: WheelEvent) => {
      e.preventDefault();
      if (e.ctrlKey || e.metaKey) {
        // Zoom X at cursor
        const rect      = el.getBoundingClientRect();
        const cursorPx  = e.clientX - rect.left + el.scrollLeft;
        const pivotFrame = cursorPx / state.zoomX;
        const factor     = e.deltaY < 0 ? 1.12 : 1 / 1.12;
        const newZoom    = Math.max(0.3, Math.min(60, state.zoomX * factor));
        dispatch({ type: 'ZOOM_X', newZoom });
        // Adjust scroll to keep pivot frame stationary
        requestAnimationFrame(() => {
          if (el) el.scrollLeft = pivotFrame * newZoom - (e.clientX - rect.left);
        });
      } else if (e.shiftKey) {
        el.scrollLeft += e.deltaY;
      } else {
        el.scrollTop  += e.deltaY;
        el.scrollLeft += e.deltaX;
      }
    };
    el.addEventListener('wheel', handler, { passive: false });
    return () => el.removeEventListener('wheel', handler);
  }, [state.zoomX, dispatch]);

  // ── Keyboard shortcuts ─────────────────────────────────────────────────
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).matches('input,textarea')) return;
      switch (e.code) {
        case 'Space': e.preventDefault(); dispatch({ type: 'TOGGLE_PLAY' }); break;
        case 'KeyV':  dispatch({ type: 'SET_TOOL', tool: 'pointer' }); break;
        case 'KeyC':  dispatch({ type: 'SET_TOOL', tool: 'razor'   }); break;
        case 'KeyR':  dispatch({ type: 'SET_TOOL', tool: 'ripple'  }); break;
        case 'KeyY':  dispatch({ type: 'SET_TOOL', tool: 'slip'    }); break;
        case 'KeyH':  dispatch({ type: 'SET_TOOL', tool: 'hand'    }); break;
        case 'Escape': dispatch({ type: 'CLEAR_SELECTION' }); break;
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [dispatch]);

  // ── Playback tick ──────────────────────────────────────────────────────
  const rafRef = useRef<number | undefined>(undefined);
  const lastTimeRef = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (!state.isPlaying) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      lastTimeRef.current = undefined;
      return;
    }
    const tick = (now: number) => {
      const delta = lastTimeRef.current ? (now - lastTimeRef.current) / 1000 : 0;
      lastTimeRef.current = now;
      const nextFrame = state.currentFrame + delta * state.fps;
      if (nextFrame >= state.totalFrames) {
        dispatch({ type: 'SEEK', frame: 0 });
        dispatch({ type: 'SET_PLAYING', playing: false });
      } else {
        dispatch({ type: 'TICK', frame: nextFrame });
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, [state.isPlaying, state.currentFrame, state.fps, state.totalFrames, dispatch]);

  // ── Seek on ruler click ────────────────────────────────────────────────
  const onSeek = useCallback((frame: number) => {
    dispatch({ type: 'SEEK', frame });
  }, [dispatch]);

  return (
    <div className="tl-root" aria-label="Video Timeline">

      {/* ── Toolbar ─────────────────────────────────────────────────────── */}
      <div className="tl-toolbar-row" style={{ gridColumn: '1 / -1', gridRow: '1' }}>
        <Toolbar />
      </div>

      {/* ── Corner ──────────────────────────────────────────────────────── */}
      <div className="tl-corner" style={{ gridColumn: '1', gridRow: '2' }} />

      {/* ── Ruler ───────────────────────────────────────────────────────── */}
      <div className="tl-ruler-container" style={{ gridColumn: '2', gridRow: '2' }}>
        <TimelineRuler
          scrollLeft={scrollLeft}
          totalWidthPx={tw}
          onSeek={onSeek}
        />
      </div>

      {/* ── Track Headers ───────────────────────────────────────────────── */}
      <div className="tl-headers-container" style={{ gridColumn: '1', gridRow: '3' }}>
        <TrackHeaders scrollTop={scrollTop} totalTrackHeightPx={th} />
      </div>

      {/* ── Track Content ───────────────────────────────────────────────── */}
      <div
        ref={contentRef}
        className="tl-content"
        style={{ gridColumn: '2', gridRow: '3' }}
        onScroll={onContentScroll}
      >
        {/* Expanded canvas */}
        <div style={{ width: tw, minHeight: th, position: 'relative' }}>
          {state.tracks.map((track, idx) => (
            <TrackRow key={track.id} track={track} trackIndex={idx} />
          ))}
        </div>
      </div>

      {/* ── Bottom Bar ──────────────────────────────────────────────────── */}
      <div className="tl-bottom-bar-container" style={{ gridColumn: '1 / -1', gridRow: '4' }}>
        <BottomBar contentRef={contentRef} viewWidth={viewWidth} />
      </div>

      {/* ── Playhead (absolute over entire grid) ────────────────────────── */}
      <Playhead scrollLeft={scrollLeft} contentLeft={HEADER_WIDTH} />

      {/* ── Ghost clip proxy during move ────────────────────────────────── */}
      <GhostClip />
    </div>
  );
}

// ─── Public export — wraps with provider ─────────────────────────────────────
export default function Timeline() {
  return (
    <TimelineProvider>
      <TimelineInner />
    </TimelineProvider>
  );
}
