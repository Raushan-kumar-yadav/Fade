import React from 'react';
const useTool = () => ({ brushColor: [1, 1, 1, 1], setBrushColor: ()=>{}, brushSize: 10, setBrushSize: ()=>{} });


const PRESET_COLORS = [
  // Grayscale
  '#ffffff', '#e0e0e0', '#c0c0c0', '#808080', '#404040', '#000000',
  // Reds & Pinks
  '#ff0000', '#ff4d4d', '#ff9999', '#ff00ff', '#ff66b2', '#ffb3d9',
  // Oranges & Yellows
  '#ffa500', '#ffc04d', '#ffff00', '#ffff80', '#8b4513', '#d2b48c',
  // Greens
  '#00ff00', '#4dff4d', '#008000', '#006400', '#32cd32', '#98fb98',
  // Cyans & Blues
  '#00ffff', '#80ffff', '#0000ff', '#4d4dff', '#00008b', '#add8e6',
  // Purples
  '#800080', '#b366ff', '#4b0082', '#9932cc', '#da70d6', '#e6e6fa'
];

function toHex(rgba: [number, number, number, number]): string {
  const [r, g, b] = rgba.map(v => Math.round(v * 255).toString(16).padStart(2, '0'));
  return '#' + r + g + b;
}

function fromHex(hex: string, alpha = 1): [number, number, number, number] {
  const r = parseInt(hex.slice(1, 3), 16) / 255;
  const g = parseInt(hex.slice(3, 5), 16) / 255;
  const b = parseInt(hex.slice(5, 7), 16) / 255;
  return [r, g, b, alpha];
}

export default function BrushToolPanel() {
  const { brushColor, setBrushColor, brushSize, setBrushSize } = useTool();
  
  const hexValue = toHex(brushColor);
  const opacity = brushColor[3];

  const handleColorChange = (hex: string) => {
    setBrushColor(fromHex(hex, opacity));
  };

  const handleOpacityChange = (newOpacity: number) => {
    const [r, g, b] = brushColor;
    setBrushColor([r, g, b, newOpacity]);
  };

  const handleHexInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    let val = e.target.value;
    if (!val.startsWith('#')) val = '#' + val;
    if (/^#[0-9A-Fa-f]{6}$/.test(val)) {
      handleColorChange(val);
    }
  };

  return (
    <div className="tp-panel">
      <div className="tp-header">
        <span className="tp-icon">??</span>
        <span className="tp-title">Brush Tool</span>
      </div>
      
      <section className="tp-section">
        <h3 className="tp-section-title">Color</h3>
        <div className="tp-row" style={{ gap: '8px', marginBottom: '12px' }}>
          <input 
            type="color" 
            value={hexValue} 
            onChange={e => handleColorChange(e.target.value)} 
            title="Custom Color Picker"
            style={{ width: '28px', height: '24px', cursor: 'pointer', padding: 0, border: 'none', background: 'transparent' }}
          />
          <input 
            type="text" 
            className="tp-input" 
            value={hexValue.toUpperCase()} 
            onChange={handleHexInputChange}
            style={{ width: '80px', textTransform: 'uppercase' }}
          />
        </div>

        <div className="tp-row">
          <label className="tp-label">Presets</label>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: '4px', marginBottom: '16px', padding: '0 12px' }}>
          {PRESET_COLORS.map(color => (
            <div 
              key={color} 
              onClick={() => handleColorChange(color)}
              style={{
                width: '100%',
                aspectRatio: '1/1',
                backgroundColor: color,
                cursor: 'pointer',
                border: hexValue.toLowerCase() === color ? '2px solid #fff' : '1px solid rgba(255,255,255,0.2)',
                borderRadius: '2px',
                boxSizing: 'border-box'
              }}
              title={color}
            />
          ))}
        </div>
      </section>

      <section className="tp-section">
        <h3 className="tp-section-title">Settings</h3>
        <div className="tp-row">
          <label className="tp-label">Opacity</label>
          <input 
            type="range" 
            className="tp-range" 
            min={0} max={1} step={0.01}
            value={opacity}
            onChange={e => handleOpacityChange(parseFloat(e.target.value))} 
          />
          <span className="tp-badge">{Math.round(opacity * 100)}%</span>
        </div>

        <div className="tp-row">
          <label className="tp-label">Size</label>
          <input 
            type="range" 
            className="tp-range" 
            min={1} max={100} step={1}
            value={brushSize}
            onChange={e => setBrushSize(parseInt(e.target.value))} 
          />
          <span className="tp-badge">{brushSize}px</span>
        </div>
      </section>
    </div>
  );
}
