 
function port(): number {
  return (window as any).__FADE_PORT__ ?? 8000;
}

const base = () => `http://127.0.0.1:${port()}`;

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${base()}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${base()}${path}`, {
    method:  'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function del(path: string): Promise<void> {
  await fetch(`${base()}${path}`, { method: 'DELETE' });
}

// Text  

export interface TextStyle {
  text?: string;
  fontFamily?: string;
  fontSize?: number;
  bold?: boolean;
  italic?: boolean;
  alignment?: 'left' | 'center' | 'right';
  lineHeight?: number;
  letterSpacing?:  number;
  maxWidth?: number;
  allCaps?: boolean;
  color?: [number, number, number, number];
  strokeColor?: [number, number, number, number];
  strokeWidth?: number;
  shadowEnabled?: boolean;
  shadowColor?: [number, number, number, number];
  shadowOffsetX?: number;
  shadowOffsetY?: number;
  shadowBlur?: number;
  bgEnabled?: boolean;
  bgColor?: [number, number, number, number];
  bgPaddingX?: number;
  bgPaddingY?: number;
  bgCornerRadius?: number;
}

export const textApi = {
  add:    (startFrame: number, duration: number, style: TextStyle = {}) =>
    post('/clips/text', { startFrame, duration, style }),
  update: (clipId: string, style: Partial<TextStyle>) =>
    patch(`/clips/text/${clipId}`, { style }),
};

//   Shape  

export type ShapeType =
  'rect' | 'circle' | 'ellipse' | 'star' | 'polygon' | 'line' | 'arc';

export interface ShapeStyle {
  shapeType?: ShapeType;
  width?: number;
  height?: number;
  cornerRadius?:   number;
  radiusX?: number;
  radiusY?: number;
  outerRadius?: number;
  innerRadius?: number;
  numPoints?: number;
  numSides?: number;
  polygonRadius?: number;
  x1?: number; y1?: number; x2?: number; y2?: number;
  arcStartAngle?: number;
  arcSweepAngle?: number;
  arcRadius?: number;
  fillColor?: [number, number, number, number];
  fillOpacity?: number;
  strokeColor?: [number, number, number, number];
  strokeWidth?: number;
  strokeStyle?: 'center' | 'inside' | 'outside';
  shadowEnabled?: boolean;
  shadowColor?: [number, number, number, number];
  shadowAngle?: number;
  shadowDistance?: number;
  shadowBlur?: number;
}

export const shapeApi = {
  add:    (startFrame: number, duration: number, style: ShapeStyle = {}, x = 960, y = 540) =>
    post('/clips/shape', { startFrame, duration, style, x, y }),
  update: (clipId: string, style: Partial<ShapeStyle>) =>
    patch(`/clips/shape/${clipId}`, { style }),
};

//   Pen  

export interface BezierPoint {
  x: number; y: number;
  inX: number; inY: number;
  outX: number; outY: number;
}

export const penApi = {
  add: (startFrame: number, duration: number,
        points: BezierPoint[] = [], isClosed = false, style: ShapeStyle = {}) =>
    post('/clips/pen', { startFrame, duration, points, isClosed, style }),
  updatePoints: (clipId: string, points: BezierPoint[], isClosed?: boolean) =>
    patch(`/clips/pen/${clipId}/points`, { points, isClosed }),
 
  addPathKeyframe: (clipId: string, frame: number, interp = 'bezier') =>
    post(`/clips/pen/${clipId}/path-keyframe`, { frame, interp }),
  removePathKeyframe: (clipId: string, frame: number) =>
    del(`/clips/pen/${clipId}/path-keyframe/${frame}`),
};

//   Mask  

export interface MaskRequest {
  name?: string;
  shape?: 'rect' | 'ellipse' | 'bezier';
  mode?: 'add' | 'subtract';
  inverted?: boolean;
  feather?: number;
  opacity?: number;
  points?: BezierPoint[];
}

export interface MaskInfo {
  maskId: string;
  name: string;
  shape: string;
  mode: string;
  inverted: boolean;
  feather: number;
  opacity: number;
  pointCount: number;
  points: BezierPoint[];   // full path  
}

export interface AddMaskResponse {
  clipId:  string;
  maskId:  string;
  masks:   MaskInfo[];
}

export const maskApi = {
  list: (clipId: string): Promise<{ masks: MaskInfo[] }> =>
    fetch(`${base()}/clips/${clipId}/masks`).then(r => r.json()),
  add: (clipId: string, req: MaskRequest = {}): Promise<AddMaskResponse> =>
    post(`/clips/${clipId}/mask`, req),
  update: (clipId: string, maskId: string, req: Partial<MaskRequest>) =>
    patch(`/clips/${clipId}/mask/${maskId}`, req),
  remove: (clipId: string, maskId: string) =>
    del(`/clips/${clipId}/mask/${maskId}`),
  /** Snapshot current mask path as an animation keyframe at `frame`. */
  addPathKeyframe: (clipId: string, maskId: string, frame: number, interp = 'bezier') =>
    post(`/clips/${clipId}/mask/${maskId}/path-keyframe`, { frame, interp }),
  removePathKeyframe: (clipId: string, maskId: string, frame: number) =>
    del(`/clips/${clipId}/mask/${maskId}/path-keyframe/${frame}`),
};

//   Effects

export interface EffectParamDef {
  value: number | number[];
  min: number | number[];
  max: number | number[];
  type: 'FloatSlider' | 'Vec2Input' | 'Vec4Input' | 'ToggleBool' | 'IntSlider';
  displayName: string;
}

export interface EffectInfo {
  effectId: string;
  name: string;
  type: string;
  enabled:  boolean;
  params: Record<string, EffectParamDef>;
  paramTypes?: 'typed';
}

export const effectsApi = {
  list:   (clipId: string): Promise<{ effects: EffectInfo[] }> =>
    fetch(`${base()}/clips/${clipId}/effects`).then(r => r.json()),
  add:    (clipId: string, effectType: string): Promise<EffectInfo> =>
    post(`/clips/${clipId}/effects`, { effectType }),
  patch:  (clipId: string, effectId: string, body: { enabled?: boolean; params?: Record<string, number | number[]> }) =>
    patch(`/clips/${clipId}/effects/${effectId}`, body),
  remove: (clipId: string, effectId: string) =>
    del(`/clips/${clipId}/effects/${effectId}`),
};

//   Export

export interface ExportSettings {
  outputPath: string;
  width?: number;
  height?: number;
  fps?: number;
  codec?: string;
  videoBitrate?: string;
  crf?: number;      // -1 = bitrate mode; 18-51 = CRF mode
  preset?: string;     // ultrafast → veryslow
  audioBitrate?: string;
  audioSampleRate?: number;
  audioChannels?:   number;
  formatId?: string;
  transparentBg?:   boolean;
}

export interface ExportProgress {
  jobId: string;
  frame:   number;
  total: number;
  percent: number;
  done: boolean;
  error: string | null;
  path: string | null;
  status?: string;  // 'video' | 'audio' | undefined — used to show mux phase label
}

export const exportApi = {
  start:    (settings: ExportSettings): Promise<{ jobId: string; total: number }> =>
    post('/export/start', settings),
  progress: (jobId: string): Promise<ExportProgress> =>
    fetch(`${base()}/export/progress/${jobId}`).then(r => r.json()),
  cancel:   (jobId: string) =>
    post(`/export/cancel/${jobId}`, {}),
};

//   Waveform

async function _pollWaveform(
  assetId: string,
  bins: number,
  attempts = 0,
): Promise<{ peaks: number[]; bins: number }> {
  const r = await fetch(`${base()}/assets/${assetId}/waveform?bins=${bins}`);
  if (r.ok || r.status === 202) {
    const d = await r.json();
    if (d.status === 'done') return { peaks: d.peaks, bins: d.bins };
    // pending — retry with exponential backoff, up to ~60s total
    if (attempts > 20) throw new Error('waveform timeout');
    const delay = Math.min(300 * Math.pow(1.5, attempts), 6000);
    await new Promise(res => setTimeout(res, delay));
    return _pollWaveform(assetId, bins, attempts + 1);
  }
  throw new Error(`waveform error ${r.status}`);
}

export const waveformApi = {
  /** Polls until waveform is ready, then resolves with peaks array. */
  get: (assetId: string, bins = 200) => _pollWaveform(assetId, bins),
};

//   Fonts  

export async function listFonts(): Promise<string[]> {
  try {
    const r = await fetch(`${base()}/fonts`);
    const d = await r.json();
    return d.fonts ?? [];
  } catch {
    return ['Arial', 'Times New Roman', 'Verdana'];
  }
}

//   Transitions  

export interface TransitionCatalogParam {
  id: string;
  displayName: string;
  type: string;
  default: number;
  min: number;
  max: number;
}

export interface TransitionCatalogEntry {
  typeId: string;
  name: string;
  icon: string;
  category: string;
  desc: string;
  params: TransitionCatalogParam[];
}

export interface TransitionInfo {
  transId: string;
  typeId: string;
  duration: number;   // frames
  clipA_id: string;
  clipB_id: string;
  values: Record<string, number>;
}

export const transitionApi = {
  catalog: (): Promise<{ transitions: TransitionCatalogEntry[] }> =>
    fetch(`${base()}/transitions/catalog`).then(r => r.json()),

  list: (trackId: string): Promise<{ transitions: TransitionInfo[] }> =>
    fetch(`${base()}/tracks/${trackId}/transitions`).then(r => r.json()),

  listAll: (): Promise<{ transitions: TransitionInfo[] }> =>
    fetch(`${base()}/timeline/transitions`).then(r => r.json()),

  add: (req: {
    typeId:   string;
    duration: number;
    clipA_id: string;
    clipB_id: string;
    trackId?:  string;
  }): Promise<TransitionInfo> =>
    post('/transitions', req),

  patch: (transId: string, req: {
    duration?: number;
    typeId?:   string;
    params?:   Record<string, number>;
  }): Promise<TransitionInfo> =>
    patch(`/transitions/${transId}`, req),

  remove: (transId: string): Promise<void> =>
    del(`/transitions/${transId}`),
};
