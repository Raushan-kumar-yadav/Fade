import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useSelection } from '../../context/selectionContext';
import { inspectorApi, type ParamRow, type ClipParams, type KFDef } from '../../api/inspectorApi';
import { maskApi, type MaskInfo } from '../../api/toolsApi';
import './InspectorPanel.css';


// ── Vec4 Color Picker ─────────────────────────────────────────────────────────
// Renders when 4 consecutive params share a base name like color_r/g/b/a

interface Vec4Props {
  label:  string;
  r: number; g: number; b: number; a: number;
  onChange: (r: number, g: number, b: number, a: number) => void;
}

function Vec4ColorPicker({ label, r, g, b, a, onChange }: Vec4Props) {
  // Convert 0-1 float to CSS hex
  const toHex = (v: number) => Math.round(Math.max(0, Math.min(1, v)) * 255).toString(16).padStart(2, '0');
  const hexColor = `#${toHex(r)}${toHex(g)}${toHex(b)}`;

  const handleColorInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const hex = e.target.value;
    const nr = parseInt(hex.slice(1, 3), 16) / 255;
    const ng = parseInt(hex.slice(3, 5), 16) / 255;
    const nb = parseInt(hex.slice(5, 7), 16) / 255;
    onChange(nr, ng, nb, a);
  };

  const handleAlpha = (e: React.ChangeEvent<HTMLInputElement>) => {
    onChange(r, g, b, parseFloat(e.target.value));
  };

  return (
    <div className="insp-vec4">
      <span className="insp-vec4__label">{label}</span>
      <div className="insp-vec4__controls">
        <label className="insp-vec4__swatch" title="Pick color">
          <input type="color" value={hexColor} onChange={handleColorInput} />
          <span className="insp-vec4__swatch-preview" style={{ background: hexColor }} />
        </label>
        <span className="insp-vec4__hex">{hexColor.toUpperCase()}</span>
        <input
          type="range" min={0} max={1} step={0.01}
          value={a}
          onChange={handleAlpha}
          className="insp-vec4__alpha"
          title={`Alpha: ${a.toFixed(2)}`}
          style={{
            background: `linear-gradient(to right, transparent, ${hexColor})`,
          }}
        />
        <span className="insp-vec4__alpha-val">{Math.round(a * 100)}%</span>
      </div>
    </div>
  );
}

// ── Keyframe diamond button ────────────────────────────────────────────────────

interface KeyframeBtnProps {
  isAnimated: boolean;
  hasKf:      boolean;
  onToggle:   () => void;
  onPrev:     () => void;
  onNext:     () => void;
}

function KeyframeBtn({ isAnimated, hasKf, onToggle, onPrev, onNext }: KeyframeBtnProps) {
  return (
    <div className="insp-kf-group">
      <button className="insp-kf-nav" disabled={!isAnimated} onClick={onPrev} title="Previous keyframe">‹</button>
      <button
        className={`insp-kf-diamond${hasKf ? ' insp-kf-diamond--active' : ''}${isAnimated ? ' insp-kf-diamond--animated' : ''}`}
        onClick={onToggle}
        title={hasKf ? 'Remove keyframe' : 'Add keyframe'}
      >
        <svg width="10" height="10" viewBox="0 0 10 10">
          <polygon
            points="5,0 10,5 5,10 0,5"
            fill={hasKf ? '#6366f1' : (isAnimated ? '#374151' : 'none')}
            stroke={isAnimated ? '#6366f1' : '#374151'}
            strokeWidth="1.5"
          />
        </svg>
      </button>
      <button className="insp-kf-nav" disabled={!isAnimated} onClick={onNext} title="Next keyframe">›</button>
    </div>
  );
}

// ── Keyframe Track Editor (click diamond to open) ─────────────────────────────

interface KFTrackProps {
  clipId:  string;
  paramId: string;
  label:   string;
  frames:  number[];
  currentFrame: number;
  onRefresh: () => void;
}

const TL_H  = 48;   // timeline SVG height px
const TL_PAD = 16;  // left/right padding in frame-space

