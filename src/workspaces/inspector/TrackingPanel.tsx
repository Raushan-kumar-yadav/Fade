import React, { useState } from 'react';
import './TrackingPanel.css';

interface TrackingPanelProps {
  clipId: string;
  startFrame: number;
  duration: number;
}

export default function TrackingPanel({ clipId, startFrame, duration }: TrackingPanelProps) {
  const [open, setOpen] = useState(false);
  const [trackStart, setTrackStart] = useState(startFrame);
  const [trackEnd, setTrackEnd] = useState(startFrame + Math.min(30, duration));
  const [property, setProperty] = useState("position");
  
  // Fake ROI inputs for tracking initial bounds
  const [x, setX] = useState(1920/2 - 50);
  const [y, setY] = useState(1080/2 - 50);
  const [w, setW] = useState(100);
  const [h, setH] = useState(100);

  const [status, setStatus] = useState<string>("");

  const handleTrack = async () => {
    setStatus("Tracking...");
    const port = (window as any).__FADE_PORT__ ?? 8000;
    try {
      const res = await fetch(`http://127.0.0.1:${port}/tracking/track`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          clip_id: clipId,
          start_frame: trackStart,
          end_frame: trackEnd,
          property: property,
          x, y, width: w, height: h
        })
      });
      if (res.ok) {
        setStatus("Tracking complete!");
      } else {
        const err = await res.json();
        setStatus(`Error: ${err.detail}`);
      }
    } catch (e) {
      setStatus(`Failed to connect`);
    }
  };

  const handleApply = async () => {
    setStatus("Applying...");
    const port = (window as any).__FADE_PORT__ ?? 8000;
    try {
      const res = await fetch(`http://127.0.0.1:${port}/tracking/bind`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          clip_id: clipId,
          property_name: property, // 'position' or 'scale'
          expression: 'tracking:self'
        })
      });
      if (res.ok) {
        setStatus("Applied tracking data!");
      } else {
        const err = await res.json();
        setStatus(`Error: ${err.detail}`);
      }
    } catch (e: any) {
      setStatus(`Failed to apply: ${e.message || String(e)}`);
    }
  };

  return (
    <div className="insp-group">
      <div className="insp-group__header" onClick={() => setOpen(!open)}>
        <span className="insp-group__toggle">{open ? '▼' : '▶'}</span>
        <span className="insp-group__title">Motion Tracking</span>
      </div>
      {open && (
        <div className="insp-group__body" style={{ padding: '8px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          
          <div style={{display: 'flex', justifyContent: 'space-between'}}>
            <label>Start Frame:</label>
            <input type="number" value={trackStart} onChange={e => setTrackStart(Number(e.target.value))} style={{width: '60px'}} />
          </div>
          <div style={{display: 'flex', justifyContent: 'space-between'}}>
            <label>End Frame:</label>
            <input type="number" value={trackEnd} onChange={e => setTrackEnd(Number(e.target.value))} style={{width: '60px'}} />
          </div>
          
          <div style={{display: 'flex', justifyContent: 'space-between'}}>
            <label>Target Box (X,Y,W,H):</label>
            <div style={{display: 'flex', gap: '4px'}}>
                <input type="number" value={x} onChange={e => setX(Number(e.target.value))} style={{width: '40px'}} title="X" />
                <input type="number" value={y} onChange={e => setY(Number(e.target.value))} style={{width: '40px'}} title="Y" />
                <input type="number" value={w} onChange={e => setW(Number(e.target.value))} style={{width: '40px'}} title="W" />
                <input type="number" value={h} onChange={e => setH(Number(e.target.value))} style={{width: '40px'}} title="H" />
            </div>
          </div>

          <div style={{display: 'flex', justifyContent: 'space-between'}}>
            <label>Property:</label>
            <select value={property} onChange={e => setProperty(e.target.value)}>
              <option value="position">Position</option>
              <option value="scale">Scale</option>
            </select>
          </div>

          <button onClick={handleTrack} style={{marginTop: '4px'}}>Start Tracking</button>
          
          {status && <div style={{fontSize: '11px', color: '#888'}}>{status}</div>}
          
          <button onClick={handleApply} disabled={!status.includes('complete')} style={{marginTop: '4px'}}>Apply to {property}</button>

        </div>
      )}
    </div>
  );
}
