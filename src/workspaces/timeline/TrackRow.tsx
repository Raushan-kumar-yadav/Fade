import React, { memo, useCallback, useRef } from 'react';
import { useTimeline } from './TimelineContext';
import { type Track, MIN_TRACK_H, MAX_TRACK_H } from './types';
import TimelineClip from './TimelineClip';

interface Props {
  track: Track;
  trackIndex: number;
}

/**
 * TrackRow — One horizontal band in the timeline content area.
 * Contains all clips for that track plus a vertical resize handle.
 */
const TrackRow = memo(function TrackRow({ track, trackIndex }: Props) {
  const { dispatch } = useTimeline();

  const resizingRef = useRef(false);
  const startYRef   = useRef(0);
  const startHRef   = useRef(0);

  // ── Row-level click: clear selection when clicking empty space ────────────
  const onRowClick = useCallback((e: React.MouseEvent) => {
    // Only clear if the click was directly on the row (not on a clip)
    if ((e.target as HTMLElement).classList.contains('tl-track-row__bg')) {
      dispatch({ type: 'CLEAR_SELECTION' });
    }
  }, [dispatch]);

  // ── Bottom resize handle ──────────────────────────────────────────────────
  const onResizeMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    resizingRef.current = true;
    startYRef.current   = e.clientY;
    startHRef.current   = track.height;

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

  const isEven = trackIndex % 2 === 0;

  return (
    <div
      className={`tl-track-row ${isEven ? 'tl-track-row--even' : 'tl-track-row--odd'} ${track.locked ? 'tl-track-row--locked' : ''}`}
      style={{ height: track.height, position: 'relative' }}
      onClick={onRowClick}
      aria-label={`Track: ${track.name}`}
    >
      {/* Full-width transparent bg that acts as the click target */}
      <div className="tl-track-row__bg" style={{ position: 'absolute', inset: 0 }} />

      {/* Bottom separator */}
      <div className="tl-track-row__sep" />

      {/* Clips */}
      {track.clips.map(clip => (
        <TimelineClip
          key={clip.id}
          clip={clip}
          track={track}
          trackIndex={trackIndex}
          trackHeight={track.height}
        />
      ))}

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

export default TrackRow;
