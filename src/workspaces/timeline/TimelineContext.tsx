import React, {
  createContext,
  useContext,
  useReducer,
  useEffect,
  type Dispatch,
  type ReactNode,
} from "react";
import {
  type TimelineState,
  type TimelineAction,
  type Track,
  type Clip,
  MIN_ZOOM,
  MAX_ZOOM,
  MIN_TRACK_H,
  MAX_TRACK_H,
} from "./types";
import { setTrackMute, setTrackSolo, setTrackLock } from "../../api/useApi";

// ── Empty initial state — filled by backend on mount ─────────────────────────
const INITIAL_STATE: TimelineState = {
  tracks: [],
  currentFrame: 0,
  totalFrames: 1800,
  fps: 30,
  zoomX: 5,
  selectedTool: "pointer",
  isPlaying: false,
  interaction: null,
  ghost: null,
};

//   Helpers

export function mapBackendTrack(t: any, defaultHeight = 64): Track {
  const isAudio = t.type === "audio" || t.name?.toLowerCase().includes("audio");
  return {
    id: t.trackId ?? t.id,
    name: t.name,
    height: isAudio ? 48 : defaultHeight,
    muted: t.muted ?? false,
    solo: t.solo ?? false,
    locked: t.locked ?? false,
    clips: (t.clips ?? []).map(mapBackendClip),
  };
}

export function mapBackendTracksPreservingOrder(
  currentTracks: Track[],
  backendTracks: any[],
): Track[] {
  const mappedById = new Map(
    backendTracks.map((track) => {
      const mapped = mapBackendTrack(track);
      return [mapped.id, mapped] as const;
    }),
  );
  const ordered = currentTracks
    .map((track) => mappedById.get(track.id))
    .filter((track): track is Track => Boolean(track));
  const currentIds = new Set(currentTracks.map((track) => track.id));
  return ordered.concat(
    backendTracks
      .map(mapBackendTrack)
      .filter((track) => !currentIds.has(track.id)),
  );
}

function mapBackendClip(c: any): Clip {
  const type: Clip["type"] =
    c.type === "audio"
      ? "audio"
      : c.type === "image"
        ? "image"
        : c.type === "text"
          ? "text"
          : c.type === "solid"
            ? "solid"
            : c.type === "shape"
              ? "shape"
              : c.type === "lottie"
                ? "lottie"
                : "video";

  return {
    id: c.clipId ?? c.id,
    name: c.name ?? c.assetId ?? "Clip",
    startFrame: c.startFrame,
    duration: c.duration,
    type,
    isSelected: false,
  };
}

