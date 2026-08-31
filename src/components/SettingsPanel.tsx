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
  aiFrameInterval: number;
}

interface AiSettings {
  visionModel: string;
  frameInterval:  number;
  whisperBackend: string;
  whisperModel: string;
  availableModels: string[];
}

interface GeneratorSettings {
  imageProvider: string;
  imageLocalModel: string;
  // ComfyUI
  comfyuiUrl: string;
  comfyuiPath: string;
  comfyuiModel: string;
  comfyuiWidth: number;
  comfyuiHeight: number;
  comfyuiSteps: number;
  comfyuiCfg: number;
  comfyuiRunning: boolean;
  comfyuiModels: string[];
  // Stability AI
  stabilityModel: string;   // "core" | "ultra" | "sd3"
  stabilityStyle: string;   // "" | "photographic" | "anime" | ...
  stabilityWidth: number;
  stabilityHeight: number;
  // TTS
  ttsProvider: string;
  ttsGoogleVoice: string;
  ttsLocalModel: string;
  ttsKokoroVoice: string;
  // Video
  videoProvider: string;
  videoLocalModel: string;
  // Ollama
  ollamaUrl: string;
  ollamaModels: string[];
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
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(delta),
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

async function postAiSettings(delta: Partial<Pick<AiSettings,'visionModel'|'frameInterval'|'whisperBackend'|'whisperModel'>>): Promise<AiSettings | null> {
  const port = getPort();
  if (!port) return null;
  try {
    const r = await fetch(`http://127.0.0.1:${port}/settings/ai`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:  JSON.stringify(delta),
    });
    return r.ok ? r.json() : null;
  } catch { return null; }
}

async function fetchGeneratorSettings(): Promise<GeneratorSettings | null> {
  const port = getPort();
  if (!port) return null;
  try {
    const r = await fetch(`http://127.0.0.1:${port}/settings/generators`);
    return r.ok ? r.json() : null;
  } catch { return null; }
}

async function postGeneratorSettings(delta: Partial<GeneratorSettings>): Promise<GeneratorSettings | null> {
  const port = getPort();
  if (!port) return null;
  try {
    const r = await fetch(`http://127.0.0.1:${port}/settings/generators`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(delta),
    });
    return r.ok ? r.json() : null;
  } catch { return null; }
}

//   Tab IDs  

type Tab = 'cache' | 'decoder' | 'output' | 'ai' | 'generators';

const TABS: { id: Tab; icon: string; label: string }[] = [
  { id: 'cache', icon: '⚡', label: 'Cache'       },
  { id: 'decoder', icon: '🎞', label: 'Decoder'     },
  { id: 'output', icon: '🖼', label: 'Output'      },
  { id: 'ai', icon: '🤖', label: 'AI Indexing' },
  { id: 'generators', icon: '✨', label: 'Generators'  },
];

const GEMINI_VOICES = [
  'Zephyr','Puck','Charon','Kore','Fenrir','Leda','Orus','Aoede',
  'Callirrhoe','Autonoe','Enceladus','Iapetus','Umbriel','Algieba',
  'Despina','Erinome','Algenib','Rasalgethi','Laomedeia','Achernar',
  'Alnilam','Schedar','Gacrux','Pulcherrima','Achird','Zubenelgenubi',
  'Vindemiatrix','Sadachbia','Sadaltager','Sulafat',
];

const VOICE_DESCRIPTIONS: Record<string, string> = {
  Zephyr: 'Bright', Puck: 'Upbeat', Charon: 'Informative', Kore: 'Firm',
  Fenrir: 'Excitable', Leda: 'Youthful', Orus: 'Firm', Aoede: 'Breezy',
  Callirrhoe: 'Easy-going', Autonoe: 'Bright', Enceladus: 'Breathy',
  Iapetus: 'Clear', Umbriel: 'Easy-going', Algieba: 'Smooth',
  Despina: 'Smooth', Erinome: 'Clear', Algenib: 'Gravelly',
  Rasalgethi: 'Informative', Laomedeia: 'Upbeat', Achernar: 'Soft',
  Alnilam: 'Firm', Schedar: 'Even', Gacrux: 'Mature',
  Pulcherrima: 'Forward', Achird: 'Friendly', Zubenelgenubi: 'Casual',
  Vindemiatrix: 'Gentle', Sadachbia: 'Lively', Sadaltager: 'Knowledgeable',
  Sulafat: 'Warm',
};

