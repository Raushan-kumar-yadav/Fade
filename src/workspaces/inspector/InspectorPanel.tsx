import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useSelection } from '../../context/selectionContext';
import { inspectorApi, type ParamRow, type ClipParams, type KFDef } from '../../api/inspectorApi';
import { expressionApi, type ExpressionState } from '../../api/expressionApi';
import { maskApi, effectsApi, type MaskInfo, type EffectInfo, type EffectParamDef } from '../../api/toolsApi';
import EffectsPanel from './EffectsPanel';
import TransitionPanel from './TransitionPanel';
import TextInspectorPanel from './TextInspectorPanel';
import WebCompInspectorPanel from './WebCompInspectorPanel';
import './InspectorPanel.css';


// Vec4 Color Picker  
 
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

// Keyframe diamond button  

interface KeyframeBtnProps {
  isAnimated: boolean;
  hasKf: boolean;
  onToggle: () => void;
  onPrev: () => void;
  onNext: () => void;
}

function KeyframeBtn({ isAnimated, hasKf, onToggle, onPrev, onNext }: KeyframeBtnProps) {
  return (
    <div className="insp-kf-group">
      <button className="insp-kf-nav" disabled={!isAnimated} onClick={onPrev} title="Previous keyframe">�</button>
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
      <button className="insp-kf-nav" disabled={!isAnimated} onClick={onNext} title="Next keyframe">�</button>
    </div>
  );
}

// Keyframe Track Editor  

interface KFTrackProps {
  clipId: string;
  paramId: string;
  label: string;
  frames: number[];
  currentFrame: number;
  onRefresh: () => void;
}

const TL_H  = 48;   // timeline SVG height px
const TL_PAD = 16;  // left/right padding in frame-space

