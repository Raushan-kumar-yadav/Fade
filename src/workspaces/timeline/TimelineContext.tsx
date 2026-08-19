import React, {
  createContext, useContext, useReducer,
  type Dispatch, type ReactNode,
} from 'react';
import {
  type TimelineState, type TimelineAction, type Track, type Clip,
  MIN_ZOOM, MAX_ZOOM, MIN_TRACK_H, MAX_TRACK_H,
} from './types';

// ─── Demo Data ────────────────────────────────────────────────────────────────
const DEMO_TRACKS: Track[] = [
  {
    id: 'v1', name: 'Video 1', height: 64,
    muted: false, solo: false, locked: false,
    clips: [
      { id: 'v1c1', name: 'Clip_001.mp4', startFrame: 0,   duration: 114, type: 'video', isSelected: false },
      { id: 'v1c2', name: 'Clip_002.mp4', startFrame: 129, duration: 84,  type: 'video', isSelected: false },
    ],
  },
  {
    id: 'a1', name: 'Audio 1', height: 52,
    muted: false, solo: false, locked: false,
    clips: [
      { id: 'a1c1', name: 'Music_bg.mp3', startFrame: 0, duration: 360, type: 'audio', isSelected: false },
    ],
  },
  {
    id: 'fx1', name: 'FX', height: 52,
    muted: false, solo: false, locked: false,
    clips: [
      { id: 'fx1c1', name: 'Blur Out',    startFrame: 24,  duration: 42, type: 'adjustment', isSelected: false },
      { id: 'fx1c2', name: 'Color Grade', startFrame: 156, duration: 30, type: 'adjustment', isSelected: false },
    ],
  },
  {
    id: 't1', name: 'Text', height: 52,
    muted: false, solo: false, locked: false,
    clips: [
      { id: 't1c1', name: 'Title Card', startFrame: 12, duration: 54, type: 'text', isSelected: false },
    ],
  },
];

const INITIAL_STATE: TimelineState = {
  tracks: DEMO_TRACKS,
  currentFrame: 0,
  totalFrames: 1800,   // 60 s @ 30 fps
  fps: 30,
  zoomX: 5,            // 5 px / frame
  selectedTool: 'pointer',
  isPlaying: false,
  interaction: null,
  ghost: null,
};

