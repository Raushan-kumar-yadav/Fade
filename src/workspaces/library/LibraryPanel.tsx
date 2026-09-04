import React, {
  useState, useEffect, useCallback, useRef, useLayoutEffect,
} from 'react';
import ReactDOM from 'react-dom';
import { fetchAssets, importAsset, removeAsset, addClipToTimeline, type AssetItem } from '../../api/useApi';
import { useTimeline } from '../timeline/TimelineContext';
import './LibraryPanel.css';

//   Types  

interface CompMeta {
  compId: string; name: string; isRoot: boolean;
  width: number; height: number; fps: number;
  totalFrames: number; trackCount: number; clipCount: number;
}
interface CompConfig {
  name: string; width: number; height: number; fps: number; totalFrames: number;
}
interface WebCompMeta {
  assetId: string; name: string; folderPath: string;
  width: number; height: number; fps: number; durationFrames: number;
}
interface CtxMenu { x: number; y: number; items: CtxItem[]; }
interface CtxItem {
  icon: string; label: string; danger?: boolean; sep?: boolean; onClick: () => void;
}
interface MediaJob {
  jobId: string;
  type: 'video_download' | 'image_download' | 'image_generate'
       | 'video_index' | 'image_index' | 'transcription' | string;
  label: string;
  status: 'pending' | 'running' | 'done' | 'error';
  progress: number;
  message: string;
  assetIds: string[];   // for download/generate jobs — the resulting assetIds
  assetId?: string | null;  // for asset-bound jobs — the specific asset being processed
  error?: string | null;
}

//   Constants  

const PRESETS = [
  { label: '1080p', w: 1920, h: 1080 }, { label: '4K',    w: 3840, h: 2160 },
  { label: '720p',  w: 1280, h: 720  }, { label: 'Square',w: 1080, h: 1080 },
  { label: '9:16',  w: 1080, h: 1920 }, { label: '4:3',   w: 1440, h: 1080 },
];
const FPS_OPTIONS = [23.976, 24, 25, 29.97, 30, 50, 59.94, 60];
function base() { return `http://127.0.0.1:${(window as any).__FADE_PORT__ ?? 8000}`; }

//   Type thumbnails

const THUMB_BG: Record<string, string> = {
  video: 'linear-gradient(135deg,#1a2a4a 0%,#0d1926 100%)',
  image: 'linear-gradient(135deg,#1a3a2a 0%,#0d2018 100%)',
  audio: 'linear-gradient(135deg,#2a1a3a 0%,#180d26 100%)',
  svg: 'linear-gradient(135deg,#1a3a3a 0%,#0d2222 100%)',
  comp: 'linear-gradient(135deg,#0d2e2e 0%,#051a1a 100%)',
  webcomp: 'linear-gradient(135deg,#1a1040 0%,#0a0628 100%)',
  unknown:'linear-gradient(135deg,#2a2a2a 0%,#111 100%)',
};

function CardThumb({ type }: { type: string }) {
  const t = type.toLowerCase();
  const bg = THUMB_BG[t] ?? THUMB_BG.unknown;

  let icon: React.ReactNode;
  switch (t) {
    case 'video':
      icon = (
        <svg viewBox="0 0 48 48" width={22} height={22} fill="none">
          <rect x="4" y="10" width="30" height="28" rx="3" fill="none" stroke="#4d9fff" strokeWidth="2.5"/>
          <polygon points="34,24 44,18 44,30" fill="#4d9fff"/>
          <circle cx="19" cy="24" r="5" fill="#4d9fff" opacity="0.35"/>
          <polygon points="17,21 17,27 23,24" fill="#4d9fff"/>
        </svg>
      );
      break;
    case 'image':
      icon = (
        <svg viewBox="0 0 48 48" width={22} height={22} fill="none">
          <rect x="6" y="8" width="36" height="32" rx="3" fill="none" stroke="#43a047" strokeWidth="2.5"/>
          <circle cx="16" cy="18" r="4" fill="#43a047" opacity="0.6"/>
          <path d="M6 34 L16 22 L24 30 L32 20 L42 34Z" fill="#43a047" opacity="0.4"/>
        </svg>
      );
      break;
    case 'audio':
      icon = (
        <svg viewBox="0 0 48 48" width={22} height={22} fill="none">
          <path d="M10 30 Q18 14 24 24 Q30 34 36 18 Q40 10 44 24" stroke="#9c27b0" strokeWidth="2.5" fill="none" strokeLinecap="round"/>
          <line x1="4"  y1="24" x2="4"  y2="24" stroke="#9c27b0" strokeWidth="2.5" strokeLinecap="round"/>
          <line x1="8"  y1="20" x2="8"  y2="28" stroke="#9c27b0" strokeWidth="2.5" strokeLinecap="round"/>
          <line x1="40" y1="18" x2="40" y2="30" stroke="#9c27b0" strokeWidth="2.5" strokeLinecap="round"/>
          <line x1="44" y1="21" x2="44" y2="27" stroke="#9c27b0" strokeWidth="2.5" strokeLinecap="round"/>
        </svg>
      );
      break;
    case 'svg':
      icon = (
        <svg viewBox="0 0 48 48" width={22} height={22} fill="none">
          <polygon points="24,6 42,40 6,40" fill="none" stroke="#0dcfb4" strokeWidth="2.5"/>
          <text x="24" y="34" textAnchor="middle" fontSize="9" fill="#0dcfb4" fontFamily="monospace">SVG</text>
        </svg>
      );
      break;
    case 'comp':
      icon = (
        <svg viewBox="0 0 48 48" width={22} height={22} fill="none">
          <rect x="6" y="6"   width="16" height="16" rx="2" fill="#0dcfb4" opacity="0.5"/>
          <rect x="26" y="6"  width="16" height="16" rx="2" fill="#0dcfb4" opacity="0.35"/>
          <rect x="6" y="26"  width="16" height="16" rx="2" fill="#0dcfb4" opacity="0.35"/>
          <rect x="26" y="26" width="16" height="16" rx="2" fill="#0dcfb4" opacity="0.2"/>
          <path d="M22 14 L26 14M14 22 L14 26M34 22 L34 26M26 34 L22 34"
            stroke="#0dcfb4" strokeWidth="1.5" strokeLinecap="round"/>
        </svg>
      );
      break;
    case 'webcomp':
      icon = (
        <svg viewBox="0 0 48 48" width={22} height={22} fill="none">
          <rect x="4" y="4" width="18" height="18" rx="3" fill="#a78bfa" opacity="0.8"/>
          <rect x="26" y="4" width="18" height="18" rx="3" fill="#a78bfa" opacity="0.5"/>
          <rect x="4" y="26" width="18" height="18" rx="3" fill="#a78bfa" opacity="0.5"/>
          <rect x="26" y="26" width="18" height="18" rx="3" fill="#a78bfa" opacity="0.3"/>
          <text x="24" y="30" textAnchor="middle" fontSize="10" fill="#a78bfa" fontFamily="monospace" opacity="0.9">⌨</text>
        </svg>
      );
      break;
    default:
      icon = (
        <svg viewBox="0 0 48 48" width={22} height={22} fill="none">
          <rect x="10" y="6" width="28" height="36" rx="3" fill="none" stroke="#888" strokeWidth="2"/>
          <line x1="16" y1="18" x2="32" y2="18" stroke="#888" strokeWidth="1.5"/>
          <line x1="16" y1="24" x2="32" y2="24" stroke="#888" strokeWidth="1.5"/>
          <line x1="16" y1="30" x2="26" y2="30" stroke="#888" strokeWidth="1.5"/>
        </svg>
      );
  }

  return (
    <div className="lib-card__thumb" style={{ background: bg }}>
      {icon}
    </div>
  );
}