function KFTrackPanel({ clipId, paramId, label, frames, currentFrame, onRefresh }: KFTrackProps) {
  const [kfData, setKfData] = useState<KFDef[]>([]);
  const [loading, setLoading]  = useState(false);
  const [selSet, setSelSet] = useState<Set<number>>(new Set());
  const [ctxMenu,  setCtxMenu]  = useState<{ x: number; y: number; frame: number } | null>(null);
 
  const [tlZoom, setTlZoom] = useState(1);  // pixels per frame
  const [tlPan, setTlPan] = useState(0);   // left offset in frame units
  // Box selection
  const [boxSel,   setBoxSel]   = useState<{ x0: number; x1: number } | null>(null);
  // Drag-to-move
  const draggingKf = useRef<{ frames: number[]; startPx: number } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await inspectorApi.listKeyframes(clipId, paramId);
      setKfData(r.frames);
    } finally { setLoading(false); }
  }, [clipId, paramId]);

  useEffect(() => { load(); }, [load]);

  // Key bindings  
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

  // Helpers  
  const svgWidth = () => svgRef.current?.clientWidth ?? 300;
  const maxFrame = useMemo(() => {
    const all = kfData.map(k => k.frame);
    return all.length > 0 ? Math.max(...all) : 100;
  }, [kfData]);

  // pixels-per-frame  
  const ppf = useMemo(() => {
    const w = svgWidth() - TL_PAD * 2;
    return w / (maxFrame || 1) * tlZoom;
  }, [maxFrame, tlZoom]);

  const frameToX = useCallback((f: number) =>
    TL_PAD + (f - tlPan) * ppf, [ppf, tlPan]);

  const xToFrame = useCallback((px: number) =>
    Math.round((px - TL_PAD) / ppf + tlPan), [ppf, tlPan]);

  // Scroll = zoom  
  const onWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    setTlZoom(z => Math.max(0.1, Math.min(50, z * factor)));
  }, []);

  // Pan / box-select on SVG background  
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

  // Diamond drag-to-move  
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

  // Delete/copy helpers  
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

  if (loading) return <div className="insp-kftrack-loading">Loading�</div>;

  // Render  
  const playX = frameToX(currentFrame);

  return (
    <div className="insp-kftrack" onClick={e => e.stopPropagation()}>
      {/* Header */}
      <div className="insp-kftrack-header">
        <span className="insp-kftrack-title">Keyframes � {label}</span>
        <span className="insp-kftrack-count">{kfData.length} kf</span>
        <button className="insp-kftrack-zoom-btn" onClick={() => { setTlZoom(1); setTlPan(0); }} title="Reset zoom">?</button>
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
              <title>Frame {kf.frame} � {kf.interp} � {kf.value.toFixed(3)}</title>
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
                    onClick={e => { e.stopPropagation(); copyKf(kf.frame); }}>?</button>
            <button className="insp-kftrack-del" title="Delete keyframe"
                    onClick={e => { e.stopPropagation(); deleteKf(kf.frame); }}>?</button>
          </div>
        ))}
        {kfData.length === 0 && (
          <div className="insp-kftrack-empty">No keyframes yet. Click the ? diamond to add one.</div>
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

//   Blend Mode Selector  

const BLEND_MODES = [
  { value: 0,  label: 'Normal' },
  { value: 1,  label: 'Multiply' },
  { value: 2,  label: 'Screen' },
  { value: 3,  label: 'Overlay' },
  { value: 4,  label: 'Darken' },
  { value: 5,  label: 'Lighten' },
  { value: 6,  label: 'Color Dodge' },
  { value: 7,  label: 'Color Burn' },
  { value: 8,  label: 'Hard Light' },
  { value: 9,  label: 'Soft Light' },
  { value: 10, label: 'Difference' },
  { value: 11, label: 'Exclusion' },
];

function BlendModeSelector({ param, clipId, onChange }: {
  param: ParamRow;
  clipId: string;
  onChange: (id: string, value: number) => void;
}) {
  const [val, setVal] = useState(Math.round(param.value));
  useEffect(() => { setVal(Math.round(param.value)); }, [param.value]);

  const handleChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const v = parseInt(e.target.value, 10);
    setVal(v);
    await inspectorApi.setParam(clipId, 'blend_mode', v, -1);
    onChange('blend_mode', v);
  };

  return (
    <div className="insp-row insp-row--blend">
      <span className="insp-row__label">Blend Mode</span>
      <div className="insp-blend-wrap">
        <select
          className="insp-blend-select"
          value={val}
          onChange={handleChange}
          id={`blend-mode-${clipId}`}
        >
          {BLEND_MODES.map(m => (
            <option key={m.value} value={m.value}>{m.label}</option>
          ))}
        </select>
        <span className="insp-blend-arrow">?</span>
      </div>
    </div>
  );
}

//   Single param row  

interface ParamRowProps {
  param: ParamRow;
  clipId: string;
  currentFrame: number;
  onChange: (id: string, value: number) => void;
  onRefresh: () => void;
}

// ── Expression Editor ──────────────────────────────────────────────────────
interface ExprEditorProps {
  clipId: string;
  param: string;
  currentFrame: number;
  onClose: () => void;
}

function ExpressionEditor({ clipId, param, currentFrame, onClose }: ExprEditorProps) {
  const [expr,    setExpr]    = useState('');
  const [preview, setPreview] = useState<{ ok: boolean; value: number | null; error: string } | null>(null);
  const [saving,  setSaving]  = useState(false);
  const [loading, setLoading] = useState(true);
  const textRef = useRef<HTMLTextAreaElement>(null);

  // Load existing expression on mount
  useEffect(() => {
    expressionApi.get(clipId, param).then(s => {
      setExpr(s.expression);
      setLoading(false);
      setTimeout(() => textRef.current?.focus(), 50);
    }).catch(() => setLoading(false));
  }, [clipId, param]);

  const handleTest = useCallback(async () => {
    if (!expr.trim()) { setPreview(null); return; }
    try {
      const r = await expressionApi.test(clipId, param, expr, currentFrame);
      setPreview(r);
    } catch (e: any) {
      setPreview({ ok: false, value: null, error: String(e) });
    }
  }, [clipId, param, expr, currentFrame]);

  const handleApply = useCallback(async () => {
    setSaving(true);
    try {
      await expressionApi.set(clipId, param, expr);
      window.dispatchEvent(new CustomEvent('fade:timeline-changed'));
      onClose();
    } finally { setSaving(false); }
  }, [clipId, param, expr, onClose]);

  const handleClear = useCallback(async () => {
    await expressionApi.clear(clipId, param);
    window.dispatchEvent(new CustomEvent('fade:timeline-changed'));
    onClose();
  }, [clipId, param, onClose]);

  const SNIPPETS = [
    { label: 'oscillate',  code: 'sin(time * 2 * pi) * 100' },
    { label: 'wiggle',     code: 'wiggle(2, 30)' },
    { label: 'bounce',     code: 'abs(sin(time * 3)) * 200' },
    { label: 'stagger',    code: 'index * 20 + value' },
    { label: 'ease loop',  code: 'smoothstep(0, 1, (time % 2) / 2) * 100' },
    { label: 'link pos_x', code: "comp.clip('CLIP_ID').pos_x" },
  ];

  return (
    <div className="expr-editor">
      <div className="expr-editor__header">
        <span className="expr-editor__icon">ƒ</span>
        <span className="expr-editor__title">Expression — <code>{param}</code></span>
        <button className="expr-editor__close" onClick={onClose} title="Close">✕</button>
      </div>

      {loading ? (
        <div className="expr-editor__loading">Loading…</div>
      ) : (
        <>
          <textarea
            ref={textRef}
            className="expr-editor__input"
            placeholder={'e.g.  sin(time * 2 * pi) * 100'}
            value={expr}
            onChange={e => setExpr(e.target.value)}
            rows={3}
            spellCheck={false}
          />

          {/* Snippets */}
          <div className="expr-editor__snippets">
            {SNIPPETS.map(s => (
              <button
                key={s.label}
                className="expr-editor__snippet"
                onClick={() => setExpr(s.code)}
                title={s.code}
              >{s.label}</button>
            ))}
          </div>

          {/* Preview */}
          {preview && (
            <div className={`expr-editor__preview ${preview.ok ? 'ok' : 'err'}`}>
              {preview.ok
                ? <><span>@f{currentFrame}</span><strong>{preview.value?.toFixed(4)}</strong></>
                : <span className="expr-editor__err">{preview.error}</span>
              }
            </div>
          )}

          {/* Context vars reference */}
          <details className="expr-editor__ref">
            <summary>Available variables</summary>
            <ul>
              <li><code>time</code> – seconds (float)</li>
              <li><code>frame</code> – timeline frame (int)</li>
              <li><code>value</code> – keyframe value at this frame</li>
              <li><code>duration</code> – clip duration (frames)</li>
              <li><code>index</code> – unique int per clip (stagger)</li>
              <li><code>sin cos tan pi tau sqrt abs min max clamp lerp smoothstep</code></li>
              <li><code>wiggle(freq, amp)</code> – perlin shake</li>
              <li><code>comp.clip("id").pos_x</code> – link to other clip</li>
            </ul>
          </details>

          <div className="expr-editor__actions">
            <button className="expr-editor__btn expr-editor__btn--test" onClick={handleTest}>
              Test @ f{currentFrame}
            </button>
            <button
              className="expr-editor__btn expr-editor__btn--apply"
              onClick={handleApply}
              disabled={saving || !expr.trim()}
            >
              {saving ? 'Applying…' : 'Apply'}
            </button>
            <button className="expr-editor__btn expr-editor__btn--clear" onClick={handleClear}>
              Clear
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// ── Link-to-Clip Picker ───────────────────────────────────────────────────
interface LinkPickerProps {
  clipId: string;
  param: string;
  onClose: () => void;
}

function LinkToPicker({ clipId, param, onClose }: LinkPickerProps) {
  const [clips, setClips] = useState<{ clipId: string; clipType: string; label: string }[]>([]);
  const [propPick, setPropPick] = useState<string>('pos_x');
  const [selClip, setSelClip] = useState<string>('');

  useEffect(() => {
    fetch(`http://127.0.0.1:${(window as any).__FADE_PORT__ ?? 8000}/timeline/state`)
      .then(r => r.json())
      .then(data => {
        const all: { clipId: string; clipType: string; label: string }[] = [];
        (data.tracks ?? []).forEach((t: any) => {
          (t.clips ?? []).forEach((c: any) => {
            if (c.clipId !== clipId)
              all.push({ clipId: c.clipId, clipType: c.clipType ?? '?', label: c.label ?? c.clipId.slice(0,8) + '…' });
          });
        });
        setClips(all);
      }).catch(() => {});
  }, [clipId]);

  const LINK_PROPS = ['pos_x','pos_y','scale_x','scale_y','rotation','opacity'];

  const handleLink = useCallback(async () => {
    if (!selClip) return;
    const expr = `comp.clip('${selClip}').${propPick}`;
    await expressionApi.set(clipId, param, expr);
    window.dispatchEvent(new CustomEvent('fade:timeline-changed'));
    onClose();
  }, [clipId, param, selClip, propPick, onClose]);

  return (
    <div className="expr-editor expr-editor--link">
      <div className="expr-editor__header">
        <span className="expr-editor__icon">🔗</span>
        <span className="expr-editor__title">Link <code>{param}</code> to clip</span>
        <button className="expr-editor__close" onClick={onClose}>✕</button>
      </div>

      <label className="expr-editor__field-label">Source clip</label>
      <select className="expr-editor__select" value={selClip} onChange={e => setSelClip(e.target.value)}>
        <option value="">— pick a clip —</option>
        {clips.map(c => (
          <option key={c.clipId} value={c.clipId}>[{c.clipType}] {c.label}</option>
        ))}
      </select>

      <label className="expr-editor__field-label">Source property</label>
      <select className="expr-editor__select" value={propPick} onChange={e => setPropPick(e.target.value)}>
        {LINK_PROPS.map(p => <option key={p} value={p}>{p}</option>)}
      </select>

      {selClip && (
        <div className="expr-editor__preview ok">
          <span>Expression:</span>
          <code>{`comp.clip('${selClip}').${propPick}`}</code>
        </div>
      )}

      <div className="expr-editor__actions">
        <button
          className="expr-editor__btn expr-editor__btn--apply"
          onClick={handleLink}
          disabled={!selClip}
        >Link</button>
        <button className="expr-editor__btn" onClick={onClose}>Cancel</button>
      </div>
    </div>
  );
}

// ── Param Row Context Menu ─────────────────────────────────────────────────
interface ParamCtxMenuProps {
  x: number; y: number;
  hasExpr: boolean;
  onAddExpr: () => void;
  onLinkClip: () => void;
  onClearExpr: () => void;
  onClose: () => void;
}

function ParamCtxMenu({ x, y, hasExpr, onAddExpr, onLinkClip, onClearExpr, onClose }: ParamCtxMenuProps) {
  useEffect(() => {
    const close = () => onClose();
    window.addEventListener('click', close, { once: true });
    return () => window.removeEventListener('click', close);
  }, [onClose]);

  return (
    <div
      className="param-ctx-menu"
      style={{ left: x, top: y }}
      onClick={e => e.stopPropagation()}
    >
      <button className="param-ctx-menu__item" onClick={() => { onAddExpr(); onClose(); }}>
        <span className="param-ctx-menu__icon">ƒ</span>
        {hasExpr ? 'Edit Expression…' : 'Add Expression…'}
      </button>
      <button className="param-ctx-menu__item" onClick={() => { onLinkClip(); onClose(); }}>
        <span className="param-ctx-menu__icon">🔗</span>
        Link / Parent to Clip…
      </button>
      {hasExpr && (
        <>
          <div className="param-ctx-menu__sep" />
          <button className="param-ctx-menu__item param-ctx-menu__item--danger" onClick={() => { onClearExpr(); onClose(); }}>
            <span className="param-ctx-menu__icon">✕</span>
            Clear Expression
          </button>
        </>
      )}
    </div>
  );
}

// ── ParamRowWidget ────────────────────────────────────────────────────────

function ParamRowWidget({ param, clipId, currentFrame, onChange, onRefresh }: ParamRowProps) {

  if (param.id === 'blend_mode') {
    return <BlendModeSelector param={param} clipId={clipId} onChange={onChange} />;
  }

  const [localVal, setLocalVal] = useState(param.value);
  const [editing,  setEditing]  = useState(false);
  const [showTrack, setShowTrack] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Expression state — driven from param.hasExpression (batch-loaded, no extra request)
  const [showExpr,    setShowExpr]    = useState(false);   // show inline editor
  const [showLink,    setShowLink]    = useState(false);   // show link picker
  const [ctxMenu,     setCtxMenu]     = useState<{ x: number; y: number } | null>(null);
  // Local mirror of expression state so we can refresh after edits
  const [exprOverride, setExprOverride] = useState<{ hasExpression: boolean; expression: string; error: string } | null>(null);

  useEffect(() => { setLocalVal(param.value); }, [param.value]);

  // Use batch-loaded state, falling back to local override after edits
  const hasExpr  = exprOverride != null ? exprOverride.hasExpression  : (param.hasExpression ?? false);
  const exprStr  = exprOverride != null ? exprOverride.expression      : (param.expression    ?? '');
  const exprErr  = exprOverride != null ? exprOverride.error           : (param.expressionError ?? '');

  const handleSlider = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setLocalVal(parseFloat(e.target.value));
  }, []);

  const handleSliderCommit = useCallback(async () => {
    await inspectorApi.setParam(clipId, param.id, localVal, -1);
    onChange(param.id, localVal);
  }, [clipId, param.id, localVal, onChange]);

  const handleNumberCommit = useCallback(async (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      const v = parseFloat((e.target as HTMLInputElement).value);
      if (!isNaN(v)) {
        const clamped = Math.max(param.min, Math.min(param.max, v));
        setLocalVal(clamped);
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

  const handleRightClick = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setCtxMenu({ x: e.clientX, y: e.clientY });
  }, []);

  const handleClearExpr = useCallback(async () => {
    await expressionApi.clear(clipId, param.id);
    setExprOverride({ hasExpression: false, expression: '', error: '' });
    window.dispatchEvent(new CustomEvent('fade:timeline-changed'));
  }, [clipId, param.id]);

  const pct = ((localVal - param.min) / (param.max - param.min)) * 100;

  const fmtVal = (v: number) => {
    if (v % 1 === 0) return v.toFixed(0);
    if (Math.abs(v) < 10) return v.toFixed(3);
    return v.toFixed(2);
  };

  return (
    <>
      <div
        className={`insp-row${param.isAnimated ? ' insp-row--animated' : ''}${hasExpr ? ' insp-row--expr' : ''}`}
        onContextMenu={handleRightClick}
      >
        <KeyframeBtn
          isAnimated={param.isAnimated}
          hasKf={param.hasKeyframe}
          onToggle={handleKfToggle}
          onPrev={() => handleKfNav('prev')}
          onNext={() => handleKfNav('next')}
        />

        <span
          className={`insp-row__label${param.isAnimated ? ' insp-row__label--animated' : ''}${hasExpr ? ' insp-row__label--expr' : ''}`}
          title={hasExpr ? `ƒ ${exprStr}` : param.id}
          onClick={() => param.isAnimated && setShowTrack(s => !s)}
          style={{ cursor: param.isAnimated ? 'pointer' : 'default' }}
        >
          {hasExpr && <span className="insp-row__expr-badge" title="Expression active">ƒ</span>}
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
            disabled={hasExpr}
          />
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
            className={`insp-row__val${hasExpr ? ' insp-row__val--expr' : ''}`}
            onClick={() => hasExpr ? setShowExpr(true) : setEditing(true)}
            title={hasExpr ? 'Expression active — click to edit' : 'Click to enter value'}
          >
            {hasExpr ? 'ƒ(x)' : fmtVal(localVal)}
          </button>
        )}
      </div>

      {/* Inline Expression Editor */}
      {showExpr && (
        <ExpressionEditor
          clipId={clipId}
          param={param.id}
          currentFrame={currentFrame}
          onClose={() => {
            setShowExpr(false);
            // Refresh expression state from API after editing
            expressionApi.get(clipId, param.id)
              .then(s => setExprOverride({ hasExpression: s.hasExpression, expression: s.expression, error: s.error }))
              .catch(() => {});
            onRefresh();
          }}
        />
      )}

      {/* Link to Clip Picker */}
      {showLink && (
        <LinkToPicker
          clipId={clipId}
          param={param.id}
          onClose={() => {
            setShowLink(false);
            expressionApi.get(clipId, param.id)
              .then(s => setExprOverride({ hasExpression: s.hasExpression, expression: s.expression, error: s.error }))
              .catch(() => {});
            onRefresh();
          }}
        />
      )}

      {/* Right-click context menu */}
      {ctxMenu && (
        <ParamCtxMenu
          x={ctxMenu.x}
          y={ctxMenu.y}
          hasExpr={hasExpr}
          onAddExpr={() => setShowExpr(true)}
          onLinkClip={() => setShowLink(true)}
          onClearExpr={handleClearExpr}
          onClose={() => setCtxMenu(null)}
        />
      )}

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


// Group header  

function GroupHeader({ label, open, onToggle }: { label: string; open: boolean; onToggle: () => void }) {
  return (
    <button className="insp-group-header" onClick={onToggle}>
      <span className={`insp-group-header__arrow${open ? ' open' : ''}`}>?</span>
      {label}
    </button>
  );
}

//   Masks Panel  

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
              <span className="insp-mask-row__icon">?</span>
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
              >?</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

//   Main Inspector Panel  

 
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
  const { selected, setSelected } = useSelection();
  const [data, setData]       = useState<ClipParams | null>(null);
  const [currentFrame, setCF] = useState(0);
  const [loading, setLoading] = useState(false);
  const [groups, setGroups]   = useState<Record<string, boolean>>({});

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    const handler = (e: Event) => {
      const frame = (e as CustomEvent<number>).detail;
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => setCF(frame), 200);
    };
    window.addEventListener('fade:frame', handler);
    window.addEventListener('fade:seek',  handler);
    return () => {
      if (timer) clearTimeout(timer);
      window.removeEventListener('fade:frame', handler);
      window.removeEventListener('fade:seek',  handler);
    };
  }, []);

  const currentFrameRef = useRef(currentFrame);
  currentFrameRef.current = currentFrame;

  const refresh = useCallback(async () => {
    if (!selected || selected.type !== 'clip') { setData(null); return; }
    setLoading(true);
    try {
      const d = await inspectorApi.getParams(selected.clipId, currentFrameRef.current);
      setData(d);
      setGroups(prev => {
        const next = { ...prev };
        [...new Set(d.params.map(p => p.group))].forEach(g => { if (!(g in next)) next[g] = true; });
        return next;
      });
    } catch (err: any) {
      
      const msg = String(err?.message ?? err);
      if (msg.includes('not found') || msg.includes('"detail"')) {
        setData(null);
        setSelected(null);  // deselect the dead clip
      } else {
        console.error('[Inspector] fetch error', err);
      }
    } finally { setLoading(false); }
  }, [selected, setSelected]);

  useEffect(() => { refresh(); }, [selected?.type === 'clip' ? selected.clipId : null, currentFrame]);

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
        <div className="insp-empty__icon">?</div>
        <div className="insp-empty__text">Select a clip or transition to inspect</div>
      </div>
    );
  }

  if (selected.type === 'transition') {
    return <TransitionPanel selected={selected.data} />;
  }

  if (loading && !data) {
    return (
      <div className="insp-empty">
        <div className="insp-empty__spinner" />
        <div className="insp-empty__text">Loading�</div>
      </div>
    );
  }

  if (!data) return null;

  // Text clips ? dedicated text inspector
  const isText = data.clipType === 'TextClip'
    || (selected.type === 'clip' && selected.clipType === 'text');

  if (isText) {
    return (
      <TextInspectorPanel
        clipId={data.clipId}
        clipName={selected.type === 'clip' ? selected.clipName : ''}
        trackIndex={selected.type === 'clip' ? selected.trackIndex : 0}
      />
    );
  }

  // WebComp clips ? generic params  
  const isWebComp = data.clipType === 'WebCompClip'
    || (selected.type === 'clip' && (selected as any).clipType === 'webcomp')
    || data.clipType.toLowerCase().includes('webcomp');

  return (
    <div className="insp-root">
      {/* Clip header */}
      <div className="insp-clip-header">
        <div className="insp-clip-header__badge">{data.clipType.replace('Clip', '')}</div>
        <div className="insp-clip-header__name">{selected.clipName}</div>
        <div className="insp-clip-header__meta">
          {data.duration} fr � start {data.startFrame} � track {selected.trackIndex + 1}
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
                  {[...vec4Groups.entries()].map(([base, [rP, gP, bP, aP]]) => (
                    <Vec4ColorPicker
                      key={base}
                      label={base.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                      r={rP.value} g={gP.value} b={bP.value} a={aP.value}
                      onChange={(r, g, b, a) => handleVec4Change(data.clipId, base, r, g, b, a)}
                    />
                  ))}
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

        {/* Effects section */}
        <InspectorEffectsPanel clipId={data.clipId} />
      </div>

      
      {isWebComp && (
        <WebCompInspectorPanel
          clipId={data.clipId}
          clipName={selected.type === 'clip' ? selected.clipName : ''}
          trackIndex={selected.type === 'clip' ? selected.trackIndex : 0}
          startFrame={data.startFrame}
          duration={data.duration}
        />
      )}
    </div>
  );
}


