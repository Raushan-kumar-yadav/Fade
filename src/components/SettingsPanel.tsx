import React, { useEffect, useState, useCallback, useRef } from 'react';
import './SettingsPanel.css';

//   Types  

interface Settings {
  // Playback / Cache
  cacheMaxMB: number;
  cacheUsedMB: number;
  cacheFrames: number;
  cacheMaxFrames: number;
  previewScale: number;
  jpegQuality: number;
  prefetchRadius: number;
  batchSize: number;
  decoderMode: string;
  // AI Indexing
  aiVisionModel: string;
  aiFrameInterval:  number;
}

interface AiSettings {
  visionModel:    string;
  frameInterval:  number;
  whisperBackend: string;   // "faster" | "openai"
  whisperModel:   string;
  availableModels: string[];
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

async function fetchAiSettings(): Promise<AiSettings | null> {
  const port = getPort();
  if (!port) return null;
  try {
    const r = await fetch(`http://127.0.0.1:${port}/settings/ai`);
    return r.ok ? r.json() : null;
  } catch { return null; }
}

async function postAiSettings(delta: Partial<Pick<AiSettings,'visionModel'|'frameInterval'>>): Promise<AiSettings | null> {
  const port = getPort();
  if (!port) return null;
  try {
    const r = await fetch(`http://127.0.0.1:${port}/settings/ai`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(delta),
    });
    return r.ok ? r.json() : null;
  } catch { return null; }
}

//   Tab IDs  

type Tab = 'cache' | 'decoder' | 'output' | 'ai';

const TABS: { id: Tab; icon: string; label: string }[] = [
  { id: 'cache',   icon: '⚡', label: 'Cache'      },
  { id: 'decoder', icon: '🎞', label: 'Decoder'    },
  { id: 'output',  icon: '🖼', label: 'Output'     },
  { id: 'ai', icon: '🤖', label: 'AI Indexing'},
];

//   Component  

interface Props { onClose: () => void; }