const KOKORO_VOICES = [
  'af_heart', 'af_alloy', 'af_aoede', 'af_bella', 'af_jessica', 'af_kore', 
  'af_nicole', 'af_nova', 'af_river', 'af_sarah', 'af_sky', 
  'am_adam', 'am_echo', 'am_eric', 'am_fenrir', 'am_liam', 'am_michael', 
  'am_onyx', 'am_puck', 'am_santa', 'bf_alice', 'bf_emma', 'bf_isabella', 
  'bf_lily', 'bm_daniel', 'bm_fable', 'bm_george', 'bm_lewis'
];

//   Sub-components  

function ProviderToggle3({
  id, value, options, onChange,
}: {
  id: string;
  value: string;
  options: { value: string; icon: string; label: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <div className="sp-provider-toggle">
      {options.map(o => (
        <button
          key={o.value}
          id={`${id}-${o.value}`}
          className={`sp-toggle-btn ${value === o.value ? 'sp-toggle-btn--active' : ''}`}
          onClick={() => onChange(o.value)}
        >
          <span className="sp-toggle-icon">{o.icon}</span> {o.label}
        </button>
      ))}
    </div>
  );
}

function ProviderToggle({
  id, value, onChange,
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <ProviderToggle3
      id={id}
      value={value}
      options={[
        { value: 'google', icon: '☁', label: 'Google API' },
        { value: 'local',  icon: '🖥', label: 'Local'      },
      ]}
      onChange={onChange}
    />
  );
}

function OllamaModelSelect({
  id, value, models, fallbackLabel, onChange,
}: {
  id: string;
  value: string;
  models: string[];
  fallbackLabel: string;
  onChange: (v: string) => void;
}) {
  return (
    <select id={id} className="sp-select" value={value} onChange={e => onChange(e.target.value)}>
      {models.length > 0
        ? models.map(m => <option key={m} value={m}>{m}</option>)
        : <option value={value}>{value || fallbackLabel}</option>
      }
    </select>
  );
}

//   Component  

interface Props { onClose: () => void; }

export default function SettingsPanel({ onClose }: Props) {
  const [s, setS] = useState<Settings | null>(null);
  const [ai, setAi] = useState<AiSettings | null>(null);
  const [gen, setGen] = useState<GeneratorSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [tab, setTab] = useState<Tab>('cache');
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchSettings().then(setS);
    fetchAiSettings().then(setAi);
    fetchGeneratorSettings().then(setGen);
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

  const applyGen = useCallback(async (delta: Partial<GeneratorSettings>) => {
    setSaving(true);
    const next = await postGeneratorSettings(delta);
    if (next) setGen(next);
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
            {!s && tab !== 'ai' && tab !== 'generators' && (
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

            {/* ── Generators ── */}
            {tab === 'generators' && (
              <>
                {!gen ? (
                  <p className="sp-loading">Loading generator settings…</p>
                ) : (
                  <>
                    {/* ── Image Generation ── */}
                    <div className="sp-subsection-title">🎨 Image Generation</div>

                    <div className="sp-row sp-row--column">
                      <label className="sp-label">Provider</label>
                      <ProviderToggle3
                        id="img-provider"
                        value={gen.imageProvider}
                        options={[
                          { value: 'google',    icon: '☁',  label: 'Google API'    },
                          { value: 'stability', icon: '🎨',  label: 'Stability AI'  },
                          { value: 'comfyui',   icon: '🏛',  label: 'ComfyUI'       },
                          { value: 'local',     icon: '🖥',  label: 'Ollama'        },
                        ]}
                        onChange={v => applyGen({ imageProvider: v })}
                      />
                    </div>

                    {gen.imageProvider === 'google' && (
                      <div className="sp-hint sp-hint--info">
                        Uses <strong>Gemini 3.1 Flash Image</strong> (Nano Banana 2).
                        Requires a paid Google AI plan.
                        <a href="https://aistudio.google.com" target="_blank" rel="noreferrer" className="sp-link"> Enable billing →</a>
                      </div>
                    )}

                    {/* ── Stability AI ── */}
                    {gen.imageProvider === 'stability' && (
                      <>
                        <div className="sp-hint sp-hint--info">
                          🎨 <strong>Stability AI</strong> — cloud generation, no GPU needed.
                          Uses your <code>STABILITY_API_KEY</code> from <code>.env</code>.
                          Free credits on signup at{' '}
                          <a href="https://platform.stability.ai" target="_blank" rel="noreferrer" className="sp-link">platform.stability.ai →</a>
                        </div>

                        {/* Engine */}
                        <div className="sp-row">
                          <label className="sp-label" htmlFor="stab-model">Engine</label>
                          <select id="stab-model" className="sp-select"
                            value={gen.stabilityModel}
                            onChange={e => applyGen({ stabilityModel: e.target.value })}>
                            <option value="core">Core — fastest, best value (~2 credits)</option>
                            <option value="sd3">SD 3.5 — high quality (~4 credits)</option>
                            <option value="ultra">Ultra — best quality (~8 credits)</option>
                          </select>
                        </div>

                        {/* Style preset */}
                        <div className="sp-row">
                          <label className="sp-label" htmlFor="stab-style">Style Preset</label>
                          <select id="stab-style" className="sp-select"
                            value={gen.stabilityStyle}
                            onChange={e => applyGen({ stabilityStyle: e.target.value })}>
                            <option value="">None (default)</option>
                            <option value="photographic">Photographic</option>
                            <option value="digital-art">Digital Art</option>
                            <option value="anime">Anime</option>
                            <option value="cinematic">Cinematic</option>
                            <option value="3d-model">3D Model</option>
                            <option value="comic-book">Comic Book</option>
                            <option value="fantasy-art">Fantasy Art</option>
                            <option value="neon-punk">Neon Punk</option>
                            <option value="isometric">Isometric</option>
                            <option value="pixel-art">Pixel Art</option>
                          </select>
                        </div>

                        {/* Resolution */}
                        <div className="sp-row">
                          <label className="sp-label">Resolution</label>
                          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                            <select id="stab-width" className="sp-select"
                              value={gen.stabilityWidth}
                              onChange={e => applyGen({ stabilityWidth: parseInt(e.target.value) })}>
                              <option value={512}>512</option>
                              <option value={768}>768</option>
                              <option value={1024}>1024</option>
                              <option value={1536}>1536</option>
                            </select>
                            <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: 12 }}>×</span>
                            <select id="stab-height" className="sp-select"
                              value={gen.stabilityHeight}
                              onChange={e => applyGen({ stabilityHeight: parseInt(e.target.value) })}>
                              <option value={512}>512</option>
                              <option value={768}>768</option>
                              <option value={1024}>1024</option>
                              <option value={1536}>1536</option>
                            </select>
                          </div>
                        </div>
                      </>
                    )}

                    {gen.imageProvider === 'comfyui' && (
                      <>
                        {/* Status indicator */}
                        <div className="sp-row">
                          <label className="sp-label">Status</label>
                          <span className={`sp-badge ${gen.comfyuiRunning ? 'sp-badge--ok' : 'sp-badge--err'}`}>
                            {gen.comfyuiRunning ? '● Running' : '○ Not running'}
                          </span>
                        </div>

                        {/* Installation folder picker */}
                        <div className="sp-row">
                          <label className="sp-label" htmlFor="comfyui-path">Installation Folder</label>
                          <div style={{ display: 'flex', gap: 6, flex: 1, minWidth: 0 }}>
                            <input
                              id="comfyui-path"
                              type="text"
                              className="sp-input sp-input--wide"
                              style={{ flex: 1 }}
                              value={gen.comfyuiPath}
                              onChange={e => setGen({ ...gen, comfyuiPath: e.target.value })}
                              onBlur={e => applyGen({ comfyuiPath: e.target.value })}
                              onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                              placeholder="e.g. D:\ComfyUI"
                            />
                            <button
                              className="sp-btn sp-btn--sm"
                              title="Browse for ComfyUI folder"
                              onClick={async () => {
                                const el = (window as any).electronAPI;
                                if (!el?.showOpenDialog) return;
                                const folder: string | undefined = await el.showOpenDialog({
                                  title: 'Select ComfyUI Installation Folder',
                                  properties: ['openDirectory'],
                                });
                                if (folder) {
                                  setGen({ ...gen, comfyuiPath: folder });
                                  applyGen({ comfyuiPath: folder });
                                }
                              }}
                            >📁</button>
                          </div>
                        </div>

                        {!gen.comfyuiRunning && (
                          <div className="sp-hint sp-hint--warn">
                            {gen.comfyuiPath ? (
                              <>
                                ⚡ ComfyUI is not running — Fade will start it automatically when you generate an image.
                                <br />
                                <span style={{ opacity: 0.7, fontSize: 11 }}>Folder: <code>{gen.comfyuiPath}</code></span>
                              </>
                            ) : (
                              <>
                                ⚠ ComfyUI is not running.<br />
                                Set the Installation Folder above for auto-start, or start it manually:<br />
                                <code>python main.py --listen 127.0.0.1 --port 8188</code>
                              </>
                            )}
                          </div>
                        )}

                        <div className="sp-row">
                          <label className="sp-label" htmlFor="comfyui-url">Server URL</label>
                          <input
                            id="comfyui-url"
                            type="text"
                            className="sp-input sp-input--wide"
                            defaultValue={gen.comfyuiUrl}
                            onBlur={e => applyGen({ comfyuiUrl: e.target.value })}
                            onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                            placeholder="http://127.0.0.1:8188"
                          />
                        </div>

                        <div className="sp-row">
                          <label className="sp-label" htmlFor="comfyui-model">Checkpoint Model</label>
                          {gen.comfyuiModels.length > 0 ? (
                            <select
                              id="comfyui-model"
                              className="sp-select"
                              value={gen.comfyuiModel}
                              onChange={e => applyGen({ comfyuiModel: e.target.value })}
                            >
                              {gen.comfyuiModels.map(m => (
                                <option key={m} value={m}>{m}</option>
                              ))}
                            </select>
                          ) : (
                            <input
                              id="comfyui-model"
                              type="text"
                              className="sp-input sp-input--wide"
                              defaultValue={gen.comfyuiModel}
                              onBlur={e => applyGen({ comfyuiModel: e.target.value })}
                              onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                              placeholder="v1-5-pruned-emaonly.safetensors"
                            />
                          )}
                        </div>

                        {gen.comfyuiModels.length === 0 && gen.comfyuiRunning && (
                          <div className="sp-hint sp-hint--warn">
                            ⚠ No checkpoint models found.<br />
                            Download <strong>v1-5-pruned-emaonly.safetensors</strong> from HuggingFace and place it in:<br />
                            <code>D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\models\checkpoints</code>
                          </div>
                        )}

                        {/* Size */}
                        <div className="sp-row">
                          <label className="sp-label">Width × Height</label>
                          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                            <select id="comfyui-width" className="sp-select" value={gen.comfyuiWidth}
                              onChange={e => applyGen({ comfyuiWidth: parseInt(e.target.value) })}>
                              <option value={256}>256</option>
                              <option value={512}>512</option>
                              <option value={768}>768</option>
                              <option value={1024}>1024</option>
                            </select>
                            <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: 12 }}>×</span>
                            <select id="comfyui-height" className="sp-select" value={gen.comfyuiHeight}
                              onChange={e => applyGen({ comfyuiHeight: parseInt(e.target.value) })}>
                              <option value={256}>256</option>
                              <option value={512}>512</option>
                              <option value={768}>768</option>
                              <option value={1024}>1024</option>
                            </select>
                          </div>
                        </div>

                        {gen.comfyuiWidth > 512 && (
                          <div className="sp-hint sp-hint--warn" style={{ marginTop: 0 }}>
                            ⚠ 4GB VRAM: stay at 512×512. Higher res may OOM.
                          </div>
                        )}

                        {/* Steps */}
                        <div className="sp-row">
                          <label className="sp-label">Steps</label>
                          <input id="comfyui-steps" type="range" className="sp-range" min={10} max={50} step={5}
                            value={gen.comfyuiSteps}
                            onChange={e => setGen({ ...gen, comfyuiSteps: parseInt(e.target.value) })}
                            onMouseUp={e => applyGen({ comfyuiSteps: parseInt((e.target as HTMLInputElement).value) })}
                          />
                          <span className="sp-badge">{gen.comfyuiSteps}</span>
                        </div>

                        {/* CFG */}
                        <div className="sp-row">
                          <label className="sp-label">CFG Scale</label>
                          <input id="comfyui-cfg" type="range" className="sp-range" min={1} max={15} step={0.5}
                            value={gen.comfyuiCfg}
                            onChange={e => setGen({ ...gen, comfyuiCfg: parseFloat(e.target.value) })}
                            onMouseUp={e => applyGen({ comfyuiCfg: parseFloat((e.target as HTMLInputElement).value) })}
                          />
                          <span className="sp-badge">{gen.comfyuiCfg.toFixed(1)}</span>
                        </div>
                      </>
                    )}

                    {gen.imageProvider === 'local' && (
                      <div className="sp-row">
                        <label className="sp-label" htmlFor="img-local-model">Ollama Model</label>
                        <OllamaModelSelect
                          id="img-local-model"
                          value={gen.imageLocalModel}
                          models={gen.ollamaModels}
                          fallbackLabel="gemma3:4b"
                          onChange={v => applyGen({ imageLocalModel: v })}
                        />
                      </div>
                    )}

                    {/* ── TTS ── */}
                    <div className="sp-subsection-title">🔊 Text-to-Speech</div>

                    <div className="sp-row sp-row--column">
                      <label className="sp-label">Provider</label>
                      <ProviderToggle3
                        id="tts-provider"
                        value={gen.ttsProvider}
                        options={[
                          { value: 'google', icon: '☁', label: 'Google API' },
                          { value: 'kokoro', icon: '⚡', label: 'Kokoro (Local)' },
                          { value: 'local',  icon: '🖥', label: 'Ollama (Local)' },
                        ]}
                        onChange={v => applyGen({ ttsProvider: v })}
                      />
                    </div>

                    {gen.ttsProvider === 'google' && (
                      <div className="sp-row">
                        <label className="sp-label" htmlFor="tts-voice">Voice</label>
                        <select
                          id="tts-voice"
                          className="sp-select"
                          value={gen.ttsGoogleVoice}
                          onChange={e => applyGen({ ttsGoogleVoice: e.target.value })}
                        >
                          {GEMINI_VOICES.map(v => (
                            <option key={v} value={v}>
                              {v} — {VOICE_DESCRIPTIONS[v] ?? ''}
                            </option>
                          ))}
                        </select>
                      </div>
                    )}

                    {gen.ttsProvider === 'kokoro' && (
                      <div className="sp-row">
                        <label className="sp-label" htmlFor="tts-kokoro-voice">Voice</label>
                        <select
                          id="tts-kokoro-voice"
                          className="sp-select"
                          value={gen.ttsKokoroVoice}
                          onChange={e => applyGen({ ttsKokoroVoice: e.target.value })}
                        >
                          {KOKORO_VOICES.map(v => (
                            <option key={v} value={v}>
                              {v}
                            </option>
                          ))}
                        </select>
                      </div>
                    )}

                    {gen.ttsProvider === 'local' && (
                      <div className="sp-row">
                        <label className="sp-label" htmlFor="tts-local-model">Ollama Model</label>
                        <OllamaModelSelect
                          id="tts-local-model"
                          value={gen.ttsLocalModel}
                          models={gen.ollamaModels}
                          fallbackLabel="llama3.1"
                          onChange={v => applyGen({ ttsLocalModel: v })}
                        />
                      </div>
                    )}

                    {/* ── Video Generation ── */}
                    <div className="sp-subsection-title">🎬 Video Generation</div>

                    <div className="sp-row sp-row--column">
                      <label className="sp-label">Provider</label>
                      <ProviderToggle
                        id="vid-provider"
                        value={gen.videoProvider}
                        onChange={v => applyGen({ videoProvider: v })}
                      />
                    </div>

                    {gen.videoProvider === 'google' && (
                      <div className="sp-hint sp-hint--info">
                        Uses <strong>Veo 3.1</strong> — cinematic video with native audio.
                        Requires a paid Google AI plan. Generation takes 30–120s.
                        <a href="https://aistudio.google.com" target="_blank" rel="noreferrer" className="sp-link"> Enable billing →</a>
                      </div>
                    )}

                    {gen.videoProvider === 'local' && (
                      <div className="sp-row">
                        <label className="sp-label" htmlFor="vid-local-model">Ollama Model</label>
                        <OllamaModelSelect
                          id="vid-local-model"
                          value={gen.videoLocalModel}
                          models={gen.ollamaModels}
                          fallbackLabel="wan2.1"
                          onChange={v => applyGen({ videoLocalModel: v })}
                        />
                      </div>
                    )}

                    {/* ── Ollama Server ── */}
                    <div className="sp-subsection-title">🖥 Ollama Server</div>

                    <div className="sp-row">
                      <label className="sp-label" htmlFor="ollama-url">Server URL</label>
                      <input
                        id="ollama-url"
                        type="text"
                        className="sp-input sp-input--wide"
                        defaultValue={gen.ollamaUrl}
                        onBlur={e => applyGen({ ollamaUrl: e.target.value })}
                        onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                        placeholder="http://localhost:11434"
                      />
                    </div>

                    <div className="sp-row">
                      <label className="sp-label">Installed models</label>
                      <span className="sp-badge sp-badge--info">
                        {gen.ollamaModels.length > 0
                          ? `${gen.ollamaModels.length} model${gen.ollamaModels.length > 1 ? 's' : ''} detected`
                          : 'Ollama not running or no models installed'}
                      </span>
                    </div>

                    {gen.ollamaModels.length === 0 && (
                      <div className="sp-hint sp-hint--warn">
                        ⚠ No Ollama models found. Start Ollama and pull models:
                        <br /><code>ollama serve</code>
                        <br /><code>ollama pull kokoro</code> (TTS)
                        <br /><code>ollama pull wan2.1</code> (Video)
                      </div>
                    )}
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
