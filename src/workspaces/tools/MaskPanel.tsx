import React, { useState, useRef, useCallback, useEffect } from 'react';
import './ToolPanels.css';
import { penApi, maskApi, type MaskRequest } from '../../api/toolsApi';

// ── MaskPanel component ──────────────────────────────────────────────────────

interface MaskPanelProps {
  clipId: string;
  masks: any[];
  onUpdate: () => void;
}

export function MaskPanel({ clipId, masks, onUpdate }: MaskPanelProps) {
  const addMask = async (shape: 'rect' | 'ellipse' | 'bezier') => {
    await maskApi.add(clipId, {
      name:   `Mask ${masks.length + 1}`,
      shape,
      mode:   'add',
      feather: 0,
      opacity: 1,
      points:  shape === 'rect'
        ? [
            { x: -100, y: -60, inX: 0, inY: 0, outX: 0, outY: 0 },
            { x:  100, y: -60, inX: 0, inY: 0, outX: 0, outY: 0 },
            { x:  100, y:  60, inX: 0, inY: 0, outX: 0, outY: 0 },
            { x: -100, y:  60, inX: 0, inY: 0, outX: 0, outY: 0 },
          ]
        : shape === 'ellipse'
        ? [
            { x: -100, y: -60, inX: 0, inY: 0, outX: 0, outY: 0 },
            { x:  100, y:  60, inX: 0, inY: 0, outX: 0, outY: 0 },
          ]
        : [],
    });
    onUpdate();
  };

  return (
    <div className="mask-panel">
      <div className="mask-header">
        <span>Masks</span>
        <div className="mask-add-btns">
          <button className="mask-add-btn" title="Add Rect Mask"    onClick={() => addMask('rect')}>▬ Rect</button>
          <button className="mask-add-btn" title="Add Ellipse Mask" onClick={() => addMask('ellipse')}>⬭ Ellipse</button>
          <button className="mask-add-btn" title="Add Bezier Mask"  onClick={() => addMask('bezier')}>✏ Path</button>
        </div>
      </div>

      {masks.length === 0 && <p className="mask-empty">No masks. Add one above.</p>}

      {masks.map((mask: any) => (
        <MaskRow key={mask.maskId} clipId={clipId} mask={mask} onUpdate={onUpdate} />
      ))}
    </div>
  );
}

function MaskRow({ clipId, mask, onUpdate }: { clipId: string; mask: any; onUpdate: () => void }) {
  const patchField = async (field: string, value: any) => {
    await maskApi.update(clipId, mask.maskId, { [field]: value } as any);
    onUpdate();
  };

  return (
    <div className="mask-row">
      <div className="mask-row-header">
        <span className="mask-row-name">{mask.name}</span>
        <div className="mask-row-actions">
          <button
            className={`tp-toggle${mask.mode === 'subtract' ? ' tp-toggle--on' : ''}`}
            title="Toggle Add/Subtract"
            onClick={() => patchField('mode', mask.mode === 'subtract' ? 'add' : 'subtract')}>
            {mask.mode === 'subtract' ? '−' : '+'}
          </button>
          <button
            className={`tp-toggle${mask.inverted ? ' tp-toggle--on' : ''}`}
            title="Invert"
            onClick={() => patchField('inverted', !mask.inverted)}>⇄</button>
          <button className="mask-delete-btn"
            onClick={async () => { await maskApi.remove(clipId, mask.maskId); onUpdate(); }}>✕</button>
        </div>
      </div>
      <div className="tp-row">
        <label className="tp-label">Feather</label>
        <input type="range" className="tp-range" min={0} max={100} step={0.5}
          defaultValue={mask.feather}
          onMouseUp={e => patchField('feather', +(e.target as HTMLInputElement).value)} />
        <span className="tp-badge">{mask.feather?.toFixed(1)}px</span>
      </div>
      <div className="tp-row">
        <label className="tp-label">Opacity</label>
        <input type="range" className="tp-range" min={0} max={1} step={0.01}
          defaultValue={mask.opacity}
          onMouseUp={e => patchField('opacity', +(e.target as HTMLInputElement).value)} />
        <span className="tp-badge">{Math.round((mask.opacity ?? 1) * 100)}%</span>
      </div>
    </div>
  );
}