//   API helpers  
 
function PlaceholderCard({ job, onDismiss }: { job: MediaJob; onDismiss: () => void }) {
  const isError = job.status === 'error';
  const isDone  = job.status === 'done';
  const icon = job.type === 'video_download' ? '🎬'
              : job.type === 'image_download' ? '🖼'
              : '✨';
  const pct = Math.round(job.progress * 100);

  if (isDone) return null; 

  return (
    <div className={`lib-placeholder-card lib-placeholder-card--${job.status}`}>
      {/* Full card overlay while loading */}
      <div className="lib-placeholder-card__overlay">
        {isError ? (
          <span className="lib-placeholder-card__err">⚠</span>
        ) : (
          <span className="lib-placeholder-card__spinner" />
        )}
      </div>

      {/* Icon + label */}
      <div className="lib-placeholder-card__body">
        <span className="lib-placeholder-card__type-icon">{icon}</span>
        <span className="lib-placeholder-card__label">{job.label}</span>
        {!isError && (
          <span className="lib-placeholder-card__msg">{job.message}</span>
        )}
        {isError && (
          <span className="lib-placeholder-card__msg lib-placeholder-card__msg--err">
            {job.error ?? 'Failed'}
          </span>
        )}
      </div>

      {/* Progress bar at bottom */}
      {!isError && (
        <div className="lib-placeholder-card__bar">
          <div className="lib-placeholder-card__bar-fill" style={{ width: `${pct}%` }} />
        </div>
      )}

      {/* Dismiss on error */}
      {isError && (
        <button className="lib-placeholder-card__dismiss" onClick={onDismiss} title="Dismiss">✕</button>
      )}
    </div>
  );
}

 
function AssetTaskOverlay({
  jobs,
  indexStatus,   
  assetType,
  assetId,
  onCancelIndex,
}: {
  jobs: MediaJob[];
  indexStatus?: string;  // 'pending' | 'running' | 'done' | 'not_found' | 'unknown'
  assetType?: string;
  assetId?: string;
  onCancelIndex?: () => void;
}) {
  const active = jobs.filter(j => j.status === 'running' || j.status === 'pending');
  const done   = jobs.filter(j => j.status === 'done');
  const error  = jobs.filter(j => j.status === 'error');

  // If no SSE job exists but the poll says indexing is active, synthesize an overlay
  const pollActive = (indexStatus === 'pending' || indexStatus === 'running') && active.length === 0;

  if (active.length === 0 && done.length === 0 && error.length === 0 && !pollActive) return null;

  const getIcon = (type: string) =>
    type === 'transcription' ? '💬'
    : type === 'video_index' || type === 'image_index' ? '🔍'
    : '⚙️';

  /** Fire the cancel request and let the parent dismiss the overlay */
  const handleStop = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!assetId) return;
    try {
      await fetch(`${base()}/library/cancel-index/${assetId}`, { method: 'POST' });
    } catch { /* non-fatal */ }
    onCancelIndex?.();
  };

  const isIndexJob = (type: string) =>
    type === 'video_index' || type === 'image_index';

  if (pollActive) {
    // Overlay driven purely by poll status  
    const icon = assetType === 'image' ? '🔍' : '🔍';
    const msg  = assetType === 'image' ? 'Describing image…' : 'Indexing: Vision + Whisper…';
    return (
      <div className="lib-asset-overlay lib-asset-overlay--active">
        <span className="lib-asset-overlay__icon">{icon}</span>
        <span className="lib-asset-overlay__text">{msg}</span>
        <span className="lib-asset-overlay__spin" />
        {assetId && (
          <button
            className="lib-asset-overlay__stop"
            onClick={handleStop}
            title="Stop indexing"
            aria-label="Stop indexing"
          >
            ✕
          </button>
        )}
      </div>
    );
  }

  // Pick the most interesting job to show 
  const show = active[0] ?? error[0] ?? done[0];
  const isActive = active.length > 0;
  const isErr    = !isActive && error.length > 0;
  // Only show stop button for index-type active jobs (not transcription)
  const canStop = isActive && assetId && isIndexJob(show.type);

  return (
    <div className={`lib-asset-overlay lib-asset-overlay--${isActive ? 'active' : isErr ? 'error' : 'done'}`}>
      <span className="lib-asset-overlay__icon">{getIcon(show.type)}</span>
      <span className="lib-asset-overlay__text">
        {isActive ? show.message || show.label
         : isErr  ? '⚠ ' + (show.error ?? 'Failed')
         : '✓ Indexed'}
      </span>
      {isActive && <span className="lib-asset-overlay__spin" />}
      {canStop && (
        <button
          className="lib-asset-overlay__stop"
          onClick={handleStop}
          title="Stop indexing"
          aria-label="Stop indexing"
        >
          ✕
        </button>
      )}
    </div>
  );
}


