/**
 * useApi.ts
 * Thin typed wrapper around the Fade backend REST + WebSocket API.
 * All calls go to the port stored in window.__FADE_PORT__ (injected by Electron
 * preload) or fall back to 8000 for browser dev.
 */

function base(): string {
  const port = (window as any).__FADE_PORT__ ?? 8000;
  return `http://127.0.0.1:${port}`;
}

function wsBase(): string {
  const port = (window as any).__FADE_PORT__ ?? 8000;
  return `ws://127.0.0.1:${port}`;
}

// ── Types ──────────────────────────────────────────────────────────────────────

export interface AssetItem {
  assetId: string;
  filename: string;
  filepath: string;
  type: "video" | "image" | "audio" | "subtitle" | "unknown";
}

export interface PlaybackState {
  frame: number;
  playing: boolean;
  fps: number;
}

export interface ClipInfo {
  clipId: string;
  trackId: string;
  startFrame: number;
  duration: number;
  assetId: string;
  type: string;
}

//   Library

export async function fetchAssets(): Promise<AssetItem[]> {
  const r = await fetch(`${base()}/library/assets`);
  if (!r.ok) return [];
  return r.json();
}

export async function importAsset(filepath: string): Promise<AssetItem | null> {
  const r = await fetch(`${base()}/library/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filepath }),
  });
  if (!r.ok) return null;
  return r.json();
}

export async function removeAsset(assetId: string): Promise<void> {
  await fetch(`${base()}/library/assets/${assetId}`, { method: "DELETE" });
}

//   Timeline

export async function addClipToTimeline(
  assetId: string,
  trackIndex: number,
  startFrame: number,
  duration: number,
): Promise<{ clipId: string; startFrame: number; duration: number } | null> {
  try {
    const r = await fetch(`${base()}/timeline/add-clip`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ assetId, trackIndex, startFrame, duration }),
    });
    if (!r.ok) return null;
    return r.json();
  } catch {
    return null;
  }
}

export async function moveClip(
  clipId: string,
  startFrame: number,
  trackIndex: number,
): Promise<void> {
  await fetch(`${base()}/timeline/move-clip`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ clipId, startFrame, trackIndex }),
  });
}

export async function removeClip(clipId: string): Promise<void> {
  await fetch(`${base()}/timeline/clips/${clipId}`, { method: "DELETE" });
}

export async function trimClip(
  clipId: string,
  side: "left" | "right",
  frameDelta: number,
): Promise<{ clipId: string; startFrame: number; duration: number } | null> {
  try {
    const r = await fetch(`${base()}/timeline/trim-clip`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clipId, side, frameDelta }),
    });
    return r.ok ? r.json() : null;
  } catch {
    return null;
  }
}

export async function splitClip(
  clipId: string,
  frame: number,
): Promise<{
  leftClipId: string;
  rightClipId: string;
  splitFrame: number;
  trackId: string;
} | null> {
  try {
    const r = await fetch(`${base()}/timeline/split-clip`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clipId, frame }),
    });
    return r.ok ? r.json() : null;
  } catch {
    return null;
  }
}

export async function undoAction(): Promise<void> {
  await fetch(`${base()}/history/undo`, { method: "POST" });
}

export async function redoAction(): Promise<void> {
  await fetch(`${base()}/history/redo`, { method: "POST" });
}

export async function setTrackMute(trackId: string): Promise<void> {
  await fetch(`${base()}/timeline/track/${trackId}/mute`, { method: "POST" });
}

export async function setTrackSolo(trackId: string): Promise<void> {
  await fetch(`${base()}/timeline/track/${trackId}/solo`, { method: "POST" });
}

export async function setTrackLock(trackId: string): Promise<void> {
  await fetch(`${base()}/timeline/track/${trackId}/lock`, { method: "POST" });
}

// Re-fetch timeline state (used after undo/redo to sync UI)
export async function fetchTimeline(): Promise<any> {
  try {
    const r = await fetch(`${base()}/timeline/state`);
    return r.ok ? r.json() : null;
  } catch {
    return null;
  }
}

export async function playbackPlay(): Promise<void> {
  await fetch(`${base()}/playback/play`, { method: "POST" });
}

export async function playbackPause(): Promise<void> {
  await fetch(`${base()}/playback/pause`, { method: "POST" });
}

export async function playbackSeek(frame: number): Promise<void> {
  await fetch(`${base()}/playback/seek`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ frame }),
  });
}

export async function getPlaybackState(): Promise<PlaybackState> {
  const r = await fetch(`${base()}/playback/state`);
  return r.json();
}

// ── Viewport frame (single-frame scrub, not streaming) ────────────────────────

export function frameUrl(frame: number): string {
  return `${base()}/frame/${frame}`;
}

// ── WebSocket preview stream ──────────────────────────────────────────────────

export function openPreviewSocket(
  onFrame: (blob: Blob) => void,
  onClose?: () => void,
): WebSocket {
  const ws = new WebSocket(`${wsBase()}/ws/preview`);
  ws.binaryType = "blob";
  ws.onmessage = (e) => onFrame(e.data as Blob);
  ws.onclose = () => onClose?.();
  ws.onerror = (e) => console.error("[PreviewWS] error", e);
  return ws;
}

// ── Preview quality ───────────────────────────────────────────────────────────

/** Set decode resolution scale: 1.0=full, 0.5=half, 0.25=quarter, 0.125=eighth */
export async function setPreviewScale(scale: number): Promise<void> {
  await fetch(`${base()}/preview/scale`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scale }),
  });
}

/** Set playback speed: 0.25, 0.5, 1.0, 2.0 */
export async function setPlaybackSpeed(speed: number): Promise<void> {
  await fetch(`${base()}/playback/speed`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ speed }),
  });
}

/** Set in/out loop points. Pass null to clear. */
export async function setPlaybackInOut(
  inPoint: number | null,
  outPoint: number | null,
): Promise<void> {
  await fetch(`${base()}/playback/inout`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ inPoint, outPoint }),
  });
}
