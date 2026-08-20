import React, { useState, useCallback } from 'react';
import './ToolPanels.css';
import { shapeApi, type ShapeStyle, type ShapeType } from '../../api/toolsApi';

interface Props {
  clipId?: string;
  currentFrame: number;
  duration?: number;
  style?: ShapeStyle;
  onCreated?: (clip: any) => void;
  onUpdated?: (clip: any) => void;
}

const SHAPE_TYPES: { type: ShapeType; label: string; icon: string }[] = [
  { type: 'rect',    label: 'Rectangle', icon: '▬' },
  { type: 'circle',  label: 'Circle',    icon: '●' },
  { type: 'ellipse', label: 'Ellipse',   icon: '⬭' },
  { type: 'star',    label: 'Star',      icon: '★' },
  { type: 'polygon', label: 'Polygon',   icon: '⬡' },
  { type: 'line',    label: 'Line',      icon: '╱' },
  { type: 'arc',     label: 'Arc',       icon: '⌒' },
];

const DEFAULT_STYLE: ShapeStyle = {
  shapeType:   'rect',
  width:       200,
  height:      120,
  cornerRadius: 0,
  fillColor:   [0.4, 0.4, 1.0, 1.0],
  fillOpacity:  1.0,
  strokeColor:  [1, 1, 1, 1],
  strokeWidth:  0,
  strokeStyle:  'center',
  shadowEnabled: false,
  shadowColor:  [0, 0, 0, 0.75],
  shadowAngle:  135,
  shadowDistance: 10,
  shadowBlur:   5,
};

function toHex(rgba: number[]): string {
  return '#' + rgba.slice(0, 3).map(v => Math.round(v * 255).toString(16).padStart(2, '0')).join('');
}
function fromHex(hex: string, alpha = 1): [number, number, number, number] {
  return [
    parseInt(hex.slice(1, 3), 16) / 255,
    parseInt(hex.slice(3, 5), 16) / 255,
    parseInt(hex.slice(5, 7), 16) / 255,
    alpha,
  ];
}