export default function SettingsPanel({ onClose }: Props) {
  const [s, setS] = useState<Settings | null>(null);
  const [ai, setAi] = useState<AiSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [tab, setTab] = useState<Tab>('cache');
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchSettings().then(setS);
    fetchAiSettings().then(setAi);
  }, []);

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

  const applyAi = useCallback(async (delta: Partial<Pick<AiSettings,'visionModel'|'frameInterval'|'whisperBackend'|'whisperModel'>>) => {
    setSaving(true);
    const next = await postAiSettings(delta);
    if (next) setAi(next);
    setSaving(false);
  }, []);

  return (
    <div className="sp-overlay" ref={overlayRef}
      onClick={e => { if (e.target === overlayRef.current) onClose(); }}>
      <div className="sp-panel" role="dialog" aria-modal="true" aria-label="Settings">

        {/* Header */}
        <div className="sp-header">
          <h2 className="sp-title">⚙ Settings</h2>
          <button className="sp-close" onClick={onClose} aria-label="Close settings">✕</button>
        </div>

        {/* Body: sidebar + content */}
        <div className="sp-body">

          {/* Left tab sidebar */}
          <nav className="sp-sidebar">
            {TABS.map(t => (
              <button
                key={t.id}
                className={`sp-tab${tab === t.id ? ' sp-tab--active' : ''}`}
                onClick={() => setTab(t.id)}
              >
                <span className="sp-tab-icon">{t.icon}</span>
                <span className="sp-tab-label">{t.label}</span>
              </button>
            ))}
          </nav>

          {/* Right content */}
          <div className="sp-content">
            {!s && tab !== 'ai' && (
              <p className="sp-loading">Connecting to engine…</p>
            )}

            {/* ── Cache ── */}
            {tab === 'cache' && s && (
              <>
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
                    <div className="sp-bar" style={{
                      width: `${Math.min(100, Math.round((s.cacheUsedMB / s.cacheMaxMB) * 100))}%`,
                      background: s.cacheUsedMB / s.cacheMaxMB > 0.8 ? '#ff6b6b'
                                : s.cacheUsedMB / s.cacheMaxMB > 0.6 ? '#ffa94d' : '#00d4aa',
                    }} />
                  </div>
                  <span className="sp-badge">{s.cacheUsedMB} / {s.cacheMaxMB} MB ({s.cacheFrames} frames)</span>
                </div>
                <div className="sp-row">
                  <label className="sp-label">Max frames cap</label>
                  <span className="sp-value">{s.cacheMaxFrames}</span>
                </div>
              </>
            )}

            {/* ── Decoder ── */}
            {tab === 'decoder' && s && (
              <>
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
              </>
            )}

            {/* ── Output ── */}
            {tab === 'output' && s && (
              <div className="sp-row">
                <label className="sp-label">JPEG quality</label>
                <input id="set-jpeg" type="range" className="sp-range" min={20} max={100} step={5}
                  value={s.jpegQuality}
                  onChange={e => setS({ ...s, jpegQuality: parseInt(e.target.value, 10) })}
                  onMouseUp={e => apply({ jpegQuality: parseInt((e.target as HTMLInputElement).value, 10) })}
                />
                <span className="sp-badge">{s.jpegQuality}</span>
              </div>
            )}

            {/* ── AI Indexing ── */}
            {tab === 'ai' && (
              <>
                {!ai ? (
                  <p className="sp-loading">Loading AI settings…</p>
                ) : (
                  <>
                    <p className="sp-hint">
                      Videos dropped into the library are automatically indexed using a vision model.
                      Smaller/faster models trade detail for speed.
                    </p>

                    <div className="sp-row">
                      <label className="sp-label" htmlFor="set-vision-model">Vision model</label>
                      <select id="set-vision-model" className="sp-select" value={ai.visionModel}
                        onChange={e => applyAi({ visionModel: e.target.value })}>
                        {/* Show installed models first */}
                        {ai.availableModels.length > 0
                          ? ai.availableModels.map(m => (
                              <option key={m} value={m}>{m}</option>
                            ))
                          : (
                            <>
                              <option value="moondream">moondream (fast, ~1-2s/frame)</option>
                              <option value="gemma3:4b">gemma3:4b (detailed, ~8s/frame)</option>
                              <option value="llava">llava (balanced)</option>
                            </>
                          )
                        }
                      </select>
                    </div>

                    <div className="sp-row">
                      <label className="sp-label" htmlFor="set-interval">Frame interval</label>
                      <select id="set-interval" className="sp-select" value={ai.frameInterval}
                        onChange={e => applyAi({ frameInterval: parseFloat(e.target.value) })}>
                        <option value={1}>Every 1s (very detailed, slow)</option>
                        <option value={2}>Every 2s (detailed)</option>
                        <option value={4}>Every 4s (balanced) ★</option>
                        <option value={6}>Every 6s (fast)</option>
                        <option value={10}>Every 10s (very fast)</option>
                      </select>
                    </div>

                    <div className="sp-row">
                      <label className="sp-label">Est. speed</label>
                      <span className="sp-badge sp-badge--info">
                        {ai.visionModel.startsWith('moondream')
                          ? `~${Math.round(ai.frameInterval * 2)}s per minute of video`
                          : `~${Math.round(ai.frameInterval * 9)}s per minute of video`}
                      </span>
                    </div>

                    {/* ── Transcription ── */}
                    <div className="sp-subsection-title">Transcription (Whisper)</div>

                    <div className="sp-row">
                      <label className="sp-label" htmlFor="set-whisper-backend">Backend</label>
                      <select id="set-whisper-backend" className="sp-select" value={ai.whisperBackend}
                        onChange={e => applyAi({ whisperBackend: e.target.value })}>
                        <option value="faster">faster-whisper ★ (4-8× faster, int8)</option>
                        <option value="openai">openai-whisper (original)</option>
                      </select>
                    </div>

                    <div className="sp-row">
                      <label className="sp-label" htmlFor="set-whisper-model">Model size</label>
                      <select id="set-whisper-model" className="sp-select" value={ai.whisperModel}
                        onChange={e => applyAi({ whisperModel: e.target.value })}>
                        <option value="tiny">tiny (fastest, lowest accuracy)</option>
                        <option value="base">base (fast)</option>
                        <option value="small">small ★ (balanced)</option>
                        <option value="medium">medium (accurate, slow)</option>
                        <option value="large-v3">large-v3 (best, very slow)</option>
                      </select>
                    </div>

                    <div className="sp-hint sp-hint--warn">
                      ⚠ Changing these settings only affects new imports. Re-delete and re-import a video to re-index it.
                    </div>
                  </>
                )}
              </>
            )}
          </div>
        </div>

        <div className="sp-footer">
          {saving && <span className="sp-saving">Saving…</span>}
          <button className="sp-btn sp-btn--close" onClick={onClose}>Done</button>
        </div>
      </div>
    </div>
  );
}