function KFTrackPanel({ clipId, paramId, label, frames, currentFrame, onRefresh }: KFTrackProps) {
  const [kfData,   setKfData]   = useState<KFDef[]>([]);
  const [loading,  setLoading]  = useState(false);
  const [selSet,   setSelSet]   = useState<Set<number>>(new Set());
  const [ctxMenu,  setCtxMenu]  = useState<{ x: number; y: number; frame: number } | null>(null);
  // Timeline zoom/pan (in frame units)
  const [tlZoom,   setTlZoom]   = useState(1);  // pixels per frame
  const [tlPan,    setTlPan]    = useState(0);   // left offset in frame units
  // Box selection
  const [boxSel,   setBoxSel]   = useState<{ x0: number; x1: number } | null>(null);
  // Drag-to-move
  const draggingKf = useRef<{ frames: number[]; startPx: number } | null>(null);
  const svgRef     = useRef<SVGSVGElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await inspectorApi.listKeyframes(clipId, paramId);
      setKfData(r.frames);
    } finally { setLoading(false); }
  }, [clipId, paramId]);

  useEffect(() => { load(); }, [load]);

  // ── Key bindings ─────────────────────────────────────────────────────────
  useEffect(() => {
    const onKey = async (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).matches('input,select,textarea')) return;
      if (e.key === 'Delete' || e.key === 'Backspace') {
        for (const f of selSet) {
          await inspectorApi.removeKeyframe(clipId, paramId, f);
        }
        setSelSet(new Set());
        onRefresh(); load();
      }
      if (e.ctrlKey && e.key === 'a') {
        e.preventDefault();
        setSelSet(new Set(kfData.map(k => k.frame)));
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selSet, kfData, clipId, paramId, onRefresh, load]);

  // ── Helpers ──────────────────────────────────────────────────────────────
  const svgWidth = () => svgRef.current?.clientWidth ?? 300;
  const maxFrame = useMemo(() => {
    const all = kfData.map(k => k.frame);
    return all.length > 0 ? Math.max(...all) : 100;
  }, [kfData]);

  // pixels-per-frame (with zoom)
  const ppf = useMemo(() => {
    const w = svgWidth() - TL_PAD * 2;
    return w / (maxFrame || 1) * tlZoom;
  }, [maxFrame, tlZoom]);

  const frameToX = useCallback((f: number) =>
    TL_PAD + (f - tlPan) * ppf, [ppf, tlPan]);

  const xToFrame = useCallback((px: number) =>
    Math.round((px - TL_PAD) / ppf + tlPan), [ppf, tlPan]);

  // ── Scroll = zoom ─────────────────────────────────────────────────────────
  const onWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    setTlZoom(z => Math.max(0.1, Math.min(50, z * factor)));
  }, []);

  // ── Pan / box-select on SVG background ───────────────────────────────────
  const panStart = useRef<{ clientX: number; startPan: number; moved: boolean } | null>(null);

  const onBgDown = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    if ((e.target as Element).getAttribute('data-kf')) return; // hit a diamond
    panStart.current = { clientX: e.clientX, startPan: tlPan, moved: false };
    setBoxSel(null);
  }, [tlPan]);

  const onBgMove = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    if (!panStart.current) return;
    const dx = e.clientX - panStart.current.clientX;
    panStart.current.moved = true;
    if (Math.abs(dx) > 3) {
      const deltaF = -dx / ppf;
      setTlPan(panStart.current.startPan + deltaF);
    }
  }, [ppf]);

  const onBgUp = useCallback(() => { panStart.current = null; }, []);

  // ── Diamond drag-to-move ──────────────────────────────────────────────────
  const onDiamondDown = useCallback((frame: number, e: React.MouseEvent) => {
    e.stopPropagation();
    const sel = selSet.has(frame)
      ? [...selSet]
      : [frame];
    if (!selSet.has(frame)) setSelSet(new Set([frame]));
    draggingKf.current = { frames: sel, startPx: e.clientX };
  }, [selSet]);

  const onDiamondMove = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    if (!draggingKf.current) return;
    // Just move via clientX delta — actual commit happens on mouseup
  }, []);

  const onDiamondUp = useCallback(async (e: React.MouseEvent<SVGSVGElement>) => {
    if (!draggingKf.current) return;
    const delta = Math.round((e.clientX - draggingKf.current.startPx) / ppf);
    if (delta !== 0) {
      for (const f of draggingKf.current.frames) {
        await inspectorApi.moveKeyframe(clipId, paramId, f, Math.max(0, f + delta));
      }
      onRefresh(); load();
    }
    draggingKf.current = null;
  }, [ppf, clipId, paramId, onRefresh, load]);

  // ── Delete/copy helpers ───────────────────────────────────────────────────
  const deleteKf = useCallback(async (frame: number) => {
    await inspectorApi.removeKeyframe(clipId, paramId, frame);
    setCtxMenu(null);
    setSelSet(prev => { const s = new Set(prev); s.delete(frame); return s; });
    onRefresh(); load();
  }, [clipId, paramId, onRefresh, load]);

  const copyKf = useCallback(async (srcFrame: number) => {
    const kf = kfData.find(k => k.frame === srcFrame);
    if (!kf) return;
    await inspectorApi.addKeyframe(clipId, paramId, { ...kf, frame: currentFrame });
    setCtxMenu(null); onRefresh(); load();
  }, [kfData, clipId, paramId, currentFrame, onRefresh, load]);

  const changeInterp = useCallback(async (frame: number, interp: string) => {
    const kf = kfData.find(k => k.frame === frame);
    if (!kf) return;
    await inspectorApi.removeKeyframe(clipId, paramId, frame);
    await inspectorApi.addKeyframe(clipId, paramId, { ...kf, interp: interp as any });
    onRefresh(); load();
  }, [kfData, clipId, paramId, onRefresh, load]);

  if (loading) return <div className="insp-kftrack-loading">Loading…</div>;

  // ── Render ────────────────────────────────────────────────────────────────
  const playX = frameToX(currentFrame);

  return (
    <div className="insp-kftrack" onClick={e => e.stopPropagation()}>
      {/* Header */}
      <div className="insp-kftrack-header">
        <span className="insp-kftrack-title">Keyframes — {label}</span>
        <span className="insp-kftrack-count">{kfData.length} kf</span>
        <button className="insp-kftrack-zoom-btn" onClick={() => { setTlZoom(1); setTlPan(0); }} title="Reset zoom">⊡</button>
      </div>

      {/* SVG Timeline */}
      <svg
        ref={svgRef}
        className="insp-kftrack-svg"
        width="100%"
        height={TL_H}
        onWheel={onWheel}
        onMouseDown={onBgDown}
        onMouseMove={e => { onBgMove(e); onDiamondMove(e); }}
        onMouseUp={e => { onBgUp(); onDiamondUp(e); }}
        onMouseLeave={onBgUp}
      >
        {/* Background */}
        <rect width="100%" height={TL_H} fill="rgba(255,255,255,0.03)" rx="4" />

        {/* Frame ruler ticks */}
        {Array.from({ length: Math.ceil(maxFrame / 10) + 1 }, (_, i) => i * 10).map(f => {
          const x = frameToX(f);
          if (x < 0 || x > (svgRef.current?.clientWidth ?? 999)) return null;
          return (
            <g key={f}>
              <line x1={x} y1={0} x2={x} y2={6} stroke="rgba(255,255,255,0.12)" strokeWidth={1} />
              <text x={x} y={14} textAnchor="middle" fill="rgba(255,255,255,0.2)" fontSize={8} fontFamily="Inter, monospace">{f}</text>
            </g>
          );
        })}

        {/* Playhead */}
        <line x1={playX} y1={0} x2={playX} y2={TL_H}
              stroke="#f59e0b" strokeWidth={1.5} opacity={0.9} />
        <polygon
          points={`${playX},0 ${playX - 5},8 ${playX + 5},8`}
          fill="#f59e0b"
        />

        {/* Keyframe diamonds */}
        {kfData.map(kf => {
          const x = frameToX(kf.frame);
          const isSel = selSet.has(kf.frame);
          const isCur = kf.frame === currentFrame;
          const col   = isCur ? '#f59e0b' : isSel ? '#818cf8' : '#6366f1';
          return (
            <g key={kf.frame}
               data-kf="1"
               style={{ cursor: 'grab' }}
               onMouseDown={e => onDiamondDown(kf.frame, e)}
               onClick={e => {
                 e.stopPropagation();
                 setSelSet(prev => {
                   const s = new Set(prev);
                   if (s.has(kf.frame)) s.delete(kf.frame); else s.add(kf.frame);
                   return s;
                 });
                 window.dispatchEvent(new CustomEvent('fade:seek', { detail: kf.frame }));
               }}
               onContextMenu={e => {
                 e.preventDefault(); e.stopPropagation();
                 setCtxMenu({ x: e.clientX, y: e.clientY, frame: kf.frame });
               }}
            >
              <polygon
                points={`${x},${TL_H/2-7} ${x+7},${TL_H/2} ${x},${TL_H/2+7} ${x-7},${TL_H/2}`}
                fill={col} stroke={isSel ? '#fff' : 'rgba(255,255,255,0.5)'}
                strokeWidth={isSel ? 1.5 : 1}
              />
              <title>Frame {kf.frame} · {kf.interp} · {kf.value.toFixed(3)}</title>
            </g>
          );
        })}
      </svg>

      {/* Keyframe list */}
      <div className="insp-kftrack-list">
        {kfData.map(kf => (
          <div key={kf.frame}
               className={`insp-kftrack-row${selSet.has(kf.frame) ? ' sel' : ''}`}
               onClick={() => setSelSet(s => { const n = new Set(s); n.has(kf.frame) ? n.delete(kf.frame) : n.add(kf.frame); return n; })}>
            <span className="insp-kftrack-row-frame">F{kf.frame}</span>
            <span className="insp-kftrack-row-val">{kf.value.toFixed(3)}</span>
            <select
              className="insp-kftrack-interp"
              value={kf.interp}
              onChange={e => changeInterp(kf.frame, e.target.value)}
              onClick={e => e.stopPropagation()}
            >
              {['constant','linear','ease_in','ease_out','ease_both','bezier'].map(m => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
            <button className="insp-kftrack-copy" title="Copy to current frame"
                    onClick={e => { e.stopPropagation(); copyKf(kf.frame); }}>⧉</button>
            <button className="insp-kftrack-del" title="Delete keyframe"
                    onClick={e => { e.stopPropagation(); deleteKf(kf.frame); }}>✕</button>
          </div>
        ))}
        {kfData.length === 0 && (
          <div className="insp-kftrack-empty">No keyframes yet. Click the ◇ diamond to add one.</div>
        )}
      </div>

      {/* Context menu */}
      {ctxMenu && (
        <div className="insp-ctx-menu"
             style={{ top: ctxMenu.y, left: ctxMenu.x }}
             onMouseLeave={() => setCtxMenu(null)}>
          <button onClick={() => copyKf(ctxMenu.frame)}>Copy to frame {currentFrame}</button>
          <button onClick={() => deleteKf(ctxMenu.frame)}>Delete</button>
          <button onClick={() => setCtxMenu(null)}>Cancel</button>
        </div>
      )}
    </div>
  );
}

// ── Single param row ────────────────────────────────────────────────────────

interface ParamRowProps {
  param:       ParamRow;
  clipId:      string;
  currentFrame: number;
  onChange:    (id: string, value: number) => void;
  onRefresh:   () => void;
}

function ParamRowWidget({ param, clipId, currentFrame, onChange, onRefresh }: ParamRowProps) {
  const [localVal, setLocalVal] = useState(param.value);
  const [editing,  setEditing]  = useState(false);
  const [showTrack, setShowTrack] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { setLocalVal(param.value); }, [param.value]);

  const handleSlider = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setLocalVal(parseFloat(e.target.value));
  }, []);

  const handleSliderCommit = useCallback(async () => {
    console.log(`[Inspector] slider commit: clipId=${clipId} param=${param.id} value=${localVal}`);
    await inspectorApi.setParam(clipId, param.id, localVal, -1);
    onChange(param.id, localVal);
  }, [clipId, param.id, localVal, onChange]);

  const handleNumberCommit = useCallback(async (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      const v = parseFloat((e.target as HTMLInputElement).value);
      if (!isNaN(v)) {
        const clamped = Math.max(param.min, Math.min(param.max, v));
        setLocalVal(clamped);
        console.log(`[Inspector] number commit: clipId=${clipId} param=${param.id} value=${clamped}`);
        await inspectorApi.setParam(clipId, param.id, clamped, -1);
        onChange(param.id, clamped);
        setEditing(false);
      }
    }
    if (e.key === 'Escape') setEditing(false);
  }, [clipId, param.id, param.min, param.max, onChange]);

  const handleKfToggle = useCallback(async () => {
    if (param.hasKeyframe) {
      await inspectorApi.removeKeyframe(clipId, param.id, currentFrame);
    } else {
      await inspectorApi.addKeyframe(clipId, param.id, {
        frame: currentFrame, value: localVal, interp: 'ease_both',
        handle_in_f: -5, handle_in_v: 0, handle_out_f: 5, handle_out_v: 0,
      });
    }
    onRefresh();
  }, [clipId, param.id, param.hasKeyframe, currentFrame, localVal, onRefresh]);

  const handleKfNav = useCallback((dir: 'prev' | 'next') => {
    const frames = param.keyframes;
    if (!frames.length) return;
    if (dir === 'prev') {
      const prev = [...frames].filter(f => f < currentFrame).pop();
      if (prev != null) window.dispatchEvent(new CustomEvent('fade:seek', { detail: prev }));
    } else {
      const next = frames.find(f => f > currentFrame);
      if (next != null) window.dispatchEvent(new CustomEvent('fade:seek', { detail: next }));
    }
  }, [param.keyframes, currentFrame]);

  const pct = ((localVal - param.min) / (param.max - param.min)) * 100;

  // Format value nicely: integers as int, small decimals with precision
  const fmtVal = (v: number) => {
    if (v % 1 === 0) return v.toFixed(0);
    if (Math.abs(v) < 10) return v.toFixed(3);
    return v.toFixed(2);
  };

  return (
    <>
      <div className={`insp-row${param.isAnimated ? ' insp-row--animated' : ''}`}>
        <KeyframeBtn
          isAnimated={param.isAnimated}
          hasKf={param.hasKeyframe}
          onToggle={handleKfToggle}
          onPrev={() => handleKfNav('prev')}
          onNext={() => handleKfNav('next')}
        />

        <span
          className={`insp-row__label${param.isAnimated ? ' insp-row__label--animated' : ''}`}
          title={param.id}
          onClick={() => param.isAnimated && setShowTrack(s => !s)}
          style={{ cursor: param.isAnimated ? 'pointer' : 'default' }}
        >
          {param.label}
          {param.isAnimated && <span className="insp-row__kf-count">{param.keyframes.length}</span>}
        </span>

        <div className="insp-row__slider-wrap">
          <div className="insp-row__slider-track">
            <div className="insp-row__slider-fill" style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
          </div>
          <input
            type="range"
            className="insp-row__slider"
            min={param.min}
            max={param.max}
            step={(param.max - param.min) / 2000}
            value={localVal}
            onChange={handleSlider}
            onMouseUp={handleSliderCommit}
            onTouchEnd={handleSliderCommit}
            aria-label={param.label}
          />
          {/* Keyframe markers */}
          {param.isAnimated && param.keyframes.map(kf => {
            const kpct = ((kf - param.min) / (param.max - param.min)) * 100;
            return (
              <div key={kf}
                   className={`insp-row__kf-marker${kf === currentFrame ? ' insp-row__kf-marker--current' : ''}`}
                   style={{ left: `${Math.max(0, Math.min(100, kpct))}%` }}
                   title={`Keyframe @ frame ${kf}`} />
            );
          })}
        </div>

        {editing ? (
          <input
            ref={inputRef}
            type="number"
            className="insp-row__num-input"
            defaultValue={fmtVal(localVal)}
            onKeyDown={handleNumberCommit}
            onBlur={() => setEditing(false)}
            autoFocus
            step="any"
          />
        ) : (
          <button
            className="insp-row__val"
            onClick={() => setEditing(true)}
            title="Click to enter value"
          >
            {fmtVal(localVal)}
          </button>
        )}
      </div>

      {showTrack && param.isAnimated && (
        <KFTrackPanel
          clipId={clipId}
          paramId={param.id}
          label={param.label}
          frames={param.keyframes}
          currentFrame={currentFrame}
          onRefresh={onRefresh}
        />
      )}
    </>
  );
}

