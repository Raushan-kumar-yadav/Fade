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
  type: 'video' | 'image' | 'audio' | 'subtitle' | 'unknown';
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

// ── Library (Assets) ──────────────────────────────────────────────────────────

export async function fetchAssets(): Promise<AssetItem[]> {
  const r = await fetch(`${base()}/library/assets`);
  if (!r.ok) return [];
  return r.json();
}

export async function importAsset(filepath: string): Promise<AssetItem | null> {
  const r = await fetch(`${base()}/library/import`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filepath }),
  });
  if (!r.ok) return null;
  return r.json();
}

export async function removeAsset(assetId: string): Promise<void> {
  await fetch(`${base()}/library/assets/${assetId}`, { method: 'DELETE' });
}

// ── Timeline ──────────────────────────────────────────────────────────────────

export async function addClipToTimeline(
  assetId: string,
  trackIndex: number,
  startFrame: number,
  duration: number,
): Promise<ClipInfo | null> {
  const r = await fetch(`${base()}/timeline/add-clip`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ assetId, trackIndex, startFrame, duration }),
  });
  if (!r.ok) return null;
  return r.json();
}

export async function moveClip(
  clipId: string,
  startFrame: number,
  trackIndex: number,
): Promise<void> {
  await fetch(`${base()}/timeline/move-clip`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ clipId, startFrame, trackIndex }),
  });
}

export async function removeClip(clipId: string): Promise<void> {
  await fetch(`${base()}/timeline/clips/${clipId}`, { method: 'DELETE' });
}

// ── Playback ──────────────────────────────────────────────────────────────────

export async function playbackPlay(): Promise<void> {
  await fetch(`${base()}/playback/play`, { method: 'POST' });
}

export async function playbackPause(): Promise<void> {
  await fetch(`${base()}/playback/pause`, { method: 'POST' });
}

export async function playbackSeek(frame: number): Promise<void> {
  await fetch(`${base()}/playback/seek?frame=${frame}`, { method: 'POST' });
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
  onFrame: (jpeg: Blob) => void,
  onClose?: () => void,
): WebSocket {
  const ws = new WebSocket(`${wsBase()}/ws/preview`);
  ws.binaryType = 'blob';
  ws.onmessage  = (e) => onFrame(e.data as Blob);
  ws.onclose    = () => onClose?.();
  ws.onerror    = (e) => console.error('[PreviewWS] error', e);
  return ws;
}
