import React, { memo, useCallback, useRef } from 'react';
import { useTimeline } from './TimelineContext';
import { type Track, HEADER_WIDTH, MIN_TRACK_H, MAX_TRACK_H } from './types';

interface Props {
  scrollTop: number;
  totalTrackHeightPx: number;
}

/**
 * TrackHeaders — Fixed left column.
 * Shows track name, M/S/L buttons, and a resize handle at the bottom.
 * Vertically synchronized with the scrollable content via CSS translateY.
 */
const TrackHeaders = memo(function TrackHeaders({ scrollTop, totalTrackHeightPx }: Props) {
  return (
    <div
      className="tl-headers"
      style={{ width: HEADER_WIDTH, overflow: 'hidden', height: '100%' }}
    >
      <div
        style={{
          transform: `translateY(-${scrollTop}px)`,
          height: totalTrackHeightPx,
        }}
      >
        {useTimeline().state.tracks.map((track, index) => (
          <TrackHeaderItem key={track.id} track={track} index={index} />
        ))}
      </div>
    </div>
  );
});

// ─── Individual track header ────────────────────────────────────────────────
interface ItemProps { track: Track; index: number }

const TrackHeaderItem = memo(function TrackHeaderItem({ track, index }: ItemProps) {
  const { dispatch } = useTimeline();
  const resizingRef = useRef(false);
  const startYRef  = useRef(0);
  const startHRef  = useRef(0);

  // ── Track resize handle ─────────────────────────────────────────────────
  const onResizeMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    resizingRef.current = true;
    startYRef.current  = e.clientY;
    startHRef.current  = track.height;

    const onMove = (ev: MouseEvent) => {
      if (!resizingRef.current) return;
      const proposed = Math.max(MIN_TRACK_H, Math.min(MAX_TRACK_H, startHRef.current + (ev.clientY - startYRef.current)));
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

  return (
    <div
      className="tl-header-item"
      style={{ height: track.height }}
      aria-label={`Track ${index + 1}: ${track.name}`}
    >
      {/* Track name */}
      <span
        className="tl-header-item__name"
        style={{ opacity: track.muted ? 0.35 : 1 }}
      >
        {track.name}
      </span>

      {/* M / S / L buttons */}
      <div className="tl-header-item__controls">
        <button
          className={`tl-btn-msb ${track.muted ? 'tl-btn-msb--muted' : ''}`}
          title="Mute"
          id={`track-mute-${track.id}`}
          onClick={() => dispatch({ type: 'TOGGLE_MUTE', trackId: track.id })}
        >
          M
        </button>
        <button
          className={`tl-btn-msb ${track.solo ? 'tl-btn-msb--solo' : ''}`}
          title="Solo"
          id={`track-solo-${track.id}`}
          onClick={() => dispatch({ type: 'TOGGLE_SOLO', trackId: track.id })}
        >
          S
        </button>
        <button
          className={`tl-btn-msb ${track.locked ? 'tl-btn-msb--locked' : ''}`}
          title="Lock"
          id={`track-lock-${track.id}`}
          onClick={() => dispatch({ type: 'TOGGLE_LOCK', trackId: track.id })}
        >
          L
        </button>
      </div>

      {/* Resize handle */}
      <div
        className="tl-header-item__resize"
        onMouseDown={onResizeMouseDown}
        title="Drag to resize track"
        aria-label="Resize track"
      />
    </div>
  );
});

export default TrackHeaders;
