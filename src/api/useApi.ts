 

function base(): string {
  const port = (window as any).__FADE_PORT__ ?? 8000;
  return `http://127.0.0.1:${port}`;
}

function wsBase(): string {
  const port = (window as any).__FADE_PORT__ ?? 8000;
  return `ws://127.0.0.1:${port}`;
}

//   Types  

export interface AssetItem {
  assetId: string;
  filename: string;
  filepath: string;
  type: "video" | "image" | "audio" | "subtitle" | "unknown" | "svg";
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

export type ImportResult =
  | { ok: true;  asset: AssetItem }
  | { ok: false; filename: string; reason: string };

export async function importAsset(filepath: string): Promise<ImportResult> {
  const filename = filepath.split(/[\\/]/).pop() ?? filepath;
  const r = await fetch(`${base()}/library/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filepath }),
  });
  if (r.status === 422) {
    let reason = 'Blocked by security scanner';
    try { const d = await r.json(); reason = d.detail ?? reason; } catch {}
    return { ok: false, filename, reason };
  }
  if (!r.ok) return { ok: false, filename, reason: `Import failed (${r.status})` };
  const asset = await r.json();
  return { ok: true, asset };
}

export async function uploadAsset(file: File): Promise<ImportResult> {
  const filename = file.name;
  try {
    const formData = new FormData();
    formData.append('file', file, file.name);
    const r = await fetch(`${base()}/library/upload`, {
      method: 'POST',
      body: formData,
    });
    if (r.status === 422) {
      let reason = 'Blocked by security scanner';
      try { const d = await r.json(); reason = d.detail ?? reason; } catch {}
      return { ok: false, filename, reason };
    }
    if (!r.ok) return { ok: false, filename, reason: `Upload failed (${r.status})` };
    const asset = await r.json();
    return { ok: true, asset };
  } catch (err) {
    return { ok: false, filename, reason: String(err) };
  }
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
  mediaOffset = 0,
  compId?: string | null,
): Promise<{ clipId: string; startFrame: number; duration: number } | null> {
  try {
    const r = await fetch(`${base()}/timeline/add-clip`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ assetId, trackIndex, startFrame, duration, mediaOffset, compId: compId ?? null }),
    });
    if (!r.ok) return null;
    return r.json();
  } catch {
    return null;
  }
}

export async function addSvgClipToTimeline(
  filepath: string,
  trackIndex: number,
  startFrame: number,
  duration: number,
  displayW = 0,
  displayH = 0,
): Promise<{ clipId: string; startFrame: number; duration: number } | null> {
  try {
    const r = await fetch(`${base()}/timeline/add-svg-clip`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filepath, trackIndex, startFrame, duration, displayW, displayH }),
    });
    if (!r.ok) return null;
    return r.json();
  } catch {
    return null;
  }
}

export async function addCompClipToTimeline(
  compId: string,
  trackIndex: number,
  startFrame: number,
  duration: number,
): Promise<{ clipId: string; startFrame: number; duration: number } | null> {
  try {
    const r = await fetch(`${base()}/clips/comp`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ compId, trackIndex, startFrame, duration }),
    });
    if (!r.ok) return null;
    return r.json();
  } catch {
    return null;
  }
}

export async function addWebCompClipToTimeline(
  assetId: string,
  trackIndex: number,
  startFrame: number,
  duration: number,
): Promise<{ clipId: string; startFrame: number; duration: number } | null> {
  try {
    const r = await fetch(`${base()}/timeline/add-clip`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
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
  compId?: string | null,
): Promise<void> {
  await fetch(`${base()}/timeline/move-clip`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ clipId, startFrame, trackIndex, compId: compId ?? null }),
  });
}

export async function removeClip(clipId: string): Promise<void> {
  await fetch(`${base()}/timeline/clips/${clipId}`, { method: "DELETE" });
}

 
export async function moveImageLayer(
  compId: string,
  fromIndex: number,
  toIndex: number,
): Promise<void> {
  await fetch(`${base()}/comps/${compId}/layers/move`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fromIndex, toIndex }),
  });
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

export async function addTrack(
  type: "video" | "audio" = "video",
  name = "",
  compId?: string | null,
): Promise<{ trackId: string; name: string; type: string } | null> {
  try {
    const r = await fetch(`${base()}/timeline/add-track`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type, name, compId: compId ?? null }),
    });
    return r.ok ? r.json() : null;
  } catch {
    return null;
  }
}


export async function removeTrack(trackId: string): Promise<void> {
  await fetch(`${base()}/timeline/track/${trackId}`, { method: "DELETE" });
}

 
export async function fetchTimeline(): Promise<any> {
  try {
    const r = await fetch(`${base()}/timeline/state`);
    return r.ok ? r.json() : null;
  } catch {
    return null;
  }
}

// Re-fetch timeline state for a specific comp 
export async function fetchCompTimeline(compId: string): Promise<any> {
  try {
    const r = await fetch(`${base()}/timeline/comp/${compId}/state`);
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

//   Viewport frame  

export function frameUrl(frame: number): string {
  return `${base()}/frame/${frame}`;
}

//   WebSocket preview stream  

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

 

 
export async function setPreviewScale(scale: number): Promise<void> {
  await fetch(`${base()}/preview/scale`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scale }),
  });
}

/** Set playback speed  */
export async function setPlaybackSpeed(speed: number): Promise<void> {
  await fetch(`${base()}/playback/speed`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ speed }),
  });
}

/** Set in/out loop points  */
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
