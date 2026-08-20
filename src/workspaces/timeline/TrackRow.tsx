import React, { memo, useCallback, useRef, useState } from 'react';
import { useTimeline } from './TimelineContext';
import { type Track, type Clip, HEADER_WIDTH, MIN_TRACK_H, MAX_TRACK_H } from './types';
import TimelineClip from './TimelineClip';
import { addClipToTimeline, type AssetItem } from '../../api/useApi';

interface Props {
  track:        Track;
  trackIndex:   number;
  scrollLeft?:  number;   // passed from Timeline so we can compute the drop frame
}

const TrackRow = memo(function TrackRow({ track, trackIndex, scrollLeft = 0 }: Props) {
  const { state, dispatch } = useTimeline();

  const resizingRef = useRef(false);
  const startYRef   = useRef(0);
  const startHRef   = useRef(0);

  // ── Drop-zone highlight state ──────────────────────────────────────────────
  const [dropOver, setDropOver] = useState(false);

  // ── Clear selection on empty-row click ────────────────────────────────────
  const onRowClick = useCallback((e: React.MouseEvent) => {
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

  // ── Drag-from-library: accept application/fade-asset ─────────────────────
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

    // Calculate which frame the user dropped onto
    // e.clientX is screen X; subtract the track-header width and add scrollLeft
    const rowRect  = (e.currentTarget as HTMLDivElement).getBoundingClientRect();
    const localX   = e.clientX - rowRect.left;          // px inside the track row
    const frame    = Math.max(0, Math.round((localX + scrollLeft) / state.zoomX));
    const duration = 150;   // default 5 s @ 30 fps

    // Optimistic update — add clip to local state immediately
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

    // Persist to backend — replace optimistic clip with real one on response
    const result = await addClipToTimeline(asset.assetId, trackIndex, frame, duration);
    if (result) {
      // Swap the tmp clip for the real clip from backend
      const realClip: Clip = {
        id:         result.clipId,
        name:       asset.filename,
        startFrame: result.startFrame,
        duration:   result.duration,
        type:       optimisticClip.type,
        isSelected: false,
      };
      // Remove optimistic, insert real
      dispatch({ type: 'ADD_CLIP', trackId: track.id, clip: realClip });
    }
  }, [track.id, trackIndex, scrollLeft, state.zoomX, dispatch]);

  const isEven = trackIndex % 2 === 0;

  return (
    <div
      className={[
        'tl-track-row',
        isEven         ? 'tl-track-row--even'   : 'tl-track-row--odd',
        track.locked   ? 'tl-track-row--locked'  : '',
        dropOver       ? 'tl-track-row--dropover' : '',
      ].join(' ')}
      style={{ height: track.height, position: 'relative' }}
      onClick={onRowClick}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      aria-label={`Track: ${track.name}`}
    >
      <div className="tl-track-row__bg" style={{ position: 'absolute', inset: 0 }} />

      {/* Row separator */}
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

      {/* Drop hint when dragging over */}
      {dropOver && (
        <div className="tl-track-row__drop-hint">
          Drop to add clip
        </div>
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

export default TrackRow;