// ── Group header ───────────────────────────────────────────────────────────────

function GroupHeader({ label, open, onToggle }: { label: string; open: boolean; onToggle: () => void }) {
  return (
    <button className="insp-group-header" onClick={onToggle}>
      <span className={`insp-group-header__arrow${open ? ' open' : ''}`}>▶</span>
      {label}
    </button>
  );
}

// ── Masks Panel ───────────────────────────────────────────────────────────────

function MasksPanel({ clipId }: { clipId: string }) {
  const [masks, setMasks] = useState<MaskInfo[]>([]);
  const [open,  setOpen]  = useState(true);

  const load = useCallback(async () => {
    try {
      const r = await maskApi.list(clipId);
      setMasks(r.masks ?? []);
    } catch { setMasks([]); }
  }, [clipId]);

  useEffect(() => { load(); }, [load]);

  // Listen for mask changes from OverlayCanvas
  useEffect(() => {
    const handler = (e: Event) => {
      const targetId = (e as CustomEvent<string>).detail;
      if (!targetId || targetId === clipId) load();
    };
    window.addEventListener('fade:masks-changed', handler);
    return () => window.removeEventListener('fade:masks-changed', handler);
  }, [clipId, load]);

  if (masks.length === 0) return null;

  return (
    <div className="insp-group">
      <GroupHeader label={`Masks (${masks.length})`} open={open} onToggle={() => setOpen(o => !o)} />
      {open && (
        <div className="insp-group__body">
          {masks.map(m => (
            <div key={m.maskId} className="insp-mask-row">
              <span className="insp-mask-row__icon">⊖</span>
              <span className="insp-mask-row__name">{m.name}</span>
              <span className="insp-mask-row__shape">{m.shape}</span>
              <span className="insp-mask-row__mode">{m.mode}</span>
              <span className="insp-mask-row__pts">{m.pointCount} pts</span>
              <button
                className="insp-mask-row__del"
                title="Remove mask"
                onClick={async () => {
                  await maskApi.remove(clipId, m.maskId);
                  load();
                }}
              >✕</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main Inspector Panel ──────────────────────────────────────────────────────

/** Detect groups of 4 params that form a vec4 color: base_r, base_g, base_b, base_a */
function extractVec4Groups(params: ParamRow[]): { rendered: Set<string>; groups: Map<string, ParamRow[]> } {
  const rendered = new Set<string>();
  const groups   = new Map<string, ParamRow[]>();
  const suffixes = ['_r', '_g', '_b', '_a'];

  params.forEach(p => {
    const sfx = suffixes.find(s => p.id.endsWith(s));
    if (!sfx) return;
    const base = p.id.slice(0, -sfx.length);
    const all  = suffixes.map(s => params.find(q => q.id === base + s));
    if (all.every(Boolean)) {
      groups.set(base, all as ParamRow[]);
      all.forEach(q => rendered.add(q!.id));
    }
  });
  return { rendered, groups };
}

export default function InspectorPanel() {
  const { selected }          = useSelection();
  const [data, setData]       = useState<ClipParams | null>(null);
  const [currentFrame, setCF] = useState(0);
  const [loading, setLoading] = useState(false);
  const [groups, setGroups]   = useState<Record<string, boolean>>({});

  useEffect(() => {
    const handler = (e: Event) => setCF((e as CustomEvent<number>).detail);
    window.addEventListener('fade:frame', handler);
    window.addEventListener('fade:seek',  handler);
    return () => {
      window.removeEventListener('fade:frame', handler);
      window.removeEventListener('fade:seek',  handler);
    };
  }, []);

  const refresh = useCallback(async () => {
    if (!selected) { setData(null); return; }
    setLoading(true);
    try {
      const d = await inspectorApi.getParams(selected.clipId, currentFrame);
      setData(d);
      setGroups(prev => {
        const next = { ...prev };
        [...new Set(d.params.map(p => p.group))].forEach(g => { if (!(g in next)) next[g] = true; });
        return next;
      });
    } catch (err) {
      console.error('[Inspector] fetch error', err);
    } finally { setLoading(false); }
  }, [selected, currentFrame]);

  useEffect(() => { refresh(); }, [selected?.clipId, currentFrame]);

  // Refresh when a mask is added from OverlayCanvas
  useEffect(() => {
    window.addEventListener('fade:masks-changed', refresh as EventListener);
    return () => window.removeEventListener('fade:masks-changed', refresh as EventListener);
  }, [refresh]);

  const handleParamChange = useCallback((_id: string, _val: number) => {
    setData(prev => prev ? {
      ...prev,
      params: prev.params.map(p => p.id === _id ? { ...p, value: _val } : p),
    } : prev);
  }, []);

  const handleVec4Change = useCallback(async (
    clipId: string, base: string, r: number, g: number, b: number, a: number
  ) => {
    console.log(`[Inspector] vec4 change: clipId=${clipId} base=${base} rgba=(${r.toFixed(3)},${g.toFixed(3)},${b.toFixed(3)},${a.toFixed(3)})`);
    const vals = { [`${base}_r`]: r, [`${base}_g`]: g, [`${base}_b`]: b, [`${base}_a`]: a };
    await Promise.all(
      Object.entries(vals).map(([id, v]) => inspectorApi.setParam(clipId, id, v, -1))
    );
    setData(prev => prev ? {
      ...prev,
      params: prev.params.map(p => vals[p.id] !== undefined ? { ...p, value: vals[p.id] } : p),
    } : prev);
  }, []);

  const grouped = useMemo(() => {
    if (!data) return {};
    const map: Record<string, ParamRow[]> = {};
    data.params.forEach(p => {
      if (!map[p.group]) map[p.group] = [];
      map[p.group].push(p);
    });
    return map;
  }, [data]);

  if (!selected) {
    return (
      <div className="insp-empty">
        <div className="insp-empty__icon">⬚</div>
        <div className="insp-empty__text">Select a clip to inspect</div>
      </div>
    );
  }

  if (loading && !data) {
    return (
      <div className="insp-empty">
        <div className="insp-empty__spinner" />
        <div className="insp-empty__text">Loading…</div>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="insp-root">
      {/* Clip header */}
      <div className="insp-clip-header">
        <div className="insp-clip-header__badge">{data.clipType.replace('Clip', '')}</div>
        <div className="insp-clip-header__name">{selected.clipName}</div>
        <div className="insp-clip-header__meta">
          {data.duration} fr · start {data.startFrame} · track {selected.trackIndex + 1}
        </div>
      </div>

      <div className="insp-groups">
        {Object.entries(grouped).map(([group, params]) => {
          const { rendered, groups: vec4Groups } = extractVec4Groups(params);
          return (
            <div key={group} className="insp-group">
              <GroupHeader
                label={group}
                open={groups[group] ?? true}
                onToggle={() => setGroups(prev => ({ ...prev, [group]: !prev[group] }))}
              />
              {(groups[group] ?? true) && (
                <div className="insp-group__body">
                  {/* Vec4 color pickers first */}
                  {[...vec4Groups.entries()].map(([base, [rP, gP, bP, aP]]) => (
                    <Vec4ColorPicker
                      key={base}
                      label={base.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                      r={rP.value} g={gP.value} b={bP.value} a={aP.value}
                      onChange={(r, g, b, a) => handleVec4Change(data.clipId, base, r, g, b, a)}
                    />
                  ))}
                  {/* Individual scalar params (not part of a vec4 group) */}
                  {params.filter(p => !rendered.has(p.id)).map(p => (
                    <ParamRowWidget
                      key={p.id}
                      param={p}
                      clipId={data.clipId}
                      currentFrame={currentFrame}
                      onChange={handleParamChange}
                      onRefresh={refresh}
                    />
                  ))}
                </div>
              )}
            </div>
          );
        })}

        {/* Masks section */}
        <MasksPanel clipId={data.clipId} />
      </div>
    </div>
  );
}
