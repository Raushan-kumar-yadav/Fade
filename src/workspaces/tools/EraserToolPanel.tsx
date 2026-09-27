import React, { useState } from 'react';
import { useTool } from '../../context/toolContext';
import './ToolPanels.css';

interface EraserPreset {
  id: string;
  name: string;
  size: number;
}
const ERASER_PRESETS: EraserPreset[] = [
  { id: 'small', name: 'Small', size: 10 },
  { id: 'medium', name: 'Medium', size: 25 },
  { id: 'large', name: 'Large', size: 50 },
  { id: 'xlarge', name: 'Extra Large', size: 100 },
];

export default function EraserToolPanel() {
  const { brushSize, setBrushSize } = useTool();
  const [activePreset, setActivePreset] = useState<string>('medium');

  const applyPreset = (p: EraserPreset) => {
    setActivePreset(p.id);
    setBrushSize(p.size);
  };

  const handleSizeChange = (val: number) => {
    setBrushSize(val);
    setActivePreset('custom');
  };

  return (
    <div className="tp-panel" style={{ userSelect: 'none', paddingBottom: '16px' }}>
      <div className="tp-header" style={{ padding: '8px 12px', borderBottom: '1px solid #1e293b', marginBottom: '12px' }}>
        <span className="tp-icon" style={{ marginRight: '8px' }}>??</span>
        <span className="tp-title" style={{ fontWeight: 600 }}>Eraser Tool</span>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '0 12px' }}>
        <div style={{ marginBottom: '16px' }}>
          <div style={{ fontSize: '10px', color: '#94a3b8', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Presets</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
            {ERASER_PRESETS.map(p => (
              <button
                key={p.id}
                onClick={() => applyPreset(p)}
                style={{
                  padding: '4px 10px',
                  background: activePreset === p.id ? '#ef4444' : '#1e293b',
                  color: '#fff',
                  border: '1px solid',
                  borderColor: activePreset === p.id ? '#fca5a5' : '#334155',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '11px',
                  fontWeight: activePreset === p.id ? 600 : 400,
                  transition: 'background 0.1s'
                }}
              >
                {p.name}
              </button>
            ))}
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '6px' }}>
              <span style={{ fontWeight: 500 }}>Eraser Size</span>
              <span style={{ color: '#94a3b8' }}>{brushSize} px</span>
            </div>
            <input 
              type="range" 
              className="tp-range"
              min={1} max={300} step={1}
              value={brushSize}
              onChange={e => handleSizeChange(parseInt(e.target.value))}
              style={{ width: '100%', margin: 0 }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
