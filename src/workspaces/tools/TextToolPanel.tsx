import React, { useState, useEffect, useCallback } from 'react';
import './ToolPanels.css';
import { textApi, listFonts, type TextStyle } from '../../api/toolsApi';

interface Props {
  clipId?: string;    // if set → patch existing; if null → create new on click
  currentFrame: number;
  duration?: number;
  style?: TextStyle;
  onCreated?: (clip: any) => void;
  onUpdated?: (clip: any) => void;
}

const DEFAULT_STYLE: TextStyle = {
  text:          'New Text',
  fontFamily:    'Arial',
  fontSize:      48,
  bold:          false,
  italic:        false,
  alignment:     'left',
  lineHeight:    1.2,
  letterSpacing: 0,
  color:         [1, 1, 1, 1],
  strokeWidth:   0,
  strokeColor:   [0, 0, 0, 1],
  shadowEnabled: false,
  shadowColor:   [0, 0, 0, 0.6],
  shadowOffsetX: 4,
  shadowOffsetY: 4,
  shadowBlur:    6,
  bgEnabled:     false,
  bgColor:       [0, 0, 0, 0.5],
  bgPaddingX:    20,
  bgPaddingY:    10,
  bgCornerRadius: 0,
};

function toHex(rgba: [number, number, number, number]): string {
  const [r, g, b] = rgba.map(v => Math.round(v * 255).toString(16).padStart(2, '0'));
  return `#${r}${g}${b}`;
}

function fromHex(hex: string, alpha = 1): [number, number, number, number] {
  const r = parseInt(hex.slice(1, 3), 16) / 255;
  const g = parseInt(hex.slice(3, 5), 16) / 255;
  const b = parseInt(hex.slice(5, 7), 16) / 255;
  return [r, g, b, alpha];
}