// ─── Reducer ──────────────────────────────────────────────────────────────────
function reducer(state: TimelineState, action: TimelineAction): TimelineState {
  switch (action.type) {
    // ── Playback ──────────────────────────────────────────────────────────
    case 'SEEK':
      return { ...state, currentFrame: Math.max(0, Math.min(action.frame, state.totalFrames)) };

    case 'TICK':
      return { ...state, currentFrame: Math.min(action.frame, state.totalFrames) };

    case 'TOGGLE_PLAY':
      return { ...state, isPlaying: !state.isPlaying };

    case 'SET_PLAYING':
      return { ...state, isPlaying: action.playing };

    // ── View ──────────────────────────────────────────────────────────────
    case 'ZOOM_X':
      return { ...state, zoomX: Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, action.newZoom)) };

    case 'SET_TOOL':
      return { ...state, selectedTool: action.tool };

    // ── Selection ─────────────────────────────────────────────────────────
    case 'SELECT_CLIP': {
      const tracks = state.tracks.map(track => ({
        ...track,
        clips: track.clips.map(clip => ({
          ...clip,
          isSelected: clip.id === action.clipId && track.id === action.trackId
            ? true
            : action.multi ? clip.isSelected : false,
        })),
      }));
      return { ...state, tracks };
    }

    case 'CLEAR_SELECTION': {
      const tracks = state.tracks.map(t => ({
        ...t,
        clips: t.clips.map(c => ({ ...c, isSelected: false })),
      }));
      return { ...state, tracks };
    }

    // ── Move (deferred — committed on mouse up) ───────────────────────────
    case 'COMMIT_MOVE': {
      const intr = state.interaction;
      if (!intr || intr.mode !== 'move') return { ...state, interaction: null, ghost: null };

      const { pendingFrameDelta, pendingTrackDelta } = intr;

      // Collect all selected clips with their source track index
      const selected: Array<{ clip: Clip; srcIdx: number }> = [];
      state.tracks.forEach((t, ti) => {
        t.clips.forEach(c => {
          if (c.isSelected) selected.push({ clip: c, srcIdx: ti });
        });
      });

      // Remove selected clips from all tracks
      let newTracks = state.tracks.map(t => ({
        ...t,
        clips: t.clips.filter(c => !c.isSelected),
      }));

      // Re-insert at new positions
      selected.forEach(({ clip, srcIdx }) => {
        const dstIdx = Math.max(0, Math.min(newTracks.length - 1, srcIdx + pendingTrackDelta));
        const newStart = Math.max(0, clip.startFrame + pendingFrameDelta);
        newTracks[dstIdx] = {
          ...newTracks[dstIdx],
          clips: [...newTracks[dstIdx].clips, { ...clip, startFrame: newStart }],
        };
      });

      // Sort clips in each track by start frame
      newTracks = newTracks.map(t => ({
        ...t,
        clips: [...t.clips].sort((a, b) => a.startFrame - b.startFrame),
      }));

      return { ...state, tracks: newTracks, interaction: null, ghost: null };
    }

    // ── Trim (live — applied immediately) ────────────────────────────────
    case 'TRIM_CLIP': {
      const { clipId, trackId, side, frameDelta } = action;
      const tracks = state.tracks.map(track => {
        if (track.id !== trackId) return track;
        return {
          ...track,
          clips: track.clips.map(clip => {
            if (clip.id !== clipId) return clip;
            if (side === 'left') {
              const newStart = Math.max(0, clip.startFrame + frameDelta);
              const newDuration = clip.duration - (newStart - clip.startFrame);
              return newDuration < 1 ? clip : { ...clip, startFrame: newStart, duration: newDuration };
            }
            const newDuration = Math.max(1, clip.duration + frameDelta);
            return { ...clip, duration: newDuration };
          }),
        };
      });
      return { ...state, tracks };
    }

    // ── Track controls ────────────────────────────────────────────────────
    case 'TOGGLE_MUTE':
      return { ...state, tracks: state.tracks.map(t => t.id === action.trackId ? { ...t, muted: !t.muted } : t) };

    case 'TOGGLE_SOLO':
      return { ...state, tracks: state.tracks.map(t => t.id === action.trackId ? { ...t, solo: !t.solo } : t) };

    case 'TOGGLE_LOCK':
      return { ...state, tracks: state.tracks.map(t => t.id === action.trackId ? { ...t, locked: !t.locked } : t) };

    case 'RESIZE_TRACK':
      return {
        ...state,
        tracks: state.tracks.map(t =>
          t.id === action.trackId
            ? { ...t, height: Math.max(MIN_TRACK_H, Math.min(MAX_TRACK_H, action.height)) }
            : t
        ),
      };

    // ── Drag interaction ──────────────────────────────────────────────────
    case 'START_INTERACTION':
      return { ...state, interaction: action.interaction };

    case 'UPDATE_INTERACTION':
      if (!state.interaction) return state;
      return {
        ...state,
        interaction: {
          ...state.interaction,
          pendingFrameDelta: action.pendingFrameDelta,
          pendingTrackDelta: action.pendingTrackDelta,
          accumPx: action.accumPx,
        },
      };

    case 'SET_GHOST':
      return { ...state, ghost: action.ghost };

    case 'END_INTERACTION':
      return { ...state, interaction: null, ghost: null };

    default:
      return state;
  }
}

// ─── Context ──────────────────────────────────────────────────────────────────
interface TimelineContextValue {
  state: TimelineState;
  dispatch: Dispatch<TimelineAction>;
}

const TimelineCtx = createContext<TimelineContextValue | null>(null);

export function TimelineProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);
  return (
    <TimelineCtx.Provider value={{ state, dispatch }}>
      {children}
    </TimelineCtx.Provider>
  );
}

/** Hook — throws if used outside <TimelineProvider> */
export function useTimeline(): TimelineContextValue {
  const ctx = useContext(TimelineCtx);
  if (!ctx) throw new Error('useTimeline must be used inside <TimelineProvider>');
  return ctx;
}

/** Derive the total content width in pixels */
export function totalWidth(state: TimelineState): number {
  return Math.max(state.totalFrames * state.zoomX, 2000);
}

/** Derive total track-content height in pixels */
export function totalTrackHeight(state: TimelineState): number {
  return state.tracks.reduce((h, t) => h + t.height, 0);
}

/** Convert frame number → MM:SS:FF string (30 fps) */
export function frameToTimecode(frame: number, fps: number): string {
  const totalSec = Math.floor(frame / fps);
  const ff = Math.floor(frame % fps);
  const mm = Math.floor(totalSec / 60);
  const ss = totalSec % 60;
  return `${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}:${String(ff).padStart(2, '0')}`;
}