async function fetchComps(): Promise<CompMeta[]> {
  const r = await fetch(`${base()}/comps`); return (await r.json()).comps ?? [];
}
async function apiCreateComp(cfg: CompConfig): Promise<CompMeta> {
  const r = await fetch(`${base()}/comps`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: cfg.name, width: cfg.width, height: cfg.height, fps: cfg.fps, totalFrames: cfg.totalFrames }),
  });
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail ?? 'Failed'); }
  return r.json();
}
async function apiDeleteComp(id: string) { await fetch(`${base()}/comps/${id}`, { method: 'DELETE' }); }
async function apiAddCompClip(compId: string, startFrame: number, duration: number) {
  const r = await fetch(`${base()}/clips/comp`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ compId, startFrame, duration }),
  });
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail ?? 'Failed'); }
  return r.json();
}
async function apiRenameComp(id: string, name: string) {
  await fetch(`${base()}/comps/${id}/rename`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
}

//   WebComp API helpers
async function fetchWebComps(): Promise<WebCompMeta[]> {
  try {
    const r = await fetch(`${base()}/timeline/webcomp/list`);
    if (!r.ok) return [];
    const d = await r.json();
    return d.webcomps ?? [];
  } catch { return []; }
}
async function apiCreateWebComp(name: string, template: string): Promise<WebCompMeta> {
  const r = await fetch(`${base()}/timeline/webcomp/create`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, template }),
  });
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail ?? 'Failed'); }
  return r.json();
}
async function apiAddWebCompClip(assetId: string, startFrame: number, duration: number) {
  const r = await fetch(`${base()}/timeline/add-clip`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ trackIndex: 0, startFrame, duration, assetId }),
  });
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail ?? 'Failed'); }
  return r.json();
}

//   WebComp Create Modal

//   Template icons by id  
const TEMPLATE_ICONS: Record<string, string> = {
  'blank': '◻',
  'lower-third': '▬',
  'kinetic-title': '⚡',
  'word-reveal': '✦',
  'neon-headline': '⬡',
  'cinematic-split': '◈',
};

const TEMPLATE_HINTS: Record<string, string> = {
  'blank': 'Empty transparent canvas',
  'lower-third': 'Animated slide-in name card',
  'kinetic-title': 'High-energy Bebas Neue reveal',
  'word-reveal': 'Staggered blur word animation',
  'neon-headline': 'Electric Orbitron glow flicker',
  'cinematic-split': 'Film-style split with light leak',
};

interface WcTemplate {
  id: string; name: string; description: string;
  width: number; height: number; fps: number;
  durationFrames: number; params: any[];
}

function WebCompCreateModal({ onSubmit, onCancel }: {
  onSubmit: (name: string, template: string) => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState('');
  const [template, setTemplate] = useState('blank');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');
  const [templates, setTemplates] = useState<WcTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const nameRef = useRef<HTMLInputElement>(null);

  // Auto-name from template selection
  const autoNamed = useRef(true);

  // Fetch template list from backend on mount
  useEffect(() => {
    fetch(`${base()}/timeline/webcomp/templates`)
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d?.templates?.length) {
          setTemplates(d.templates);
          const first = d.templates[0].id;
          setTemplate(first);
          if (autoNamed.current) setName(d.templates[0].name);
        } else {
          // Fallback static list
          setTemplates([
            { id: 'blank', name: 'Blank', description: '', width: 1920, height: 1080, fps: 30, durationFrames: 150, params: [] },
            { id: 'lower-third', name: 'Lower Third', description: '', width: 1920, height: 1080, fps: 30, durationFrames: 150, params: [] },
          ]);
        }
      })
      .catch(() => {
        setTemplates([
          { id: 'blank', name: 'Blank', description: '', width: 1920, height: 1080, fps: 30, durationFrames: 150, params: [] },
          { id: 'lower-third', name: 'Lower Third', description: '', width: 1920, height: 1080, fps: 30, durationFrames: 150, params: [] },
        ]);
      })
      .finally(() => { setLoading(false); setTimeout(() => nameRef.current?.select(), 80); });
  }, []);

  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onCancel(); };
    document.addEventListener('keydown', h, true);
    return () => document.removeEventListener('keydown', h, true);
  }, [onCancel]);

  const selectTemplate = (t: WcTemplate) => {
    setTemplate(t.id);
    if (autoNamed.current) setName(t.name);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setCreating(true); setError('');
    try { await onSubmit(name.trim(), template); }
    catch (err: any) { setError(err.message ?? 'Failed'); setCreating(false); }
  };

  return ReactDOM.createPortal(
    <div className="lib-modal-overlay" onClick={e => { if (e.target === e.currentTarget) onCancel(); }}>
      <form className="lib-modal" onSubmit={handleSubmit} style={{ width: 480, maxHeight: '80vh' }}>
        <div className="lib-modal__header">
          <span className="lib-modal__title" style={{ color: '#a78bfa' }}>⊞ New WebComp</span>
          <button type="button" className="lib-modal__close" onClick={onCancel}>✕</button>
        </div>
        <div className="lib-modal__body" style={{ overflowY: 'auto', maxHeight: 'calc(80vh - 120px)' }}>
          <label className="lib-comp-cfg__label">NAME</label>
          <input ref={nameRef} className="lib-comp-cfg__input" value={name}
            onChange={e => { setName(e.target.value); autoNamed.current = false; }}
            placeholder="WebComp name…" />

          <label className="lib-comp-cfg__label" style={{ marginTop: 16 }}>TEMPLATE</label>

          {loading ? (
            <div style={{ padding: '20px 0', textAlign: 'center', color: '#5a5a74', fontSize: 12 }}>
              Loading templates…
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 6 }}>
              {templates.map(t => {
                const active = template === t.id;
                const icon   = TEMPLATE_ICONS[t.id] ?? '◈';
                const hint   = TEMPLATE_HINTS[t.id] ?? t.description ?? '';
                return (
                  <label key={t.id} onClick={() => selectTemplate(t)}
                    style={{ display: 'flex', flexDirection: 'column', gap: 4, cursor: 'pointer',
                      padding: '10px 12px', borderRadius: 8,
                      border: `1px solid ${active ? '#a78bfa' : '#2a2a38'}`,
                      background: active ? 'rgba(167,139,250,0.1)' : 'rgba(255,255,255,0.02)',
                      transition: 'all 0.12s', position: 'relative' }}>
                    <input type="radio" name="template" value={t.id} checked={active}
                      onChange={() => selectTemplate(t)}
                      style={{ position: 'absolute', top: 10, right: 10, accentColor: '#a78bfa' }} />
                    {/* Icon + name */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                      <span style={{ fontSize: 18, opacity: 0.8 }}>{icon}</span>
                      <span style={{ fontSize: 12, color: '#e0e0ec', fontWeight: 600, lineHeight: 1.2 }}>{t.name}</span>
                    </div>
                    {/* Hint */}
                    <div style={{ fontSize: 10, color: '#5a5a74', lineHeight: 1.4, paddingLeft: 2 }}>{hint}</div>
                    {/* Meta pills */}
                    <div style={{ display: 'flex', gap: 4, marginTop: 2, flexWrap: 'wrap' }}>
                      {t.durationFrames > 0 && (
                        <span style={{ fontSize: 9, color: '#6b7280', background: 'rgba(255,255,255,0.05)',
                          borderRadius: 4, padding: '1px 5px' }}>{t.durationFrames}fr</span>
                      )}
                      {t.params.length > 0 && (
                        <span style={{ fontSize: 9, color: '#6b7280', background: 'rgba(255,255,255,0.05)',
                          borderRadius: 4, padding: '1px 5px' }}>{t.params.length} param{t.params.length > 1 ? 's' : ''}</span>
                      )}
                      {t.width && (
                        <span style={{ fontSize: 9, color: '#6b7280', background: 'rgba(255,255,255,0.05)',
                          borderRadius: 4, padding: '1px 5px' }}>{t.width}×{t.height}</span>
                      )}
                    </div>
                  </label>
                );
              })}
            </div>
          )}

          {error && <div className="lib-comp-cfg__error" style={{ marginTop: 10 }}>⚠ {error}</div>}
        </div>
        <div className="lib-modal__footer">
          <button type="button" className="lib-comp-cfg__btn lib-comp-cfg__btn--cancel" onClick={onCancel}>Cancel</button>
          <button type="submit" className="lib-comp-cfg__btn lib-comp-cfg__btn--create"
            style={{ background: '#7c3aed' }}
            disabled={creating || !name.trim() || loading}>
            {creating ? 'Creating…' : '✓ Create WebComp'}
          </button>
        </div>
      </form>
    </div>,
    document.body
  );
}