//   Reducer
function reducer(state: TimelineState, action: TimelineAction): TimelineState {
  switch (action.type) {
    //   Backend sync
    case "SET_TRACKS":
      return { ...state, tracks: action.tracks };

    case "SET_TOTAL_FRAMES":
      return { ...state, totalFrames: action.totalFrames };

    case "ADD_CLIP": {
      const tracks = state.tracks.map((t) => {
        if (t.id !== action.trackId) return t;
        // Swap optimistic tmp- clip with real one, or just append
        const hasTmp = t.clips.some(
          (c) => c.id.startsWith("tmp-") && c.name === action.clip.name,
        );
        const clips = hasTmp
          ? t.clips.map((c) =>
              c.id.startsWith("tmp-") && c.name === action.clip.name
                ? action.clip
                : c,
            )
          : [...t.clips, action.clip].sort(
              (a, b) => a.startFrame - b.startFrame,
            );
        return { ...t, clips };
      });
      return { ...state, tracks };
    }

    //   Playback
    case "SEEK":
      return {
        ...state,
        currentFrame: Math.max(0, Math.min(action.frame, state.totalFrames)),
      };

    case "TICK":
      return {
        ...state,
        currentFrame: Math.min(action.frame, state.totalFrames),
      };

    case "TOGGLE_PLAY":
      return { ...state, isPlaying: !state.isPlaying };

    case "SET_PLAYING":
      return { ...state, isPlaying: action.playing };

    case "SET_CURRENT_FRAME":
      return {
        ...state,
        currentFrame: Math.max(0, Math.min(action.frame, state.totalFrames)),
      };

    //   View
    case "ZOOM_X":
      return {
        ...state,
        zoomX: Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, action.newZoom)),
      };

    case "SET_TOOL":
      return { ...state, selectedTool: action.tool };

    //   Selection
    case "SELECT_CLIP": {
      const tracks = state.tracks.map((track) => ({
        ...track,
        clips: track.clips.map((clip) => ({
          ...clip,
          isSelected:
            clip.id === action.clipId && track.id === action.trackId
              ? true
              : action.multi
                ? clip.isSelected
                : false,
        })),
      }));
      return { ...state, tracks };
    }

    case "CLEAR_SELECTION": {
      const tracks = state.tracks.map((t) => ({
        ...t,
        clips: t.clips.map((c) => ({ ...c, isSelected: false })),
      }));
      return { ...state, tracks };
    }

    case "DELETE_CLIP": {
      const tracks = state.tracks.map((t) => ({
        ...t,
        clips: t.clips.filter((c) => c.id !== action.clipId),
      }));
      return { ...state, tracks };
    }

    case "SPLIT_CLIP_DONE": {
      // Replace the original clip (now shorter) and append the right half
      const { originalClip, rightClip, trackId } = action;
      const tracks = state.tracks.map((t) => {
        if (t.id !== trackId) return t;
        const clips = t.clips
          .filter((c) => c.id !== originalClip.id)
          .concat([originalClip, rightClip])
          .sort((a, b) => a.startFrame - b.startFrame);
        return { ...t, clips };
      });
      return { ...state, tracks };
    }

    //   Move
    case "COMMIT_MOVE": {
      const intr = state.interaction;
      if (!intr || intr.mode !== "move")
        return { ...state, interaction: null, ghost: null };

      const { pendingFrameDelta, pendingTrackDelta } = intr;
      const selected: Array<{ clip: Clip; srcIdx: number }> = [];
      state.tracks.forEach((t, ti) => {
        t.clips.forEach((c) => {
          if (c.isSelected) selected.push({ clip: c, srcIdx: ti });
        });
      });

      let newTracks = state.tracks.map((t) => ({
        ...t,
        clips: t.clips.filter((c) => !c.isSelected),
      }));

      selected.forEach(({ clip, srcIdx }) => {
        const dstIdx = Math.max(
          0,
          Math.min(newTracks.length - 1, srcIdx + pendingTrackDelta),
        );
        const newStart = Math.max(0, clip.startFrame + pendingFrameDelta);
        newTracks[dstIdx] = {
          ...newTracks[dstIdx],
          clips: [
            ...newTracks[dstIdx].clips,
            { ...clip, startFrame: newStart },
          ],
        };
      });

      newTracks = newTracks.map((t) => ({
        ...t,
        clips: [...t.clips].sort((a, b) => a.startFrame - b.startFrame),
      }));

      return { ...state, tracks: newTracks, interaction: null, ghost: null };
    }

    //   Trim
    case "TRIM_CLIP": {
      const { clipId, trackId, side, frameDelta } = action;
      const tracks = state.tracks.map((track) => {
        if (track.id !== trackId) return track;
        return {
          ...track,
          clips: track.clips.map((clip) => {
            if (clip.id !== clipId) return clip;
            if (side === "left") {
              const newStart = Math.max(0, clip.startFrame + frameDelta);
              const newDuration = clip.duration - (newStart - clip.startFrame);
              return newDuration < 1
                ? clip
                : { ...clip, startFrame: newStart, duration: newDuration };
            }
            const newDuration = Math.max(1, clip.duration + frameDelta);
            return { ...clip, duration: newDuration };
          }),
        };
      });
      return { ...state, tracks };
    }

    //   Track controls
    case "TOGGLE_MUTE":
      setTrackMute(action.trackId).catch(() => {});
      return {
        ...state,
        tracks: state.tracks.map((t) =>
          t.id === action.trackId ? { ...t, muted: !t.muted } : t,
        ),
      };

    case "TOGGLE_SOLO":
      setTrackSolo(action.trackId).catch(() => {});
      return {
        ...state,
        tracks: state.tracks.map((t) =>
          t.id === action.trackId
            ? { ...t, solo: !t.solo }
            : { ...t, solo: false },
        ),
      };

    case "TOGGLE_LOCK":
      setTrackLock(action.trackId).catch(() => {});
      return {
        ...state,
        tracks: state.tracks.map((t) =>
          t.id === action.trackId ? { ...t, locked: !t.locked } : t,
        ),
      };

    case "RESIZE_TRACK":
      return {
        ...state,
        tracks: state.tracks.map((t) =>
          t.id === action.trackId
            ? {
                ...t,
                height: Math.max(
                  MIN_TRACK_H,
                  Math.min(MAX_TRACK_H, action.height),
                ),
              }
            : t,
        ),
      };

    //   Drag interaction
    case "START_INTERACTION":
      return { ...state, interaction: action.interaction };

    case "UPDATE_INTERACTION":
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

    case "SET_GHOST":
      return { ...state, ghost: action.ghost };

    case "END_INTERACTION":
      return { ...state, interaction: null, ghost: null };

    default:
      return state;
  }
}

