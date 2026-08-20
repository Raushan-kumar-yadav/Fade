import type { TimelineState } from './types';

/** Format a frame number as MM:SS:FF timecode */
export function frameToTimecode(frame: number, fps: number): string {
  const totalSec = Math.floor(frame / fps);
  const ff = Math.floor(frame % fps);
  const mm = Math.floor(totalSec / 60);
  const ss = totalSec % 60;
  return `${String(mm).padStart(2,'0')}:${String(ss).padStart(2,'0')}:${String(ff).padStart(2,'0')}`;
}

export function totalWidth(state: TimelineState): number {
  return Math.max(state.totalFrames * state.zoomX, 2000);
}

export function totalTrackHeight(state: TimelineState): number {
  return state.tracks.reduce((h, t) => h + t.height, 0);
}
