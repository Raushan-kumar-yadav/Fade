import React, { useEffect, useState, useCallback, useRef } from 'react';
import './SettingsPanel.css';

interface Settings {
  cacheMaxMB:     number;
  cacheUsedMB:    number;
  cacheFrames:    number;
  cacheMaxFrames: number;
  previewScale:   number;
  jpegQuality:    number;
  prefetchRadius: number;
  batchSize:      number;
  decoderMode:    string;
}

function getPort(): number | null {
  return (window as any).__FADE_PORT__ ?? null;
}

async function fetchSettings(): Promise<Settings | null> {
  const port = getPort();
  if (!port) return null;
  try {
    const r = await fetch(`http://127.0.0.1:${port}/settings`);
    return r.ok ? r.json() : null;
  } catch { return null; }
}

async function postSettings(delta: Partial<Settings>): Promise<Settings | null> {
  const port = getPort();
  if (!port) return null;
  try {
    const r = await fetch(`http://127.0.0.1:${port}/settings`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(delta),
    });
    return r.ok ? r.json() : null;
  } catch { return null; }
}

interface Props {
  onClose: () => void;
}

export default function SettingsPanel({ onClose }: Props) {
  const [s, setS]         = useState<Settings | null>(null);
  const [saving, setSaving] = useState(false);
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchSettings().then(setS);
  }, []);

  // Close on Escape
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const apply = useCallback(async (delta: Partial<Settings>) => {
    setSaving(true);
    const next = await postSettings(delta);
    if (next) setS(next);
    setSaving(false);
  }, []);

  if (!s) return (
    <div className="sp-overlay" ref={overlayRef} onClick={e => { if (e.target === overlayRef.current) onClose(); }}>
      <div className="sp-panel"><p className="sp-loading">Connecting to engine…</p></div>
    </div>
  );

  const cachePercent = Math.min(100, Math.round((s.cacheUsedMB / s.cacheMaxMB) * 100));

  return (
    <div className="sp-overlay" ref={overlayRef} onClick={e => { if (e.target === overlayRef.current) onClose(); }}>
      <div className="sp-panel" role="dialog" aria-modal="true" aria-label="Settings">

        {/* Header */}
        <div className="sp-header">
          <h2 className="sp-title">⚙ Settings</h2>
          <button className="sp-close" onClick={onClose} aria-label="Close settings">✕</button>
        </div>

        {/* ── Cache ── */}
        <section className="sp-section">
          <h3 className="sp-section-title">Frame Cache</h3>

          <div className="sp-row">
            <label className="sp-label">Budget (MB)</label>
            <input id="set-cache-mb" type="number" className="sp-input" min={64} max={4096} step={64}
              defaultValue={s.cacheMaxMB}
              onBlur={e => apply({ cacheMaxMB: parseInt(e.target.value, 10) })}
              onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
            />
          </div>

          <div className="sp-row">
            <label className="sp-label">Usage</label>
            <div className="sp-bar-wrap">
              <div className="sp-bar" style={{ width: `${cachePercent}%`,
                background: cachePercent > 80 ? '#ff6b6b' : cachePercent > 60 ? '#ffa94d' : '#00d4aa' }} />
            </div>
            <span className="sp-badge">{s.cacheUsedMB} / {s.cacheMaxMB} MB ({s.cacheFrames} frames)</span>
          </div>

          <div className="sp-row">
            <label className="sp-label">Max frames cap</label>
            <span className="sp-value">{s.cacheMaxFrames}</span>
          </div>
        </section>

        {/* ── Decode ── */}
        <section className="sp-section">
          <h3 className="sp-section-title">Decoder</h3>

          <div className="sp-row">
            <label className="sp-label" htmlFor="set-decoder">Backend</label>
            <select id="set-decoder" className="sp-select" value={s.decoderMode}
              onChange={e => apply({ decoderMode: e.target.value })}>
              <option value="auto">Auto (PyAV → FFmpeg)</option>
              <option value="pyav">PyAV in-process</option>
              <option value="ffmpeg">FFmpeg subprocess</option>
            </select>
          </div>

          <div className="sp-row">
            <label className="sp-label" htmlFor="set-scale">Preview resolution</label>
            <select id="set-scale" className="sp-select" value={s.previewScale}
              onChange={e => apply({ previewScale: parseFloat(e.target.value) })}>
              <option value={1.0}>Full (1.0×)</option>
              <option value={0.5}>Half (0.5×)</option>
              <option value={0.25}>Quarter (0.25×)</option>
              <option value={0.125}>Eighth (0.125×)</option>
            </select>
          </div>

          <div className="sp-row">
            <label className="sp-label">Prefetch radius</label>
            <input id="set-prefetch" type="range" className="sp-range" min={10} max={240} step={10}
              value={s.prefetchRadius}
              onChange={e => setS({ ...s, prefetchRadius: parseInt(e.target.value, 10) })}
              onMouseUp={e => apply({ prefetchRadius: parseInt((e.target as HTMLInputElement).value, 10) })}
            />
            <span className="sp-badge">{s.prefetchRadius} frames</span>
          </div>

          <div className="sp-row">
            <label className="sp-label">Batch size</label>
            <input id="set-batch" type="range" className="sp-range" min={10} max={120} step={10}
              value={s.batchSize}
              onChange={e => setS({ ...s, batchSize: parseInt(e.target.value, 10) })}
              onMouseUp={e => apply({ batchSize: parseInt((e.target as HTMLInputElement).value, 10) })}
            />
            <span className="sp-badge">{s.batchSize}</span>
          </div>
        </section>

        {/* ── Output ── */}
        <section className="sp-section">
          <h3 className="sp-section-title">Preview Output</h3>

          <div className="sp-row">
            <label className="sp-label">JPEG quality</label>
            <input id="set-jpeg" type="range" className="sp-range" min={20} max={100} step={5}
              value={s.jpegQuality}
              onChange={e => setS({ ...s, jpegQuality: parseInt(e.target.value, 10) })}
              onMouseUp={e => apply({ jpegQuality: parseInt((e.target as HTMLInputElement).value, 10) })}
            />
            <span className="sp-badge">{s.jpegQuality}</span>
          </div>
        </section>

        <div className="sp-footer">
          {saving && <span className="sp-saving">Saving…</span>}
          <button className="sp-btn sp-btn--close" onClick={onClose}>Done</button>
        </div>
      </div>
    </div>
  );
}

