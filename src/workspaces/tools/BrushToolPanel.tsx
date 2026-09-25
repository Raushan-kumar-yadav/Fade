import React, { useRef, useState, useEffect } from 'react';
import { useTool } from '../../context/toolContext';
import './ToolPanels.css';

// Hex utils
function toHex(color: [number, number, number, number]): string {
  const r = Math.round(color[0] * 255).toString(16).padStart(2, '0');
  const g = Math.round(color[1] * 255).toString(16).padStart(2, '0');
  const b = Math.round(color[2] * 255).toString(16).padStart(2, '0');
  return '#' + r + g + b;
}
function fromHex(hex: string, alpha = 1): [number, number, number, number] {
  const r = parseInt(hex.slice(1, 3), 16) / 255;
  const g = parseInt(hex.slice(3, 5), 16) / 255;
  const b = parseInt(hex.slice(5, 7), 16) / 255;
  return [r, g, b, alpha];
}

function hsvToRgb(h: number, s: number, v: number): [number, number, number] {
  let r = 0, g = 0, b = 0;
  const i = Math.floor(h * 6);
  const f = h * 6 - i;
  const p = v * (1 - s);
  const q = v * (1 - f * s);
  const t = v * (1 - (1 - f) * s);
  switch (i % 6) {
    case 0: r = v, g = t, b = p; break;
    case 1: r = q, g = v, b = p; break;
    case 2: r = p, g = v, b = t; break;
    case 3: r = p, g = q, b = v; break;
    case 4: r = t, g = p, b = v; break;
    case 5: r = v, g = p, b = q; break;
  }
  return [r, g, b];
}

function rgbToHsv(r: number, g: number, b: number): [number, number, number] {
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h = 0, s = 0, v = max;
  const d = max - min;
  s = max === 0 ? 0 : d / max;
  if (max === min) {
    h = 0;
  } else {
    switch (max) {
      case r: h = (g - b) / d + (g < b ? 6 : 0); break;
      case g: h = (b - r) / d + 2; break;
      case b: h = (r - g) / d + 4; break;
    }
    h /= 6;
  }
  return [h, s, v];
}

const QUICK_COLORS = [
  '#FFFFFF', '#000000', '#FF0000', '#FF7F00', '#FFFF00', '#00FF00', 
  '#00FFFF', '#0000FF', '#7F00FF', '#FF00FF', '#8B4513', '#808080'
];

interface BrushPreset {
  id: string;
  name: string;
  size: number;
  opacity: number;
}
const BRUSH_PRESETS: BrushPreset[] = [
  { id: 'pencil', name: 'Pencil', size: 2, opacity: 0.9 },
  { id: 'pen', name: 'Pen', size: 4, opacity: 1.0 },
  { id: 'marker', name: 'Marker', size: 15, opacity: 0.8 },
  { id: 'highlighter', name: 'Highlighter', size: 30, opacity: 0.4 },
  { id: 'thick', name: 'Thick Paint', size: 25, opacity: 0.95 },
];