export default function TextToolPanel({ clipId, currentFrame, duration = 150, style: initStyle, onCreated, onUpdated }: Props) {
  const [s, setS]         = useState<TextStyle>({ ...DEFAULT_STYLE, ...initStyle });
  const [fonts, setFonts] = useState<string[]>(['Arial', 'Times New Roman', 'Verdana', 'Georgia']);
  const [saving, setSaving] = useState(false);

  useEffect(() => { listFonts().then(f => f.length > 0 && setFonts(f)); }, []);

  const update = useCallback((delta: Partial<TextStyle>) => {
    setS(prev => ({ ...prev, ...delta }));
  }, []);

  const apply = useCallback(async () => {
    setSaving(true);
    try {
      if (clipId) {
        const clip = await textApi.update(clipId, s);
        onUpdated?.(clip);
      } else {
        const clip = await textApi.add(currentFrame, duration, s);
        onCreated?.(clip);
      }
    } finally {
      setSaving(false);
    }
  }, [clipId, s, currentFrame, duration]);

  return (
    <div className="tp-panel">
      <div className="tp-header">
        <span className="tp-icon">T</span>
        <span className="tp-title">Text</span>
      </div>

      {/* Content */}
      <section className="tp-section">
        <h3 className="tp-section-title">Content</h3>
        <textarea
          id="tp-text"
          className="tp-textarea"
          value={s.text ?? ''}
          onChange={e => update({ text: e.target.value })}
          rows={3}
          placeholder="Enter text…"
        />
      </section>

      {/* Font */}
      <section className="tp-section">
        <h3 className="tp-section-title">Font</h3>
        <div className="tp-row">
          <label className="tp-label">Family</label>
          <select id="tp-font-family" className="tp-select"
            value={s.fontFamily} onChange={e => update({ fontFamily: e.target.value })}>
            {fonts.map(f => <option key={f} value={f}>{f}</option>)}
          </select>
        </div>
        <div className="tp-row">
          <label className="tp-label">Size</label>
          <input id="tp-font-size" type="number" className="tp-input" min={6} max={400}
            value={s.fontSize} onChange={e => update({ fontSize: +e.target.value })} />
          <div className="tp-toggles">
            <button id="tp-bold" className={`tp-toggle${s.bold ? ' tp-toggle--on' : ''}`}
              onClick={() => update({ bold: !s.bold })}>B</button>
            <button id="tp-italic" className={`tp-toggle${s.italic ? ' tp-toggle--on' : ''}`}
              onClick={() => update({ italic: !s.italic })}>I</button>
          </div>
        </div>
        <div className="tp-row">
          <label className="tp-label">Align</label>
          <div className="tp-toggles">
            {(['left', 'center', 'right'] as const).map(a => (
              <button key={a} id={`tp-align-${a}`}
                className={`tp-toggle${s.alignment === a ? ' tp-toggle--on' : ''}`}
                onClick={() => update({ alignment: a })}>
                {a === 'left' ? '≡L' : a === 'center' ? '≡C' : '≡R'}
              </button>
            ))}
          </div>
        </div>
        <div className="tp-row">
          <label className="tp-label">Line H</label>
          <input id="tp-line-h" type="range" className="tp-range" min={0.5} max={3} step={0.05}
            value={s.lineHeight} onChange={e => update({ lineHeight: +e.target.value })} />
          <span className="tp-badge">{s.lineHeight?.toFixed(2)}</span>
        </div>
        <div className="tp-row">
          <label className="tp-label">Tracking</label>
          <input id="tp-tracking" type="range" className="tp-range" min={-20} max={40} step={0.5}
            value={s.letterSpacing} onChange={e => update({ letterSpacing: +e.target.value })} />
          <span className="tp-badge">{s.letterSpacing}</span>
        </div>
      </section>

      {/* Fill */}
      <section className="tp-section">
        <h3 className="tp-section-title">Fill Color</h3>
        <div className="tp-row">
          <label className="tp-label">Color</label>
          <input id="tp-fill-color" type="color"
            value={toHex(s.color as any ?? [1,1,1,1])}
            onChange={e => update({ color: fromHex(e.target.value, s.color?.[3] ?? 1) })} />
          <input type="range" className="tp-range" min={0} max={1} step={0.01}
            value={s.color?.[3] ?? 1}
            onChange={e => update({ color: [...(s.color ?? [1,1,1]).slice(0,3), +e.target.value] as any })} />
          <span className="tp-badge">{Math.round((s.color?.[3] ?? 1) * 100)}%</span>
        </div>
      </section>

      {/* Stroke */}
      <section className="tp-section">
        <h3 className="tp-section-title">Stroke</h3>
        <div className="tp-row">
          <label className="tp-label">Width</label>
          <input id="tp-stroke-w" type="range" className="tp-range" min={0} max={20} step={0.5}
            value={s.strokeWidth} onChange={e => update({ strokeWidth: +e.target.value })} />
          <span className="tp-badge">{s.strokeWidth}px</span>
        </div>
        {(s.strokeWidth ?? 0) > 0 && (
          <div className="tp-row">
            <label className="tp-label">Color</label>
            <input id="tp-stroke-color" type="color"
              value={toHex(s.strokeColor as any ?? [0,0,0,1])}
              onChange={e => update({ strokeColor: fromHex(e.target.value, 1) })} />
          </div>
        )}
      </section>

      {/* Shadow */}
      <section className="tp-section">
        <div className="tp-row">
          <label className="tp-label">Shadow</label>
          <button id="tp-shadow-toggle"
            className={`tp-toggle${s.shadowEnabled ? ' tp-toggle--on' : ''}`}
            onClick={() => update({ shadowEnabled: !s.shadowEnabled })}>
            {s.shadowEnabled ? 'On' : 'Off'}
          </button>
        </div>
        {s.shadowEnabled && <>
          <div className="tp-row">
            <label className="tp-label">Color</label>
            <input id="tp-shadow-color" type="color"
              value={toHex(s.shadowColor as any ?? [0,0,0,0.6])}
              onChange={e => update({ shadowColor: fromHex(e.target.value, s.shadowColor?.[3] ?? 0.6) })} />
          </div>
          <div className="tp-row">
            <label className="tp-label">Offset X</label>
            <input type="range" className="tp-range" min={-50} max={50} step={0.5}
              value={s.shadowOffsetX} onChange={e => update({ shadowOffsetX: +e.target.value })} />
            <span className="tp-badge">{s.shadowOffsetX}</span>
          </div>
          <div className="tp-row">
            <label className="tp-label">Offset Y</label>
            <input type="range" className="tp-range" min={-50} max={50} step={0.5}
              value={s.shadowOffsetY} onChange={e => update({ shadowOffsetY: +e.target.value })} />
            <span className="tp-badge">{s.shadowOffsetY}</span>
          </div>
          <div className="tp-row">
            <label className="tp-label">Blur</label>
            <input type="range" className="tp-range" min={0} max={40} step={0.5}
              value={s.shadowBlur} onChange={e => update({ shadowBlur: +e.target.value })} />
            <span className="tp-badge">{s.shadowBlur}</span>
          </div>
        </>}
      </section>

      {/* Background */}
      <section className="tp-section">
        <div className="tp-row">
          <label className="tp-label">BG Box</label>
          <button id="tp-bg-toggle"
            className={`tp-toggle${s.bgEnabled ? ' tp-toggle--on' : ''}`}
            onClick={() => update({ bgEnabled: !s.bgEnabled })}>
            {s.bgEnabled ? 'On' : 'Off'}
          </button>
        </div>
        {s.bgEnabled && <>
          <div className="tp-row">
            <label className="tp-label">Color</label>
            <input type="color"
              value={toHex(s.bgColor as any ?? [0,0,0,0.5])}
              onChange={e => update({ bgColor: fromHex(e.target.value, s.bgColor?.[3] ?? 0.5) })} />
          </div>
          <div className="tp-row">
            <label className="tp-label">Radius</label>
            <input type="range" className="tp-range" min={0} max={40} step={1}
              value={s.bgCornerRadius} onChange={e => update({ bgCornerRadius: +e.target.value })} />
            <span className="tp-badge">{s.bgCornerRadius}px</span>
          </div>
        </>}
      </section>

      <div className="tp-footer">
        {saving && <span className="tp-saving">Applying…</span>}
        <button id="tp-apply" className="tp-btn" onClick={apply}>
          {clipId ? 'Update' : 'Add to Timeline'}
        </button>
      </div>
    </div>
  );
}