// Inspector Effects Panel  

function InspectorEffectsPanel({ clipId }: { clipId: string }) {
  const [effects, setEffects] = useState<EffectInfo[]>([]);
  const [open, setOpen] = useState(true);

  const load = useCallback(async () => {
    try {
      const r = await effectsApi.list(clipId);
      setEffects(r.effects ?? []);
    } catch { setEffects([]); }
  }, [clipId]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const handler = (e: Event) => {
      const targetId = (e as CustomEvent<string>).detail;
      if (!targetId || targetId === clipId) load();
    };
    window.addEventListener('fade:effects-changed', handler);
    return () => window.removeEventListener('fade:effects-changed', handler);
  }, [clipId, load]);

  if (effects.length === 0) return null;

  return (
    <div className="insp-group">
      <GroupHeader
        label={`Effects (${effects.length})`}
        open={open}
        onToggle={() => setOpen(o => !o)}
      />
      {open && (
        <div className="insp-group__body">
          {effects.map(eff => (
            <div key={eff.effectId} className="insp-effect">
              <div className="insp-effect__header">
                <input
                  type="checkbox"
                  checked={eff.enabled}
                  onChange={async () => {
                    await effectsApi.patch(clipId, eff.effectId, { enabled: !eff.enabled });
                    load();
                  }}
                  className="insp-effect__check"
                />
                <span className="insp-effect__name">{eff.name}</span>
                <button
                  className="insp-effect__del"
                  onClick={async () => { await effectsApi.remove(clipId, eff.effectId); load(); }}
                  title="Remove effect"
                >?</button>
              </div>
              <div className="insp-effect__params">
                {Object.entries(eff.params)
                  .filter(([, def]: [string, EffectParamDef]) =>
                    def.type === 'FloatSlider' || def.type === 'ToggleBool' || def.type === 'IntSlider')
                  .map(([pid, def]: [string, EffectParamDef]) => {
                    const val = Array.isArray(def.value) ? (def.value as number[])[0] : def.value as number;
                    const min = Array.isArray(def.min) ? (def.min as number[])[0] : def.min as number;
                    const max = Array.isArray(def.max) ? (def.max as number[])[0] : def.max as number;
                    const pct = ((val - min) / (max - min)) * 100;
                    return (
                      <div key={pid} className="efx-param">
                        <label className="efx-param__label">{def.displayName}</label>
                        <div className="efx-param__track">
                          <div className="efx-param__fill" style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
                          <input
                            type="range" min={min} max={max} step={(max - min) / 400}
                            defaultValue={val}
                            className="efx-param__slider"
                            onMouseUp={async e => {
                              const v = parseFloat((e.target as HTMLInputElement).value);
                              await effectsApi.patch(clipId, eff.effectId, { params: { [pid]: v } });
                              load();
                            }}
                          />
                        </div>
                        <span className="efx-param__val">{val.toFixed(2)}</span>
                      </div>
                    );
                  })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