export default function ShapeToolPanel({ clipId, currentFrame, duration = 150, style: initStyle, onCreated, onUpdated }: Props) {
  const [s, setS] = useState<ShapeStyle>({ ...DEFAULT_STYLE, ...initStyle });
  const [saving, setSaving] = useState(false);

  const update = useCallback((delta: Partial<ShapeStyle>) => setS(p => ({ ...p, ...delta })), []);

  const apply = useCallback(async () => {
    setSaving(true);
    try {
      if (clipId) {
        const clip = await shapeApi.update(clipId, s);
        onUpdated?.(clip);
      } else {
        const clip = await shapeApi.add(currentFrame, duration, s);
        onCreated?.(clip);
      }
    } finally { setSaving(false); }
  }, [clipId, s, currentFrame, duration]);

  const shape = s.shapeType ?? 'rect';

  return (
    <div className="tp-panel">
      <div className="tp-header">
        <span className="tp-icon">▬</span>
        <span className="tp-title">Shape</span>
      </div>

      {/* Shape Type */}
      <section className="tp-section">
        <h3 className="tp-section-title">Type</h3>
        <div className="sp-shape-grid">
          {SHAPE_TYPES.map(({ type, label, icon }) => (
            <button key={type} id={`sp-shape-${type}`}
              className={`sp-shape-btn${shape === type ? ' sp-shape-btn--active' : ''}`}
              title={label}
              onClick={() => update({ shapeType: type })}>
              <span>{icon}</span>
              <small>{label}</small>
            </button>
          ))}
        </div>
      </section>

      {/* Dimensions */}
      <section className="tp-section">
        <h3 className="tp-section-title">Dimensions</h3>
        {(shape === 'rect') && <>
          <div className="tp-row"><label className="tp-label">W</label>
            <input type="number" className="tp-input" value={s.width} onChange={e => update({ width: +e.target.value })} />
          </div>
          <div className="tp-row"><label className="tp-label">H</label>
            <input type="number" className="tp-input" value={s.height} onChange={e => update({ height: +e.target.value })} />
          </div>
          <div className="tp-row"><label className="tp-label">Radius</label>
            <input type="range" className="tp-range" min={0} max={200} value={s.cornerRadius}
              onChange={e => update({ cornerRadius: +e.target.value })} />
            <span className="tp-badge">{s.cornerRadius}px</span>
          </div>
        </>}
        {(shape === 'circle') && (
          <div className="tp-row"><label className="tp-label">Radius</label>
            <input type="number" className="tp-input" value={s.radiusX} onChange={e => update({ radiusX: +e.target.value })} />
          </div>
        )}
        {(shape === 'ellipse') && <>
          <div className="tp-row"><label className="tp-label">Rx</label>
            <input type="number" className="tp-input" value={s.radiusX} onChange={e => update({ radiusX: +e.target.value })} />
          </div>
          <div className="tp-row"><label className="tp-label">Ry</label>
            <input type="number" className="tp-input" value={s.radiusY} onChange={e => update({ radiusY: +e.target.value })} />
          </div>
        </>}
        {(shape === 'star') && <>
          <div className="tp-row"><label className="tp-label">Points</label>
            <input type="number" className="tp-input" min={3} max={20} value={s.numPoints}
              onChange={e => update({ numPoints: +e.target.value })} />
          </div>
          <div className="tp-row"><label className="tp-label">Outer R</label>
            <input type="number" className="tp-input" value={s.outerRadius}
              onChange={e => update({ outerRadius: +e.target.value })} />
          </div>
          <div className="tp-row"><label className="tp-label">Inner R</label>
            <input type="number" className="tp-input" value={s.innerRadius}
              onChange={e => update({ innerRadius: +e.target.value })} />
          </div>
        </>}
        {(shape === 'polygon') && <>
          <div className="tp-row"><label className="tp-label">Sides</label>
            <input type="number" className="tp-input" min={3} max={20} value={s.numSides}
              onChange={e => update({ numSides: +e.target.value })} />
          </div>
          <div className="tp-row"><label className="tp-label">Radius</label>
            <input type="number" className="tp-input" value={s.polygonRadius}
              onChange={e => update({ polygonRadius: +e.target.value })} />
          </div>
        </>}
        {(shape === 'arc') && <>
          <div className="tp-row"><label className="tp-label">Radius</label>
            <input type="number" className="tp-input" value={s.arcRadius}
              onChange={e => update({ arcRadius: +e.target.value })} />
          </div>
          <div className="tp-row"><label className="tp-label">Start°</label>
            <input type="range" className="tp-range" min={0} max={360} value={s.arcStartAngle}
              onChange={e => update({ arcStartAngle: +e.target.value })} />
            <span className="tp-badge">{s.arcStartAngle}°</span>
          </div>
          <div className="tp-row"><label className="tp-label">Sweep°</label>
            <input type="range" className="tp-range" min={1} max={360} value={s.arcSweepAngle}
              onChange={e => update({ arcSweepAngle: +e.target.value })} />
            <span className="tp-badge">{s.arcSweepAngle}°</span>
          </div>
        </>}
      </section>

      {/* Fill */}
      <section className="tp-section">
        <h3 className="tp-section-title">Fill</h3>
        <div className="tp-row">
          <label className="tp-label">Color</label>
          <input type="color" value={toHex(s.fillColor ?? [0.4,0.4,1,1])}
            onChange={e => update({ fillColor: fromHex(e.target.value, s.fillColor?.[3] ?? 1) })} />
          <input type="range" className="tp-range" min={0} max={1} step={0.01}
            value={s.fillOpacity ?? 1}
            onChange={e => update({ fillOpacity: +e.target.value })} />
          <span className="tp-badge">{Math.round((s.fillOpacity ?? 1) * 100)}%</span>
        </div>
      </section>

      {/* Stroke */}
      <section className="tp-section">
        <h3 className="tp-section-title">Stroke</h3>
        <div className="tp-row">
          <label className="tp-label">Width</label>
          <input type="range" className="tp-range" min={0} max={30} step={0.5}
            value={s.strokeWidth ?? 0} onChange={e => update({ strokeWidth: +e.target.value })} />
          <span className="tp-badge">{s.strokeWidth}px</span>
        </div>
        {(s.strokeWidth ?? 0) > 0 && <>
          <div className="tp-row">
            <label className="tp-label">Color</label>
            <input type="color" value={toHex(s.strokeColor ?? [1,1,1,1])}
              onChange={e => update({ strokeColor: fromHex(e.target.value, 1) })} />
          </div>
          <div className="tp-row">
            <label className="tp-label">Style</label>
            <select className="tp-select" value={s.strokeStyle}
              onChange={e => update({ strokeStyle: e.target.value as any })}>
              <option value="center">Center</option>
              <option value="inside">Inside</option>
              <option value="outside">Outside</option>
            </select>
          </div>
        </>}
      </section>

      {/* Shadow */}
      <section className="tp-section">
        <div className="tp-row">
          <label className="tp-label">Drop Shadow</label>
          <button className={`tp-toggle${s.shadowEnabled ? ' tp-toggle--on' : ''}`}
            onClick={() => update({ shadowEnabled: !s.shadowEnabled })}>
            {s.shadowEnabled ? 'On' : 'Off'}
          </button>
        </div>
        {s.shadowEnabled && <>
          <div className="tp-row"><label className="tp-label">Color</label>
            <input type="color" value={toHex(s.shadowColor ?? [0,0,0,0.75])}
              onChange={e => update({ shadowColor: fromHex(e.target.value, s.shadowColor?.[3] ?? 0.75) })} />
          </div>
          <div className="tp-row"><label className="tp-label">Angle</label>
            <input type="range" className="tp-range" min={0} max={360}
              value={s.shadowAngle} onChange={e => update({ shadowAngle: +e.target.value })} />
            <span className="tp-badge">{s.shadowAngle}°</span>
          </div>
          <div className="tp-row"><label className="tp-label">Distance</label>
            <input type="range" className="tp-range" min={0} max={100}
              value={s.shadowDistance} onChange={e => update({ shadowDistance: +e.target.value })} />
            <span className="tp-badge">{s.shadowDistance}px</span>
          </div>
          <div className="tp-row"><label className="tp-label">Blur</label>
            <input type="range" className="tp-range" min={0} max={40}
              value={s.shadowBlur} onChange={e => update({ shadowBlur: +e.target.value })} />
            <span className="tp-badge">{s.shadowBlur}px</span>
          </div>
        </>}
      </section>

      <div className="tp-footer">
        {saving && <span className="tp-saving">Applying…</span>}
        <button id="sp-apply" className="tp-btn" onClick={apply}>
          {clipId ? 'Update' : 'Add to Timeline'}
        </button>
      </div>
    </div>
  );
}