export default function BrushToolPanel() {
  const { brushColor, setBrushColor, brushSize, setBrushSize } = useTool();
  
  const hexValue = toHex(brushColor);
  const opacity = brushColor[3];
  const [activePreset, setActivePreset] = useState<string>('pen');

  const [hsv, setHsv] = useState<[number, number, number]>(() => rgbToHsv(brushColor[0], brushColor[1], brushColor[2]));
  const canvasRef = useRef<HTMLCanvasElement>(null);
  
  useEffect(() => {
    setHsv(rgbToHsv(brushColor[0], brushColor[1], brushColor[2]));
  }, [brushColor[0], brushColor[1], brushColor[2]]);

  const applyPreset = (p: BrushPreset) => {
    setActivePreset(p.id);
    setBrushSize(p.size);
    setBrushColor([brushColor[0], brushColor[1], brushColor[2], p.opacity]);
  };

  const handleOpacityChange = (val: number) => {
    setBrushColor([brushColor[0], brushColor[1], brushColor[2], val]);
    setActivePreset('custom');
  };

  const handleSizeChange = (val: number) => {
    setBrushSize(val);
    setActivePreset('custom');
  };

  const handleHexInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    if (/^#[0-9A-Fa-f]{6}$/.test(val)) {
      setBrushColor(fromHex(val, opacity));
    }
  };

  const setHsvColor = (h: number, s: number, v: number) => {
    const [r, g, b] = hsvToRgb(h, s, v);
    setBrushColor([r, g, b, opacity]);
    setHsv([h, s, v]);
  };

  useEffect(() => {
    const cvs = canvasRef.current;
    if (!cvs) return;
    const ctx = cvs.getContext('2d');
    if (!ctx) return;
    
    const size = cvs.width;
    const cx = size / 2;
    const cy = size / 2;
    const radius = size / 2;

    ctx.clearRect(0, 0, size, size);

    if (typeof (ctx as any).createConicGradient === 'function') {
      const grad = (ctx as any).createConicGradient(0, cx, cy);
      grad.addColorStop(0, '#f00');
      grad.addColorStop(1/6, '#ff0');
      grad.addColorStop(2/6, '#0f0');
      grad.addColorStop(3/6, '#0ff');
      grad.addColorStop(4/6, '#00f');
      grad.addColorStop(5/6, '#f0f');
      grad.addColorStop(1, '#f00');
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.fill();
    } else {
      ctx.fillStyle = '#fff';
      ctx.fillRect(0,0,size,size);
    }

    const rgrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
    rgrad.addColorStop(0, 'white');
    rgrad.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = rgrad;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = `rgba(0,0,0,${1 - hsv[2]})`;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.fill();
    
    const angle = hsv[0] * Math.PI * 2;
    const dist = hsv[1] * radius;
    const kx = cx + Math.cos(angle) * dist;
    const ky = cy + Math.sin(angle) * dist;
    
    ctx.beginPath();
    ctx.arc(kx, ky, 5, 0, Math.PI * 2);
    ctx.strokeStyle = hsv[2] < 0.5 ? '#fff' : '#000';
    ctx.lineWidth = 2;
    ctx.stroke();

  }, [hsv]);

  const onWheelInteraction = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (e.buttons !== 1) return;
    const cvs = canvasRef.current;
    if (!cvs) return;
    const rect = cvs.getBoundingClientRect();
    const size = rect.width;
    const cx = size / 2;
    const cy = size / 2;
    
    const x = e.clientX - rect.left - cx;
    const y = e.clientY - rect.top - cy;
    
    const dist = Math.min(Math.sqrt(x*x + y*y), size/2);
    let angle = Math.atan2(y, x);
    if (angle < 0) angle += Math.PI * 2;
    
    const s = dist / (size / 2);
    const h = angle / (Math.PI * 2);
    
    setHsvColor(h, s, hsv[2]);
  };

  return (
    <div className="tp-panel" style={{ userSelect: 'none', paddingBottom: '16px' }}>
      <div className="tp-header" style={{ padding: '8px 12px', borderBottom: '1px solid #1e293b', marginBottom: '12px' }}>
        <span className="tp-icon" style={{ marginRight: '8px' }}>??</span>
        <span className="tp-title" style={{ fontWeight: 600 }}>Brush Tool</span>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '0 12px' }}>
        {/* Presets */}
        <div style={{ marginBottom: '16px' }}>
          <div style={{ fontSize: '10px', color: '#94a3b8', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Presets</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
            {BRUSH_PRESETS.map(p => (
              <button
                key={p.id}
                onClick={() => applyPreset(p)}
                style={{
                  padding: '4px 10px',
                  background: activePreset === p.id ? '#3b82f6' : '#1e293b',
                  color: '#fff',
                  border: '1px solid',
                  borderColor: activePreset === p.id ? '#60a5fa' : '#334155',
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

        {/* Color Wheel Section */}
        <div style={{ marginBottom: '16px' }}>
          <div style={{ fontSize: '10px', color: '#94a3b8', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Color & Shade</div>
          <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
            <div style={{ width: '100px', height: '100px', borderRadius: '50%', overflow: 'hidden', flexShrink: 0, boxShadow: '0 0 0 1px #334155' }}>
              <canvas 
                ref={canvasRef}
                width={100} 
                height={100} 
                onMouseDown={onWheelInteraction}
                onMouseMove={onWheelInteraction}
                style={{ cursor: 'crosshair', display: 'block' }}
              />
            </div>
            
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <div 
                  style={{ 
                    width: '24px', height: '24px', 
                    backgroundColor: hexValue, 
                    borderRadius: '4px',
                    border: '1px solid #334155',
                    boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.1)'
                  }} 
                />
                <input 
                  type="text" 
                  value={hexValue.toUpperCase()} 
                  onChange={handleHexInput}
                  style={{
                    width: '60px',
                    background: '#0f172a',
                    border: '1px solid #334155',
                    color: '#fff',
                    fontSize: '11px',
                    padding: '4px 6px',
                    borderRadius: '4px',
                    fontFamily: 'monospace'
                  }}
                />
              </div>

              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: '#94a3b8', marginBottom: '4px' }}>
                  <span>Shade (Value)</span>
                  <span>{Math.round(hsv[2] * 100)}%</span>
                </div>
                <input 
                  type="range" 
                  className="tp-range"
                  min={0} max={1} step={0.01} 
                  value={hsv[2]}
                  onChange={e => setHsvColor(hsv[0], hsv[1], parseFloat(e.target.value))}
                  style={{ width: '100%', margin: 0 }}
                />
              </div>
            </div>
          </div>
        </div>

        {/* Quick Colors */}
        <div style={{ marginBottom: '20px' }}>
          <div style={{ fontSize: '10px', color: '#94a3b8', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Quick Colors</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
            {QUICK_COLORS.map(c => (
              <div 
                key={c}
                onClick={() => setBrushColor(fromHex(c, opacity))}
                title={c}
                style={{
                  width: '18px', height: '18px',
                  borderRadius: '50%',
                  backgroundColor: c,
                  cursor: 'pointer',
                  border: c.toLowerCase() === hexValue.toLowerCase() ? '2px solid #3b82f6' : '1px solid #334155',
                  boxShadow: c.toLowerCase() === hexValue.toLowerCase() ? '0 0 4px rgba(59,130,246,0.5)' : 'none'
                }}
              />
            ))}
          </div>
        </div>

        {/* Sliders */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '6px' }}>
              <span style={{ fontWeight: 500 }}>Opacity</span>
              <span style={{ color: '#94a3b8' }}>{Math.round(opacity * 100)}%</span>
            </div>
            <input 
              type="range" 
              className="tp-range"
              min={0} max={1} step={0.01}
              value={opacity}
              onChange={e => handleOpacityChange(parseFloat(e.target.value))}
              style={{ width: '100%', margin: 0 }}
            />
          </div>

          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '6px' }}>
              <span style={{ fontWeight: 500 }}>Brush Size</span>
              <span style={{ color: '#94a3b8' }}>{brushSize} px</span>
            </div>
            <input 
              type="range" 
              className="tp-range"
              min={1} max={150} step={1}
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