//   Context menu portal  


function ContextMenu({ menu, onClose }: { menu: CtxMenu; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ x: menu.x, y: menu.y });
  useLayoutEffect(() => {
    if (!ref.current) return;
    const { offsetWidth: w, offsetHeight: h } = ref.current;
    setPos({ x: menu.x + w > window.innerWidth ? menu.x - w : menu.x,
             y: menu.y + h > window.innerHeight ? menu.y - h : menu.y });
  }, [menu.x, menu.y]);
  useEffect(() => {
    const close = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) onClose(); };
    const esc   = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('mousedown', close, true);
    document.addEventListener('keydown',   esc,   true);
    return () => { document.removeEventListener('mousedown', close, true); document.removeEventListener('keydown', esc, true); };
  }, [onClose]);
  return ReactDOM.createPortal(
    <div ref={ref} className="lib-ctx" style={{ left: pos.x, top: pos.y }} onContextMenu={e => e.preventDefault()}>
      {menu.items.map((item, i) =>
        item.sep ? <div key={`s${i}`} className="lib-ctx__sep" /> : (
          <div key={i} className={`lib-ctx__item${item.danger ? ' lib-ctx__item--danger' : ''}`}
            onClick={() => { onClose(); item.onClick(); }}>
            <span className="lib-ctx__icon">{item.icon}</span>{item.label}
          </div>
        )
      )}
    </div>,
    document.body
  );
}

//   Comp Config Modal  

function CompConfigModal({ onSubmit, onCancel }: { onSubmit: (cfg: CompConfig) => void; onCancel: () => void }) {
  const [name, setName] = useState('New Composition');
  const [width, setWidth] = useState(1920);
  const [height, setHeight] = useState(1080);
  const [fps, setFps] = useState(30);
  const [totalFrames, setTotalFrames] = useState(900);
  const [creating, setCreating] = useState(false);
  const nameRef = useRef<HTMLInputElement>(null);

  useEffect(() => { nameRef.current?.select(); }, []);
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onCancel(); };
    document.addEventListener('keydown', h, true);
    return () => document.removeEventListener('keydown', h, true);
  }, [onCancel]);

  const applyPreset = (w: number, h: number) => { setWidth(w); setHeight(h); };
  const durationSec = (totalFrames / fps).toFixed(1);
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault(); if (!name.trim()) return;
    setCreating(true);
    await onSubmit({ name: name.trim(), width, height, fps, totalFrames });
    setCreating(false);
  };

  return ReactDOM.createPortal(
    <div className="lib-modal-overlay" onClick={e => { if (e.target === e.currentTarget) onCancel(); }}>
      <form className="lib-modal" onSubmit={handleSubmit}>
        <div className="lib-modal__header">
          <span className="lib-modal__title">⊞ New Composition</span>
          <button type="button" className="lib-modal__close" onClick={onCancel}>✕</button>
        </div>
        <div className="lib-modal__body">
          <label className="lib-comp-cfg__label">Name</label>
          <input ref={nameRef} className="lib-comp-cfg__input" value={name}
            onChange={e => setName(e.target.value)} placeholder="Composition name…" />

          <label className="lib-comp-cfg__label" style={{ marginTop: 8 }}>Resolution Preset</label>
          <div className="lib-comp-cfg__presets">
            {PRESETS.map(p => (
              <button key={p.label} type="button"
                className={`lib-comp-cfg__preset${width === p.w && height === p.h ? ' lib-comp-cfg__preset--active' : ''}`}
                onClick={() => applyPreset(p.w, p.h)}>{p.label}</button>
            ))}
          </div>

          <div className="lib-comp-cfg__row" style={{ marginTop: 8 }}>
            <div className="lib-comp-cfg__field">
              <label className="lib-comp-cfg__label">Width (px)</label>
              <input className="lib-comp-cfg__input lib-comp-cfg__input--num" type="number"
                min={1} max={7680} value={width} onChange={e => setWidth(+e.target.value)} />
            </div>
            <div className="lib-comp-cfg__field">
              <label className="lib-comp-cfg__label">Height (px)</label>
              <input className="lib-comp-cfg__input lib-comp-cfg__input--num" type="number"
                min={1} max={4320} value={height} onChange={e => setHeight(+e.target.value)} />
            </div>
          </div>
          <div className="lib-comp-cfg__row" style={{ marginTop: 6 }}>
            <div className="lib-comp-cfg__field">
              <label className="lib-comp-cfg__label">Frame Rate</label>
              <select className="lib-comp-cfg__input lib-comp-cfg__input--num"
                value={fps} onChange={e => setFps(+e.target.value)}>
                {FPS_OPTIONS.map(f => <option key={f} value={f}>{f} fps</option>)}
              </select>
            </div>
            <div className="lib-comp-cfg__field">
              <label className="lib-comp-cfg__label">Duration (frames)</label>
              <input className="lib-comp-cfg__input lib-comp-cfg__input--num" type="number"
                min={1} max={216000} value={totalFrames} onChange={e => setTotalFrames(+e.target.value)} />
            </div>
          </div>
          <div className="lib-comp-cfg__hint" style={{ marginTop: 4 }}>
            {durationSec}s · {width}×{height} · {fps}fps
          </div>
        </div>
        <div className="lib-modal__footer">
          <button type="button" className="lib-comp-cfg__btn lib-comp-cfg__btn--cancel" onClick={onCancel}>Cancel</button>
          <button type="submit" className="lib-comp-cfg__btn lib-comp-cfg__btn--create" disabled={creating || !name.trim()}>
            {creating ? 'Creating…' : '✓ Create'}
          </button>
        </div>
      </form>
    </div>,
    document.body
  );
}