//   Context
interface TimelineContextValue {
  state: TimelineState;
  dispatch: Dispatch<TimelineAction>;
}

const TimelineCtx = createContext<TimelineContextValue | null>(null);

//   Provider
export function TimelineProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);
  // Keep a ref so async callbacks can read latest tracks without stale closure
  const stateRef = React.useRef<TimelineState>(state);
  React.useEffect(() => { stateRef.current = state; }, [state]);

  useEffect(() => {
    // Hoist onFrame so cleanup can always reach it
    const onFrame = (e: Event) => {
      const frame = (e as CustomEvent<number>).detail;
      dispatch({ type: "SET_CURRENT_FRAME", frame });
    };
    window.addEventListener("fade:frame", onFrame);

    function fetchAndSetTracks(port: number, preserveOrder = false) {
      fetch(`http://127.0.0.1:${port}/timeline/state`)
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
          if (!data) return;
          const backendTracks = data.tracks ?? [];
          const tracks: Track[] = preserveOrder
            ? mapBackendTracksPreservingOrder(
                stateRef.current.tracks,
                backendTracks,
              )
            : backendTracks.map(mapBackendTrack);
          dispatch({ type: "SET_TRACKS", tracks });
          if (data.totalFrames)
            dispatch({ type: "SET_TOTAL_FRAMES", totalFrames: data.totalFrames });
        })
        .catch(() => {});
    }

    function startSync(port: number) {
      // ── Startup burst: poll /timeline/state rapidly for 2s ────────────
      // Necessary because the backend lifespan (which seeds tracks) runs
      // after FastAPI starts accepting connections — so the very first
      // fetch may return 0 tracks before lifespan finishes.
      let burstCount = 0;
      const BURST_INTERVAL = 200;  // ms between polls
      const BURST_DURATION = 2000; // ms total burst window
      const burstId = setInterval(() => {
        fetchAndSetTracks(port, false);
        burstCount++;
        if (burstCount * BURST_INTERVAL >= BURST_DURATION) {
          clearInterval(burstId);
        }
      }, BURST_INTERVAL);

      // ── Listen for track changes from viewport tools ───────────────────
      const onTracksChanged = () => fetchAndSetTracks(port, true);
      window.addEventListener("fade:tracks-changed", onTracksChanged);

      // ── Slow refresh: re-sync tracks every 2s (catches missed events) ──
      const trackRefreshId = setInterval(() => {
        fetchAndSetTracks(port, true);
      }, 2000);

      // ── Fast poll: playback state (play/pause + totalFrames) ──────────
      const playbackId = setInterval(() => {
        fetch(`http://127.0.0.1:${port}/playback/state`)
          .then((r) => (r.ok ? r.json() : null))
          .then((data) => {
            if (!data) return;
            dispatch({ type: "SET_PLAYING", playing: data.playing });
            if (data.totalFrames)
              dispatch({ type: "SET_TOTAL_FRAMES", totalFrames: data.totalFrames });
          })
          .catch(() => {});
      }, 500);

      return () => {
        clearInterval(burstId);
        clearInterval(trackRefreshId);
        clearInterval(playbackId);
        window.removeEventListener("fade:tracks-changed", onTracksChanged);
      };
    }

    let cleanupSync: (() => void) | null = null;

    const knownPort: number | null = (window as any).__FADE_PORT__;
    if (knownPort) {
      cleanupSync = startSync(knownPort);
    } else {
      const handler = (e: Event) => {
        cleanupSync = startSync((e as CustomEvent<number>).detail);
      };
      window.addEventListener("fade:port", handler, { once: true });
    }

    return () => {
      if (cleanupSync) cleanupSync();
      window.removeEventListener("fade:frame", onFrame);
    };
  }, []);

  return (
    <TimelineCtx.Provider value={{ state, dispatch }}>
      {children}
    </TimelineCtx.Provider>
  );
}

// Hook
export function useTimeline(): TimelineContextValue {
  const ctx = useContext(TimelineCtx);
  if (!ctx)
    throw new Error("useTimeline must be used inside <TimelineProvider>");
  return ctx;
}

export { frameToTimecode, totalWidth, totalTrackHeight } from "./timelineUtils";
