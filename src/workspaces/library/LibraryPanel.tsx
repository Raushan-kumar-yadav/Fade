import React, {
  useState, useEffect, useCallback, useRef, useLayoutEffect,
} from 'react';
import ReactDOM from 'react-dom';
import { fetchAssets, importAsset, removeAsset, type AssetItem } from '../../api/useApi';
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
interface CtxMenu { x: number; y: number; items: CtxItem[]; }
interface CtxItem {
  icon: string; label: string; danger?: boolean; sep?: boolean; onClick: () => void;
}

//   Constants  

const PRESETS = [
  { label: '1080p', w: 1920, h: 1080 }, { label: '4K',    w: 3840, h: 2160 },
  { label: '720p',  w: 1280, h: 720  }, { label: 'Square',w: 1080, h: 1080 },
  { label: '9:16',  w: 1080, h: 1920 }, { label: '4:3',   w: 1440, h: 1080 },
];
const FPS_OPTIONS = [23.976, 24, 25, 29.97, 30, 50, 59.94, 60];
const BASE = 'http://localhost:8000';

//   Type thumbnails

const THUMB_BG: Record<string, string> = {
  video: 'linear-gradient(135deg,#1a2a4a 0%,#0d1926 100%)',
  image: 'linear-gradient(135deg,#1a3a2a 0%,#0d2018 100%)',
  audio: 'linear-gradient(135deg,#2a1a3a 0%,#180d26 100%)',
  svg: 'linear-gradient(135deg,#1a3a3a 0%,#0d2222 100%)',
  comp: 'linear-gradient(135deg,#0d2e2e 0%,#051a1a 100%)',
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

async function fetchComps(): Promise<CompMeta[]> {
  const r = await fetch(`${BASE}/comps`); return (await r.json()).comps ?? [];
}
async function apiCreateComp(cfg: CompConfig): Promise<CompMeta> {
  const r = await fetch(`${BASE}/comps`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: cfg.name, width: cfg.width, height: cfg.height, fps: cfg.fps, totalFrames: cfg.totalFrames }),
  });
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail ?? 'Failed'); }
  return r.json();
}
async function apiDeleteComp(id: string) { await fetch(`${BASE}/comps/${id}`, { method: 'DELETE' }); }
async function apiAddCompClip(compId: string, startFrame: number, duration: number) {
  const r = await fetch(`${BASE}/clips/comp`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ compId, startFrame, duration }),
  });
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail ?? 'Failed'); }
  return r.json();
}
async function apiRenameComp(id: string, name: string) {
  await fetch(`${BASE}/comps/${id}/rename`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
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

  const [comps, setComps] = useState<CompMeta[]>([]);
  const [showCfg, setShowCfg] = useState(false);
  const [renamingId, setRenamingId]  = useState<string | null>(null);
  const [compError, setCompError]   = useState<string | null>(null);
  const [ctxMenu, setCtxMenu] = useState<CtxMenu | null>(null);

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

  //   Load comps  
  const refreshComps = useCallback(async () => {
    try { setComps(await fetchComps()); } catch { /* ignore */ }
  }, []);
  useEffect(() => {
    if ((window as any).__FADE_PORT__) refreshComps();
    else { const h = () => refreshComps(); window.addEventListener('fade:port', h, { once: true }); return () => window.removeEventListener('fade:port', h); }
  }, [refreshComps]);

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
      { icon: '⊞', label: 'New Composition', onClick: () => setShowCfg(true) },
      { icon: '+', label: 'Import Media…',   onClick: () => fileInputRef.current?.click() },
      { icon: '', label: '', sep: true, onClick: () => {} },
      { icon: '↺', label: 'Refresh',         onClick: () => { refreshAssets(); refreshComps(); } },
    ]);
  }, [openCtx, refreshAssets, refreshComps]);

  const filtered = assets.filter(a => a.filename.toLowerCase().includes(query.toLowerCase()));

   
  return (
    <div className="lib" onDragOver={e => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; }}
      onDrop={handleDrop} onContextMenu={bgCtx}>

      {ctxMenu && <ContextMenu menu={ctxMenu} onClose={() => setCtxMenu(null)} />}
      {showCfg && <CompConfigModal onSubmit={handleCreateComp} onCancel={() => { setShowCfg(false); setCompError(null); }} />}

      {/* Search bar */}
      <div className="lib__search">
        <span className="lib__search-icon">⌕</span>
        <input className="lib__search-input" placeholder="Search…" value={query} onChange={e => setQuery(e.target.value)} />
        <button className="lib__import-btn" title="Import" onClick={() => fileInputRef.current?.click()}>+</button>
        <input ref={fileInputRef} type="file" hidden multiple accept="video/*,image/*,audio/*,.svg" onChange={handleFileSelect} />
      </div>

      {compError && (
        <div className="lib-comp-cfg__error" onClick={() => setCompError(null)}>⚠ {compError}</div>
      )}

      {/* GRID — Comps + Media unified, no dividers */}
      <div className="lib__grid">
        {comps.map(comp => {
          const isActive = state.activeCompId === comp.compId;
          return (
            <LibCard
              key={comp.compId}
              type="comp"
              title={comp.name}
              badge={comp.isRoot ? 'ROOT' : 'COMP'}
              isActive={isActive}
              isDragging={dragging === comp.compId}
              onDragStart={e => {
                if (comp.isRoot) return; // Root shouldn't be draggable
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
          );
        })}

        {loading && filtered.length === 0 && (
          <div className="lib__spinner" style={{ margin: '20px auto', gridColumn: '1/-1' }} />
        )}

        {filtered.map(asset => (
          <LibCard
            key={asset.assetId}
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
        ))}

        {!loading && filtered.length === 0 && comps.length === 0 && (
          <div className="lib__empty" style={{ gridColumn: '1/-1' }}>
            <div className="lib__empty-icon">📂</div>
            <p className="lib__empty-hint">Drop files here or click <strong>+</strong></p>
          </div>
        )}
      </div>
    </div>
  );
}
