//   Tool Types
export type ToolType = "pointer" | "razor" | "ripple" | "slip" | "hand";

//   Clip Types
export type ClipType =
  | "video"
  | "audio"
  | "text"
  | "solid"
  | "shape"
  | "lottie"
  | "image"
  | "comp"
  | "adjustment";

export const CLIP_COLORS: Record<ClipType, string> = {
  comp: "#7c4dff",
  text: "#e6a817",
  solid: "#00b8a9",
  shape: "#43a047",
  lottie: "#e91e8c",
  image: "#00bcd4",
  audio: "#546e7a",
  adjustment: "#ff6d00",
  video: "#4a90e2",
};

// Data Models
export interface Clip {
  id: string;
  name: string;
  startFrame: number;
  duration: number;
  type: ClipType;
  isSelected: boolean;
  assetId?: string;
}

export interface Track {
  id: string;
  name: string;
  height: number;
  muted: boolean;
  solo: boolean;
  locked: boolean;
  clips: Clip[];
}

// Interaction State
export type InteractionMode = "move" | "trimLeft" | "trimRight" | "slip";

export interface ClipInteraction {
  clipId: string;
  trackId: string;
  mode: InteractionMode;
  startMouseX: number;
  startMouseY: number;
  startClipFrame: number;
  startTrackIndex: number;
  pendingFrameDelta: number;
  pendingTrackDelta: number;
  accumPx: number;
}

// Ghost proxy rendered during move
export interface GhostInfo {
  clip: Clip;
  x: number; //   screen X
  y: number; //   screen Y
  width: number;
  height: number;
}

// Full Timeline State
export interface TimelineState {
  tracks: Track[];
  currentFrame: number;
  totalFrames: number;
  fps: number;
  zoomX: number;
  selectedTool: ToolType;
  isPlaying: boolean;
  interaction: ClipInteraction | null;
  ghost: GhostInfo | null;
}

// Reducer Actions
export type TimelineAction =
  | { type: "SEEK"; frame: number }
  | { type: "ZOOM_X"; newZoom: number }
  | { type: "SET_TOOL"; tool: ToolType }
  | { type: "TOGGLE_PLAY" }
  | { type: "SET_PLAYING"; playing: boolean }
  | { type: "SET_CURRENT_FRAME"; frame: number }
  | { type: "TICK"; frame: number }
  // Backend sync
  | { type: "SET_TRACKS"; tracks: Track[] }
  | { type: "SET_TOTAL_FRAMES"; totalFrames: number }
  | { type: "ADD_CLIP"; trackId: string; clip: Clip }
  | { type: "DELETE_CLIP"; clipId: string }
  | {
      type: "SPLIT_CLIP_DONE";
      trackId: string;
      originalClip: Clip;
      rightClip: Clip;
    }
  | { type: "SELECT_CLIP"; clipId: string; trackId: string; multi: boolean }
  | { type: "CLEAR_SELECTION" }
  | { type: "COMMIT_MOVE" }
  | {
      type: "TRIM_CLIP";
      clipId: string;
      trackId: string;
      side: "left" | "right";
      frameDelta: number;
    }
  | { type: "TOGGLE_MUTE"; trackId: string }
  | { type: "TOGGLE_SOLO"; trackId: string }
  | { type: "TOGGLE_LOCK"; trackId: string }
  | { type: "RESIZE_TRACK"; trackId: string; height: number }
  | { type: "START_INTERACTION"; interaction: ClipInteraction }
  | {
      type: "UPDATE_INTERACTION";
      pendingFrameDelta: number;
      pendingTrackDelta: number;
      accumPx: number;
    }
  | { type: "SET_GHOST"; ghost: GhostInfo | null }
  | { type: "END_INTERACTION" };

// Layout Constants
export const HEADER_WIDTH = 120;
export const RULER_HEIGHT = 28;
export const BOTTOM_BAR_H = 24;
export const EDGE_TOLERANCE = 8; // px — trim handle zone
export const MIN_ZOOM = 0.3;
export const MAX_ZOOM = 60;
export const MIN_TRACK_H = 40;
export const MAX_TRACK_H = 300;
