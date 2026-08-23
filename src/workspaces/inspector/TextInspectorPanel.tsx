import React, { useState, useEffect, useCallback, useRef } from 'react';
import './TextInspectorPanel.css';

function port(): number { return (window as any).__FADE_PORT__ ?? 8000; }
const base = () => `http://127.0.0.1:${port()}`;

async function patchTextStyle(clipId: string, style: Record<string, unknown>) {
  try {
    const r = await fetch(`${base()}/clips/text/${clipId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ style }),
    });
    if (r.ok) {
      // Only trigger re-render after the server has confirmed the update
      window.dispatchEvent(new CustomEvent('fade:render-now'));
    }
  } catch {
    // backend not ready
  }
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface TextStyle {
  text: string;
  fontFamily: string;
  fontSize: number;
  bold: boolean;
  italic: boolean;
  alignment: 'left' | 'center' | 'right';
  lineHeight: number;
  letterSpacing: number;
  allCaps: boolean;
  color: [number, number, number, number];
  strokeColor: [number, number, number, number];
  strokeWidth: number;
  shadowEnabled: boolean;
  shadowColor: [number, number, number, number];
  shadowOffsetX: number;
  shadowOffsetY: number;
  shadowBlur: number;
  bgEnabled: boolean;
  bgColor: [number, number, number, number];
  bgPaddingX: number;
  bgPaddingY: number;
  bgCornerRadius: number;
}

const DEFAULT_STYLE: TextStyle = {
  text: 'New Text',
  fontFamily: 'Arial',
  fontSize: 48,
  bold: false,
  italic: false,
  alignment: 'left',
  lineHeight: 1.2,
  letterSpacing: 0,
  allCaps: false,
  color: [1, 1, 1, 1],
  strokeColor: [0, 0, 0, 1],
  strokeWidth: 0,
  shadowEnabled: false,
  shadowColor: [0, 0, 0, 0.6],
  shadowOffsetX: 4,
  shadowOffsetY: 4,
  shadowBlur: 6,
  bgEnabled: false,
  bgColor: [0, 0, 0, 0.5],
  bgPaddingX: 20,
  bgPaddingY: 10,
  bgCornerRadius: 0,
};

const COMMON_FONTS = [
  'Arial', 'Arial Black', 'Comic Sans MS', 'Courier New', 'Georgia',
  'Impact', 'Lucida Console', 'Palatino Linotype', 'Tahoma',
  'Times New Roman', 'Trebuchet MS', 'Verdana',
  'Segoe UI', 'Calibri', 'Cambria',
];

// ── Util ──────────────────────────────────────────────────────────────────────

function vecToHex([r, g, b]: [number, number, number, number]): string {
  const h = (v: number) => Math.round(Math.max(0, Math.min(1, v)) * 255).toString(16).padStart(2, '0');
  return `#${h(r)}${h(g)}${h(b)}`;
}

function hexToVec(hex: string, a: number): [number, number, number, number] {
  const r = parseInt(hex.slice(1, 3), 16) / 255;
  const g = parseInt(hex.slice(3, 5), 16) / 255;
  const b = parseInt(hex.slice(5, 7), 16) / 255;
  return [r, g, b, a];
}

// ── Sub-components ────────────────────────────────────────────────────────────

interface ColorRowProps {
  label: string;
  value: [number, number, number, number];
  onChange: (v: [number, number, number, number]) => void;
}

function ColorRow({ label, value, onChange }: ColorRowProps) {
  const hex = vecToHex(value);
  return (
    <div className="ti-row">
      <span className="ti-label">{label}</span>
      <div className="ti-color-wrap">
        <label className="ti-swatch" style={{ background: hex }}>
          <input
            type="color"
            value={hex}
            onChange={e => onChange(hexToVec(e.target.value, value[3]))}
          />
        </label>
        <span className="ti-hex">{hex.toUpperCase()}</span>
        <input
          type="range" min={0} max={1} step={0.01}
          value={value[3]}
          className="ti-alpha"
          style={{ background: `linear-gradient(to right, transparent, ${hex})` }}
          onChange={e => onChange([value[0], value[1], value[2], parseFloat(e.target.value)])}
        />
        <span className="ti-alpha-val">{Math.round(value[3] * 100)}%</span>
      </div>
    </div>
  );
}

interface NumberRowProps {
  label: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (v: number) => void;
}

function NumberRow({ label, value, min = 0, max = 400, step = 1, onChange }: NumberRowProps) {
  const [local, setLocal] = useState(String(value));
  useEffect(() => setLocal(String(Math.round(value * 1000) / 1000)), [value]);

  return (
    <div className="ti-row">
      <span className="ti-label">{label}</span>
      <input
        type="range" min={min} max={max} step={step}
        value={value}
        className="ti-slider"
        onChange={e => onChange(parseFloat(e.target.value))}
      />
      <input
        type="number"
        className="ti-num"
        value={local}
        min={min} max={max} step={step}
        onChange={e => setLocal(e.target.value)}
        onBlur={() => {
          const v = parseFloat(local);
          if (!isNaN(v)) onChange(Math.max(min, Math.min(max, v)));
        }}
        onKeyDown={e => {
          if (e.key === 'Enter') {
            const v = parseFloat(local);
            if (!isNaN(v)) onChange(Math.max(min, Math.min(max, v)));
          }
        }}
      />
    </div>
  );
}

function SectionHeader({ label, open, onToggle }: { label: string; open: boolean; onToggle: () => void }) {
  return (
    <button className="ti-section-hdr" onClick={onToggle}>
      <span className={`ti-arrow${open ? ' open' : ''}`}>▶</span>
      {label}
    </button>
  );
}

// ── Text Animator ─────────────────────────────────────────────────────────────
// Simple per-character animation: offset, scale, opacity with easing controls

interface AnimatorState {
  enabled: boolean;
  mode: 'characters' | 'words' | 'lines';
  property: 'opacity' | 'offset_y' | 'offset_x' | 'scale';
  from: number;
  to: number;
  easing: 'linear' | 'ease_in' | 'ease_out' | 'ease_both';
  startOffset: number; // 0-1
  endOffset: number;   // 0-1
}

const DEFAULT_ANIMATOR: AnimatorState = {
  enabled: false,
  mode: 'characters',
  property: 'opacity',
  from: 0,
  to: 1,
  easing: 'ease_both',
  startOffset: 0,
  endOffset: 1,
};

interface TextAnimatorProps {
  clipId: string;
  animator: AnimatorState;
  onChange: (a: AnimatorState) => void;
}

function TextAnimator({ clipId, animator, onChange }: TextAnimatorProps) {
  const [open, setOpen] = useState(false);

  const set = (patch: Partial<AnimatorState>) => {
    const next = { ...animator, ...patch };
    onChange(next);
    patchTextStyle(clipId, { animator: next });
  };

  const propRanges: Record<string, [number, number]> = {
    opacity:  [0, 1],
    offset_y: [-500, 500],
    offset_x: [-500, 500],
    scale:    [0, 5],
  };

  const [lo, hi] = propRanges[animator.property] ?? [0, 1];

  return (
    <div className="ti-group">
      <SectionHeader label="Text Animator" open={open} onToggle={() => setOpen(o => !o)} />
      {open && (
        <div className="ti-group-body">
          <div className="ti-row">
            <span className="ti-label">Enabled</span>
            <label className="ti-toggle">
              <input type="checkbox" checked={animator.enabled} onChange={e => set({ enabled: e.target.checked })} />
              <span className="ti-toggle-track" />
            </label>
          </div>

          <div className="ti-row">
            <span className="ti-label">Animate By</span>
            <select className="ti-select" value={animator.mode} onChange={e => set({ mode: e.target.value as any })}>
              <option value="characters">Characters</option>
              <option value="words">Words</option>
              <option value="lines">Lines</option>
            </select>
          </div>

          <div className="ti-row">
            <span className="ti-label">Property</span>
            <select className="ti-select" value={animator.property} onChange={e => set({ property: e.target.value as any })}>
              <option value="opacity">Opacity</option>
              <option value="offset_y">Offset Y</option>
              <option value="offset_x">Offset X</option>
              <option value="scale">Scale</option>
            </select>
          </div>

          <NumberRow label="From" value={animator.from} min={lo} max={hi} step={0.01}
            onChange={v => set({ from: v })} />
          <NumberRow label="To" value={animator.to} min={lo} max={hi} step={0.01}
            onChange={v => set({ to: v })} />

          <div className="ti-row">
            <span className="ti-label">Easing</span>
            <select className="ti-select" value={animator.easing} onChange={e => set({ easing: e.target.value as any })}>
              <option value="linear">Linear</option>
              <option value="ease_in">Ease In</option>
              <option value="ease_out">Ease Out</option>
              <option value="ease_both">Ease Both</option>
            </select>
          </div>

          <div className="ti-row">
            <span className="ti-label">Start %</span>
            <input type="range" min={0} max={1} step={0.01} value={animator.startOffset}
              className="ti-slider"
              onChange={e => set({ startOffset: parseFloat(e.target.value) })} />
            <span className="ti-num-static">{Math.round(animator.startOffset * 100)}%</span>
          </div>

          <div className="ti-row">
            <span className="ti-label">End %</span>
            <input type="range" min={0} max={1} step={0.01} value={animator.endOffset}
              className="ti-slider"
              onChange={e => set({ endOffset: parseFloat(e.target.value) })} />
            <span className="ti-num-static">{Math.round(animator.endOffset * 100)}%</span>
          </div>

          <div className="ti-animator-preview">
            <div className="ti-animator-preview__bar"
              style={{
                left: `${animator.startOffset * 100}%`,
                width: `${(animator.endOffset - animator.startOffset) * 100}%`,
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

interface Props {
  clipId: string;
  clipName: string;
  trackIndex: number;
}

export default function TextInspectorPanel({ clipId, clipName, trackIndex }: Props) {
  const [style, setStyle] = useState<TextStyle>(DEFAULT_STYLE);
  const [animator, setAnimator] = useState<AnimatorState>(DEFAULT_ANIMATOR);
  const [loading, setLoading] = useState(true);

  // Section open states
  const [secContent,  setSecContent]  = useState(true);
  const [secFont,     setSecFont]     = useState(true);
  const [secFill,     setSecFill]     = useState(true);
  const [secStroke,   setSecStroke]   = useState(false);
  const [secShadow,   setSecShadow]   = useState(false);
  const [secBg,       setSecBg]       = useState(false);

  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Fetch current style from Python
  useEffect(() => {
    setLoading(true);
    fetch(`${base()}/clips/text/${clipId}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data) return;
        const s = data.style ?? {};
        setStyle({ ...DEFAULT_STYLE, ...s });
        if (s.animator) setAnimator({ ...DEFAULT_ANIMATOR, ...s.animator });
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [clipId]);

  // Debounced patch — avoids hammering the server while dragging sliders
  const patch = useCallback((patch: Partial<TextStyle>) => {
    setStyle(prev => {
      const next = { ...prev, ...patch };
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
      debounceTimer.current = setTimeout(() => patchTextStyle(clipId, next), 80);
      return next;
    });
  }, [clipId]);

  if (loading) {
    return (
      <div className="ti-root">
        <div className="ti-loading"><span className="ti-spinner" />Loading text…</div>
      </div>
    );
  }

  return (
    <div className="ti-root">
      {/* Header */}
      <div className="ti-header">
        <span className="ti-header__badge">T</span>
        <span className="ti-header__name">{clipName}</span>
        <span className="ti-header__meta">Track {trackIndex + 1}</span>
      </div>

      <div className="ti-scroll">

        {/* Content */}
        <div className="ti-group">
          <SectionHeader label="Content" open={secContent} onToggle={() => setSecContent(o => !o)} />
          {secContent && (
            <div className="ti-group-body">
              <textarea
                className="ti-textarea"
                value={style.text}
                rows={3}
                onChange={e => patch({ text: e.target.value })}
                placeholder="Type your text…"
              />
            </div>
          )}
        </div>

        {/* Font */}
        <div className="ti-group">
          <SectionHeader label="Font" open={secFont} onToggle={() => setSecFont(o => !o)} />
          {secFont && (
            <div className="ti-group-body">
              <div className="ti-row">
                <span className="ti-label">Family</span>
                <select
                  className="ti-select ti-select--wide"
                  value={style.fontFamily}
                  onChange={e => patch({ fontFamily: e.target.value })}
                >
                  {COMMON_FONTS.map(f => (
                    <option key={f} value={f} style={{ fontFamily: f }}>{f}</option>
                  ))}
                </select>
              </div>

              <NumberRow label="Size" value={style.fontSize} min={4} max={400} step={1}
                onChange={v => patch({ fontSize: v })} />

              <div className="ti-row">
                <span className="ti-label">Style</span>
                <div className="ti-btn-row">
                  <button
                    className={`ti-style-btn${style.bold ? ' active' : ''}`}
                    title="Bold"
                    onClick={() => patch({ bold: !style.bold })}
                  ><b>B</b></button>
                  <button
                    className={`ti-style-btn${style.italic ? ' active' : ''}`}
                    title="Italic"
                    onClick={() => patch({ italic: !style.italic })}
                  ><i>I</i></button>
                  <button
                    className={`ti-style-btn${style.allCaps ? ' active' : ''}`}
                    title="All Caps"
                    onClick={() => patch({ allCaps: !style.allCaps })}
                  >AA</button>
                </div>
              </div>

              <div className="ti-row">
                <span className="ti-label">Align</span>
                <div className="ti-btn-row">
                  {(['left', 'center', 'right'] as const).map(a => (
                    <button
                      key={a}
                      className={`ti-align-btn${style.alignment === a ? ' active' : ''}`}
                      title={a}
                      onClick={() => patch({ alignment: a })}
                    >
                      {a === 'left' ? '⬛◻◻' : a === 'center' ? '◻⬛◻' : '◻◻⬛'}
                    </button>
                  ))}
                </div>
              </div>

              <NumberRow label="Line Height" value={style.lineHeight} min={0.5} max={4} step={0.05}
                onChange={v => patch({ lineHeight: v })} />
              <NumberRow label="Tracking" value={style.letterSpacing} min={-20} max={200} step={0.5}
                onChange={v => patch({ letterSpacing: v })} />
            </div>
          )}
        </div>

        {/* Fill */}
        <div className="ti-group">
          <SectionHeader label="Fill" open={secFill} onToggle={() => setSecFill(o => !o)} />
          {secFill && (
            <div className="ti-group-body">
              <ColorRow
                label="Color"
                value={style.color}
                onChange={v => patch({ color: v })}
              />
            </div>
          )}
        </div>

        {/* Stroke */}
        <div className="ti-group">
          <SectionHeader label="Stroke" open={secStroke} onToggle={() => setSecStroke(o => !o)} />
          {secStroke && (
            <div className="ti-group-body">
              <ColorRow
                label="Color"
                value={style.strokeColor}
                onChange={v => patch({ strokeColor: v })}
              />
              <NumberRow label="Width" value={style.strokeWidth} min={0} max={50} step={0.5}
                onChange={v => patch({ strokeWidth: v })} />
            </div>
          )}
        </div>

        {/* Shadow */}
        <div className="ti-group">
          <div className="ti-section-hdr-with-toggle">
            <SectionHeader label="Shadow" open={secShadow} onToggle={() => setSecShadow(o => !o)} />
            <label className="ti-toggle ti-toggle--inline">
              <input type="checkbox" checked={style.shadowEnabled}
                onChange={e => patch({ shadowEnabled: e.target.checked })} />
              <span className="ti-toggle-track" />
            </label>
          </div>
          {secShadow && style.shadowEnabled && (
            <div className="ti-group-body">
              <ColorRow
                label="Color"
                value={style.shadowColor}
                onChange={v => patch({ shadowColor: v })}
              />
              <NumberRow label="Offset X" value={style.shadowOffsetX} min={-100} max={100} step={1}
                onChange={v => patch({ shadowOffsetX: v })} />
              <NumberRow label="Offset Y" value={style.shadowOffsetY} min={-100} max={100} step={1}
                onChange={v => patch({ shadowOffsetY: v })} />
              <NumberRow label="Blur" value={style.shadowBlur} min={0} max={100} step={1}
                onChange={v => patch({ shadowBlur: v })} />
            </div>
          )}
        </div>

        {/* Background Box */}
        <div className="ti-group">
          <div className="ti-section-hdr-with-toggle">
            <SectionHeader label="Background" open={secBg} onToggle={() => setSecBg(o => !o)} />
            <label className="ti-toggle ti-toggle--inline">
              <input type="checkbox" checked={style.bgEnabled}
                onChange={e => patch({ bgEnabled: e.target.checked })} />
              <span className="ti-toggle-track" />
            </label>
          </div>
          {secBg && style.bgEnabled && (
            <div className="ti-group-body">
              <ColorRow
                label="Color"
                value={style.bgColor}
                onChange={v => patch({ bgColor: v })}
              />
              <NumberRow label="Padding X" value={style.bgPaddingX} min={0} max={200} step={1}
                onChange={v => patch({ bgPaddingX: v })} />
              <NumberRow label="Padding Y" value={style.bgPaddingY} min={0} max={200} step={1}
                onChange={v => patch({ bgPaddingY: v })} />
              <NumberRow label="Corner Radius" value={style.bgCornerRadius} min={0} max={100} step={1}
                onChange={v => patch({ bgCornerRadius: v })} />
            </div>
          )}
        </div>

        {/* Text Animator */}
        <TextAnimator
          clipId={clipId}
          animator={animator}
          onChange={setAnimator}
        />

      </div>
    </div>
  );
}