//   Inline rename  

function InlineRename({ initial, onCommit, onCancel }: {
  initial: string; onCommit: (v: string) => void; onCancel: () => void;
}) {
  const [val, setVal] = useState(initial);
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => { ref.current?.select(); }, []);
  return (
    <input ref={ref} className="lib-card__rename" value={val}
      onChange={e => setVal(e.target.value)}
      onBlur={() => val.trim() ? onCommit(val.trim()) : onCancel()}
      onKeyDown={e => {
        if (e.key === 'Enter') val.trim() ? onCommit(val.trim()) : onCancel();
        if (e.key === 'Escape') onCancel();
      }} />
  );
}

//   Card component  

interface CardProps {
  type: string;
  title: string;
  badge?: string;
  isActive?: boolean;
  isDragging?: boolean;
  onDoubleClick?: () => void;
  onContextMenu?: (e: React.MouseEvent) => void;
  onDragStart?: (e: React.DragEvent) => void;
  onDragEnd?: () => void;
  onDelete?: () => void;
  renaming?: boolean;
  onRenameCommit?: (v: string) => void;
  onRenameCancel?: () => void;
  subtitle?: string;
}

function LibCard({
  type, title, badge, isActive, isDragging,
  onDoubleClick, onContextMenu, onDragStart, onDragEnd,
  onDelete, renaming, onRenameCommit, onRenameCancel, subtitle,
}: CardProps) {
  return (
    <div
      className={`lib-card${isActive ? ' lib-card--active' : ''}${isDragging ? ' lib-card--dragging' : ''}`}
      draggable={!!onDragStart}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onDoubleClick={onDoubleClick}
      onContextMenu={onContextMenu}
    >
      <CardThumb type={type} />
      <div className="lib-card__body">
        {badge && <span className={`lib-card__badge lib-card__badge--${type}`}>{badge}</span>}
        {renaming && onRenameCommit && onRenameCancel ? (
          <InlineRename initial={title} onCommit={onRenameCommit} onCancel={onRenameCancel} />
        ) : (
          <span className="lib-card__title" title={title}>{title}</span>
        )}
        {subtitle && <span className="lib-card__subtitle">{subtitle}</span>}
      </div>
      {onDelete && (
        <button className="lib-card__del" title="Remove" onClick={e => { e.stopPropagation(); onDelete(); }}>✕</button>
      )}
    </div>
  );
}

// Section header  

function SectionHeader({ label, onAdd }: { label: string; onAdd?: () => void }) {
  return (
    <div className="lib__section">
      <span className="lib__section-label">{label}</span>
      <div className="lib__section-line" />
      {onAdd && (
        <button className="lib__section-add" onClick={onAdd} title={`New ${label}`}>+</button>
      )}
    </div>
  );
}

// LibraryPanel  

