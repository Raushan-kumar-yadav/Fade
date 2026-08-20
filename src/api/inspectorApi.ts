/** inspectorApi.ts — typed client for Inspector param + keyframe routes */

function port(): number { return (window as any).__FADE_PORT__ ?? 8000; }
const base = () => `http://127.0.0.1:${port()}`;

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${base()}${path}`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${base()}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
async function del(path: string): Promise<void> {
  await fetch(`${base()}${path}`, { method: 'DELETE' });
}

// ── Types ──────────────────────────────────────────────────────────────────

export type InterpMode = 'constant' | 'linear' | 'bezier' | 'ease_in' | 'ease_out' | 'ease_both';

export interface ParamRow {
  id:          string;
  label:       string;
  type:        'float' | 'int';
  min:         number;
  max:         number;
  default:     number;
  group:       string;
  value:       number;
  isAnimated:  boolean;
  hasKeyframe: boolean;
  keyframes:   number[];   // frame numbers that have keyframes
}

export interface ClipParams {
  clipId:     string;
  clipType:   string;
  startFrame: number;
  duration:   number;
  params:     ParamRow[];
}

export interface KFDef {
  frame:        number;
  value:        number;
  interp:       InterpMode;
  handle_in_f:  number;
  handle_in_v:  number;
  handle_out_f: number;
  handle_out_v: number;
}

// ── API calls ─────────────────────────────────────────────────────────────

export const inspectorApi = {
  getParams: (clipId: string, frame: number): Promise<ClipParams> =>
    get(`/clips/${clipId}/params?frame=${frame}`),

  setParam: (clipId: string, key: string, value: number, frame = -1) =>
    post(`/clips/${clipId}/params/${key}`, { value, frame }),

  addKeyframe: (clipId: string, key: string, kf: KFDef) =>
    post(`/clips/${clipId}/keyframes/${key}`, kf),

  listKeyframes: (clipId: string, key: string) =>
    get<{ frames: KFDef[]; allFrames: number[] }>(`/clips/${clipId}/keyframes/${key}`),

  removeKeyframe: (clipId: string, key: string, frame: number) =>
    del(`/clips/${clipId}/keyframes/${key}/${frame}`),
};