export default function LibraryPanel({ onAddToTimeline }: {
  onAddToTimeline?: (asset: AssetItem, trackIndex?: number) => void;
}) {
  const { state, dispatch } = useTimeline();

  const [assets, setAssets] = useState<AssetItem[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading]  = useState(false);
  const [dragging, setDragging] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Semantic search state
  const [semanticResults, setSemanticResults] = useState<any[] | null>(null);
  const [semanticLoading, setSemanticLoading] = useState(false);
  const [indexStatuses, setIndexStatuses] = useState<Record<string, string>>({}); // assetId → status (video)
  const [transcriptStatuses, setTranscriptStatuses] = useState<Record<string, string>>({}); // assetId → status (audio)
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [comps, setComps] = useState<CompMeta[]>([]);
  const [showCfg, setShowCfg] = useState(false);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [compError, setCompError] = useState<string | null>(null);
  const [ctxMenu, setCtxMenu] = useState<CtxMenu | null>(null);

  // WebComp state
  const [webcomps, setWebcomps] = useState<WebCompMeta[]>([]);
  const [showWcCfg, setShowWcCfg] = useState(false);
  const [wcError, setWcError] = useState<string | null>(null);

  // Media job state  
  const [jobs, setJobs] = useState<MediaJob[]>([]);

  const openCtx = useCallback((e: React.MouseEvent, items: CtxItem[]) => {
    e.preventDefault(); e.stopPropagation();
    setCtxMenu({ x: e.clientX, y: e.clientY, items });
  }, []);

  //   Load assets  
  const refreshAssets = useCallback(async () => {
    setLoading(true); const data = await fetchAssets(); setAssets(data); setLoading(false);
  }, []);

  useEffect(() => {
    if ((window as any).__FADE_PORT__) refreshAssets();
    else { const h = () => refreshAssets(); window.addEventListener('fade:port', h, { once: true }); return () => window.removeEventListener('fade:port', h); }
  }, [refreshAssets]);
  useEffect(() => {
    const h = () => refreshAssets();
    window.addEventListener('fade:library-changed', h);
    return () => window.removeEventListener('fade:library-changed', h);
  }, [refreshAssets]);

  // Subscribe to job SSE events  
  useEffect(() => {
    const handleJob = (e: Event) => {
      const job = (e as CustomEvent<MediaJob>).detail;
      if (!job?.jobId) return;
      setJobs(prev => {
        const idx = prev.findIndex(j => j.jobId === job.jobId);
        if (idx >= 0) { const next = [...prev]; next[idx] = job; return next; }
        return [job, ...prev];
      });
      if (job.status === 'done') refreshAssets();
    };
    window.addEventListener('fade:job-update', handleJob);
    return () => window.removeEventListener('fade:job-update', handleJob);
  }, [refreshAssets]);

  const dismissJob = useCallback((jobId: string) => {
    setJobs(prev => prev.filter(j => j.jobId !== jobId));
  }, []);
 
  const indexStatusesRef = useRef<Record<string, string>>(indexStatuses);
  useEffect(() => { indexStatusesRef.current = indexStatuses; }, [indexStatuses]);

  useEffect(() => {
    const videoAssets = assets.filter(a => a.type === 'video');
    if (!videoAssets.length) return;
    let cancelled = false;
    const poll = async () => {
      const statuses: Record<string, string> = {};
      await Promise.all(videoAssets.map(async a => {
        try {
          const r = await fetch(`${base()}/library/index-status/${a.assetId}`);
          const d = await r.json();
          statuses[a.assetId] = d.status;
        } catch { statuses[a.assetId] = 'unknown'; }
      }));
      if (!cancelled) setIndexStatuses(statuses);
    };
    poll();
    // keep polling while any video is still being indexed
    const interval = setInterval(async () => {
      const cur = indexStatusesRef.current;   
      const stillActive = videoAssets.some(a => cur[a.assetId] === 'pending' || cur[a.assetId] === 'running');
      if (!stillActive) { clearInterval(interval); return; }
      await poll();
    }, 3000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [assets]);

  // Poll transcript status for all audio assets
  const transcriptStatusesRef = useRef<Record<string, string>>(transcriptStatuses);
  useEffect(() => { transcriptStatusesRef.current = transcriptStatuses; }, [transcriptStatuses]);

  useEffect(() => {
    const audioAssets = assets.filter(a => a.type === 'audio');
    if (!audioAssets.length) return;
    let cancelled = false;
    const poll = async () => {
      const statuses: Record<string, string> = {};
      await Promise.all(audioAssets.map(async a => {
        try {
          const r = await fetch(`${base()}/library/transcript-status/${a.assetId}`);
          const d = await r.json();
          statuses[a.assetId] = d.status;
        } catch { statuses[a.assetId] = 'unknown'; }
      }));
      if (!cancelled) setTranscriptStatuses(statuses);
    };
    poll();
    const interval = setInterval(async () => {
      const cur = transcriptStatusesRef.current;
      const stillActive = audioAssets.some(a => cur[a.assetId] === 'running');
      if (!stillActive) { clearInterval(interval); return; }
      await poll();
    }, 3000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [assets]);

  // Debounced semantic search  
  useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    if (query.length < 4) { setSemanticResults(null); return; }
    // Check if query matches any filename exactly  
    const hasFilenameMatch = assets.some(a => a.filename.toLowerCase().includes(query.toLowerCase()));
    if (hasFilenameMatch) { setSemanticResults(null); return; }
    searchTimerRef.current = setTimeout(async () => {
      setSemanticLoading(true);
      try {
        const r = await fetch(`${base()}/search/video?q=${encodeURIComponent(query)}&top_k=8`);
        const d = await r.json();
        setSemanticResults(d.results ?? []);
      } catch { setSemanticResults([]); }
      finally { setSemanticLoading(false); }
    }, 500);
    return () => { if (searchTimerRef.current) clearTimeout(searchTimerRef.current); };
  }, [query, assets]);

  //   Load comps
  const refreshComps = useCallback(async () => {
    try { setComps(await fetchComps()); } catch { /* ignore */ }
  }, []);
  useEffect(() => {
    if ((window as any).__FADE_PORT__) refreshComps();
    else { const h = () => refreshComps(); window.addEventListener('fade:port', h, { once: true }); return () => window.removeEventListener('fade:port', h); }
  }, [refreshComps]);
  useEffect(() => {
    const h = () => refreshComps();
    window.addEventListener('fade:comps-changed', h);
    return () => window.removeEventListener('fade:comps-changed', h);
  }, [refreshComps]);

  //   Load webcomps
  const refreshWebComps = useCallback(async () => {
    try { setWebcomps(await fetchWebComps()); } catch { /* ignore */ }
  }, []);
  useEffect(() => {
    if ((window as any).__FADE_PORT__) refreshWebComps();
    else { const h = () => refreshWebComps(); window.addEventListener('fade:port', h, { once: true }); return () => window.removeEventListener('fade:port', h); }
  }, [refreshWebComps]);
  useEffect(() => {
    const h = () => refreshWebComps();
    window.addEventListener('fade:webcomps-changed', h);
    return () => window.removeEventListener('fade:webcomps-changed', h);
  }, [refreshWebComps]);

  //   Asset handlers  
  const handleFileSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files) return; setLoading(true);
    for (const f of Array.from(e.target.files)) await importAsset((f as any).path ?? f.name);
    await refreshAssets(); if (fileInputRef.current) fileInputRef.current.value = '';
  }, [refreshAssets]);

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault(); setLoading(true);
    for (const item of Array.from(e.dataTransfer.items)) {
      const entry = item.webkitGetAsEntry?.();
      if (entry?.isFile) await new Promise<void>(res =>
        (entry as any).file((f: File) => importAsset((f as any).path ?? f.name).then(() => res()))
      );
    }
    await refreshAssets();
  }, [refreshAssets]);

  //   Comp handlers  
  const handleCreateComp = useCallback(async (cfg: CompConfig) => {
    setCompError(null);
    try { const c = await apiCreateComp(cfg); setComps(p => [...p, c]); setShowCfg(false); }
    catch (err: any) { setCompError(err.message ?? 'Failed to create composition'); }
  }, []);

  const handleDeleteComp = useCallback(async (comp: CompMeta) => {
    if (!window.confirm(`Delete "${comp.name}"?`)) return;
    await apiDeleteComp(comp.compId);
    setComps(p => p.filter(c => c.compId !== comp.compId));
    if (state.activeCompId === comp.compId) dispatch({ type: 'EXIT_COMP' });
  }, [state.activeCompId, dispatch]);

  const handleEnterComp = useCallback((comp: CompMeta) => {
    dispatch({ type: 'ENTER_COMP', compId: comp.compId, compName: comp.name });
  }, [dispatch]);

  const handleAddCompToTimeline = useCallback(async (comp: CompMeta) => {
    try { await apiAddCompClip(comp.compId, state.currentFrame, 90); }
    catch (err: any) { setCompError(err.message ?? 'Cycle detected'); }
  }, [state.currentFrame]);

  const handleRenameComp = useCallback(async (compId: string, name: string) => {
    await apiRenameComp(compId, name);
    setComps(p => p.map(c => c.compId === compId ? { ...c, name } : c));
    setRenamingId(null);
  }, []);

  //   WebComp handlers
  const handleCreateWebComp = useCallback(async (name: string, template: string) => {
    setWcError(null);
    const wc = await apiCreateWebComp(name, template);
    setWebcomps(p => [...p, wc]);
    setShowWcCfg(false);
  }, []);

  const handleAddWebCompToTimeline = useCallback(async (wc: WebCompMeta) => {
    try { await apiAddWebCompClip(wc.assetId, state.currentFrame, wc.durationFrames || 150); }
    catch (err: any) { setWcError(err.message ?? 'Failed'); }
  }, [state.currentFrame]);

  //   Context menus  
  const assetCtx = useCallback((e: React.MouseEvent, asset: AssetItem) => {
    openCtx(e, [
      { icon: '↓', label: 'Add to Timeline', onClick: () => onAddToTimeline?.(asset, 0) },
      { icon: '', label: '', sep: true, onClick: () => {} },
      { icon: '✕', label: 'Remove', danger: true, onClick: async () => { await removeAsset(asset.assetId); setAssets(p => p.filter(a => a.assetId !== asset.assetId)); } },
    ]);
  }, [openCtx, onAddToTimeline]);

  const compCtx = useCallback((e: React.MouseEvent, comp: CompMeta) => {
    const items: CtxItem[] = [
      { icon: '✎', label: 'Open',                         onClick: () => handleEnterComp(comp) },
      { icon: '↓', label: 'Add to Timeline at Playhead',  onClick: () => handleAddCompToTimeline(comp) },
      { icon: '', label: '', sep: true, onClick: () => {} },
      { icon: '✏', label: 'Rename',                       onClick: () => setRenamingId(comp.compId) },
    ];
    if (!comp.isRoot) items.push({ icon: '🗑', label: 'Delete', danger: true, onClick: () => handleDeleteComp(comp) });
    openCtx(e, items);
  }, [openCtx, handleEnterComp, handleAddCompToTimeline, handleDeleteComp]);

  const bgCtx = useCallback((e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('.lib-card,.lib-modal-overlay')) return;
    openCtx(e, [
      { icon: '⊞', label: 'New Composition',  onClick: () => setShowCfg(true) },
      { icon: '⌨', label: 'New WebComp',      onClick: () => setShowWcCfg(true) },
      { icon: '+', label: 'Import Media…',    onClick: () => fileInputRef.current?.click() },
      { icon: '', label: '', sep: true, onClick: () => {} },
      { icon: '↺', label: 'Refresh',          onClick: () => { refreshAssets(); refreshComps(); refreshWebComps(); } },
    ]);
  }, [openCtx, refreshAssets, refreshComps, refreshWebComps]);


  const filtered = assets.filter(a => a.filename.toLowerCase().includes(query.toLowerCase()));

  // Helpers for semantic results
  const videoAssets = assets.filter(a => a.type === 'video');
  const indexingCount = videoAssets.filter(a => indexStatuses[a.assetId] === 'pending' || indexStatuses[a.assetId] === 'running').length;
  const allIndexed   = videoAssets.length > 0 && videoAssets.every(a => indexStatuses[a.assetId] === 'done');

  const isSemanticMode = semanticResults !== null || semanticLoading;

  return (
    <div className="lib" onDragOver={e => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; }}
      onDrop={handleDrop} onContextMenu={bgCtx}>

      {ctxMenu && <ContextMenu menu={ctxMenu} onClose={() => setCtxMenu(null)} />}
      {showCfg && <CompConfigModal onSubmit={handleCreateComp} onCancel={() => { setShowCfg(false); setCompError(null); }} />}
      {showWcCfg && (
        <WebCompCreateModal
          onSubmit={handleCreateWebComp}
          onCancel={() => { setShowWcCfg(false); setWcError(null); }}
        />
      )}

      {/* Search bar */}
      <div className="lib__search">
        <span className="lib__search-icon">{semanticLoading ? '⟳' : isSemanticMode ? '✦' : '⌕'}</span>
        <input
          className="lib__search-input"
          placeholder="Search files or describe a scene…"
          value={query}
          onChange={e => setQuery(e.target.value)}
        />
        {query && <button className="lib__search-clear" onClick={() => { setQuery(''); setSemanticResults(null); }} title="Clear">✕</button>}
        <button className="lib__import-btn" title="Import" onClick={() => fileInputRef.current?.click()}>+</button>
        <input ref={fileInputRef} type="file" hidden multiple accept="video/*,image/*,audio/*,.svg" onChange={handleFileSelect} />
      </div>

      {compError && (
        <div className="lib-comp-cfg__error" onClick={() => setCompError(null)}>⚠ {compError}</div>
      )}
      {wcError && (
        <div className="lib-comp-cfg__error" style={{ borderColor: '#a78bfa' }} onClick={() => setWcError(null)}>⚠ {wcError}</div>
      )}

      {/* GRID */}
      <div className="lib__grid">
 
        {isSemanticMode && (
          <div style={{ gridColumn: '1/-1' }}>
            {semanticLoading && (
              <div className="lib__semantic-searching">
                <span className="lib__spinner" style={{ display: 'inline-block', width: 14, height: 14, marginRight: 8 }} />
                Searching scenes…
              </div>
            )}

            {!semanticLoading && semanticResults && semanticResults.length > 0 && (
              <>
                <div className="lib__semantic-label">✦ Scene matches for "{query}"</div>
                {semanticResults.map((hit, i) => {
                  const asset = assets.find(a => a.assetId === hit.assetId);
                  const startS = Math.round(hit.start_sec);
                  const endS   = Math.round(hit.end_sec);
                  const score  = Math.round(hit.score * 100);
                  const fps = state.fps ?? 30;
                  const inFrames  = Math.round(hit.start_sec * fps);
                  const outFrames = Math.round(hit.end_sec   * fps);
                  const dur = Math.max(1, outFrames - inFrames);
                  return (
                    <div key={i} className="lib__semantic-hit"
                      draggable
                      onDragStart={e => {
                        e.dataTransfer.effectAllowed = 'copy';
                        const payload = JSON.stringify({
                          assetId: hit.assetId,
                          filename: asset?.filename ?? hit.assetId.slice(0, 8),
                          type: asset?.type ?? 'video',
                          start_sec: hit.start_sec,
                          end_sec: hit.end_sec,
                          inFrames,
                          outFrames,
                          duration:   dur,
                        });
                        e.dataTransfer.setData('application/fade-scene-hit', payload);
                        e.dataTransfer.setData('text/fade-scene-hit', payload); // Electron fallback
                      }}
                      onClick={async () => {
                        if (!asset) return;
                        const frame = state.currentFrame ?? 0;
                        await addClipToTimeline(hit.assetId, 0, frame, dur, inFrames);
                        window.dispatchEvent(new CustomEvent('fade:tracks-changed'));
                      }}
                      title={hit.text}
                    >
                      <div className="lib__semantic-hit-score">{score}%</div>
                      <div className="lib__semantic-hit-info">
                        <div className="lib__semantic-hit-name">{asset?.filename ?? hit.assetId.slice(0,8)}</div>
                        <div className="lib__semantic-hit-time">{startS}s – {endS}s</div>
                        <div className="lib__semantic-hit-desc">{hit.text.slice(0, 120)}{hit.text.length > 120 ? '…' : ''}</div>
                      </div>
                    </div>
                  );
                })}
              </>
            )}

            {!semanticLoading && semanticResults && semanticResults.length === 0 && (
              <div className="lib__semantic-empty">
                {allIndexed
                  ? <><span>🔍</span><p>No matching scenes found</p><small>All {videoAssets.length} video{videoAssets.length !== 1 ? 's' : ''} indexed</small></>
                  : indexingCount > 0
                    ? <><span>⏳</span><p>No results yet</p><small>Still indexing {indexingCount} video{indexingCount !== 1 ? 's' : ''}… try again soon</small></>
                    : <><span>🔍</span><p>No matching scenes found</p></>}
              </div>
            )}
          </div>
        )}

        {/*   Normal grid  */}
        {!isSemanticMode && (
          <>
             
            {jobs
              .filter(j => !j.assetId && j.status !== 'done')
              .map(job => (
                <PlaceholderCard key={job.jobId} job={job} onDismiss={() => dismissJob(job.jobId)} />
              ))
            }

            {/* WebComps */}
            {webcomps.map(wc => (
              <div key={wc.assetId} className="lib__card-wrap">
                <LibCard
                  type="webcomp"
                  title={wc.name}
                  badge="WC"
                  subtitle={`${wc.width}×${wc.height} · ${wc.fps}fps`}
                  isDragging={dragging === wc.assetId}
                  onDragStart={e => {
                    setDragging(wc.assetId);
                    e.dataTransfer.setData('application/fade-webcomp', JSON.stringify(wc));
                    e.dataTransfer.effectAllowed = 'copy';
                  }}
                  onDragEnd={() => setDragging(null)}
                  onDoubleClick={() => handleAddWebCompToTimeline(wc)}
                  onContextMenu={e => openCtx(e, [
                    { icon: '↓', label: 'Add to Timeline', onClick: () => handleAddWebCompToTimeline(wc) },
                    { icon: '📁', label: 'Open Folder', onClick: () => (window as any).electronAPI?.shellOpenPath?.(wc.folderPath) },
                    { icon: '', label: '', sep: true, onClick: () => {} },
                    { icon: '✕', label: 'Delete', danger: true, onClick: async () => {
                      if (!window.confirm(`Delete WebComp "${wc.name}"?`)) return;
                      await fetch(`${base()}/timeline/webcomp/${wc.assetId}`, { method: 'DELETE' });
                      setWebcomps(p => p.filter(w => w.assetId !== wc.assetId));
                    }},
                  ])}
                />
              </div>
            ))}

            {comps.map(comp => {
              const isActive = state.activeCompId === comp.compId;
              return (
                <div key={comp.compId} className="lib__card-wrap">
                  <LibCard
                    type="comp"
                    title={comp.name}
                    badge={comp.isRoot ? 'ROOT' : 'COMP'}
                    isActive={isActive}
                    isDragging={dragging === comp.compId}
                    onDragStart={e => {
                      if (comp.isRoot) return;
                      setDragging(comp.compId);
                      e.dataTransfer.setData('application/fade-comp', JSON.stringify(comp));
                      e.dataTransfer.effectAllowed = 'copy';
                    }}
                    onDragEnd={() => setDragging(null)}
                    renaming={renamingId === comp.compId}
                    onRenameCommit={v => handleRenameComp(comp.compId, v)}
                    onRenameCancel={() => setRenamingId(null)}
                    subtitle={`${comp.width}×${comp.height} · ${comp.fps}fps`}
                    onDoubleClick={() => handleEnterComp(comp)}
                    onContextMenu={e => compCtx(e, comp)}
                  />
                </div>
              );
            })}

            {loading && filtered.length === 0 && (
              <div className="lib__spinner" style={{ margin: '20px auto', gridColumn: '1/-1' }} />
            )}

            {filtered.map(asset => {
              // Asset-bound jobs for this specific card  
              const assetJobs = jobs.filter(j => j.assetId === asset.assetId);
              return (
                <div key={asset.assetId} className="lib__card-wrap">
                  <LibCard
                    type={asset.type}
                    title={asset.filename}
                    badge={asset.type}
                    isDragging={dragging === asset.assetId}
                    onDragStart={e => {
                      setDragging(asset.assetId);
                      e.dataTransfer.setData('application/fade-asset', JSON.stringify(asset));
                      e.dataTransfer.effectAllowed = 'copy';
                    }}
                    onDragEnd={() => setDragging(null)}
                    onDoubleClick={() => onAddToTimeline?.(asset, 0)}
                    onContextMenu={e => assetCtx(e, asset)}
                    onDelete={async () => { await removeAsset(asset.assetId); setAssets(p => p.filter(a => a.assetId !== asset.assetId)); }}
                  />
                  
                  <AssetTaskOverlay
                    jobs={assetJobs}
                    indexStatus={
                      asset.type === 'audio'
                        ? transcriptStatuses[asset.assetId]
                        : indexStatuses[asset.assetId]
                    }
                    assetType={asset.type}
                    assetId={asset.assetId}
                    onCancelIndex={() => {
                      // Optimistically hide the overlay by bumping indexStatuses
                      setIndexStatuses(prev => ({ ...prev, [asset.assetId]: 'cancelled' }));
                      setJobs(prev => prev.filter(
                        j => !(j.assetId === asset.assetId &&
                               (j.type === 'video_index' || j.type === 'image_index'))
                      ));
                    }}
                  />
                </div>
              );
            })}

            {!loading && filtered.length === 0 && comps.length === 0 && (
              <div className="lib__empty" style={{ gridColumn: '1/-1' }}>
                <div className="lib__empty-icon">📂</div>
                <p className="lib__empty-hint">Drop files here or click <strong>+</strong></p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
