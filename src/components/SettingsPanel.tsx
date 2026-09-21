import React, { useEffect, useState, useCallback, useRef } from 'react';
import './SettingsPanel.css';

// Env key info from backend
interface EnvKeyInfo {
  value: string;
  masked: string;
  isSecret: boolean;
}
type EnvSettings = Record<string, EnvKeyInfo>;

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
  maxConcurrentIndex: number;
  availableModels: string[];
  indexProvider: string;       // 'ollama' | 'gemini'
  indexGeminiModel: string;    // e.g. 'gemini-1.5-flash'
  indexQueue: {
    maxConcurrent: number;
    active: number;
    waiting: number;
    activeIds: string[];
    waitingIds: string[];
  };
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

async function postAiSettings(delta: Partial<Pick<AiSettings,'visionModel'|'frameInterval'|'whisperBackend'|'whisperModel'|'indexProvider'|'indexGeminiModel'>>): Promise<AiSettings | null> {
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

async function fetchEnvSettings(): Promise<EnvSettings | null> {
  const port = getPort();
  if (!port) return null;
  try {
    const r = await fetch(`http://127.0.0.1:${port}/settings/env`);
    return r.ok ? r.json() : null;
  } catch { return null; }
}

async function postEnvSettings(updates: Record<string, string>): Promise<EnvSettings | null> {
  const port = getPort();
  if (!port) return null;
  try {
    const r = await fetch(`http://127.0.0.1:${port}/settings/env`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ updates }),
    });
    return r.ok ? r.json() : null;
  } catch { return null; }
}

//   Tab IDs  

type Tab = 'cache' | 'decoder' | 'output' | 'ai' | 'agent' | 'generators' | 'apis';

const TABS: { id: Tab; icon: string; label: string }[] = [
  { id: 'cache',      icon: '⚡', label: 'Cache'       },
  { id: 'decoder',    icon: '🎞', label: 'Decoder'     },
  { id: 'output',     icon: '🖼', label: 'Output'      },
  { id: 'ai',         icon: '🔍', label: 'Indexing'    },
  { id: 'agent',      icon: '🤖', label: 'Agent AI'    },
  { id: 'generators', icon: '✨', label: 'Generators'  },
  { id: 'apis',       icon: '🔑', label: 'API Keys'    },
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

// Which edge/corner is being dragged
type ResizeEdge = 'e' | 'w' | 's' | 'n' | 'se' | 'sw' | 'ne' | 'nw';

const INIT_W = 860;
const INIT_H = Math.round(window.innerHeight * 0.82);
const MIN_W  = 520;
const MIN_H  = 400;

export default function SettingsPanel({ onClose }: Props) {
  const [s, setS] = useState<Settings | null>(null);
  const [ai, setAi] = useState<AiSettings | null>(null);
  const [gen, setGen] = useState<GeneratorSettings | null>(null);
  const [env, setEnv] = useState<EnvSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [tab, setTab] = useState<Tab>('cache');
  const [showSecrets, setShowSecrets] = useState<Record<string, boolean>>({});
  const [panelW, setPanelW] = useState(INIT_W);
  const [panelH, setPanelH] = useState(INIT_H);
  const overlayRef = useRef<HTMLDivElement>(null);
  const panelRef   = useRef<HTMLDivElement>(null);
  const dragRef    = useRef<{
    edge: ResizeEdge;
    startX: number; startY: number;
    startW: number; startH: number;
  } | null>(null);

  useEffect(() => {
    fetchSettings().then(setS);
    fetchAiSettings().then(setAi);
    fetchGeneratorSettings().then(setGen);
    fetchEnvSettings().then(setEnv);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  // Resize drag logic
  const startResize = useCallback((edge: ResizeEdge) => (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragRef.current = {
      edge,
      startX: e.clientX,
      startY: e.clientY,
      startW: panelRef.current?.offsetWidth  ?? panelW,
      startH: panelRef.current?.offsetHeight ?? panelH,
    };
    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return;
      const { edge: eg, startX, startY, startW, startH } = dragRef.current;
      const dx = ev.clientX - startX;
      const dy = ev.clientY - startY;
      let nw = startW, nh = startH;
      if (eg.includes('e'))  nw = Math.max(MIN_W, startW + dx);
      if (eg.includes('w'))  nw = Math.max(MIN_W, startW - dx);
      if (eg.includes('s'))  nh = Math.max(MIN_H, startH + dy);
      if (eg.includes('n'))  nh = Math.max(MIN_H, startH - dy);
      // Clamp to viewport
      nw = Math.min(nw, window.innerWidth  - 20);
      nh = Math.min(nh, window.innerHeight - 20);
      setPanelW(nw);
      setPanelH(nh);
    };
    const onUp = () => {
      dragRef.current = null;
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup',   onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup',   onUp);
  }, [panelW, panelH]);


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

  const [agentToast, setAgentToast] = React.useState<string | null>(null);

  const restartAgent = React.useCallback(async () => {
    const port = getPort();
    if (!port) return;
    try {
      const r = await fetch(`http://127.0.0.1:${port}/ai/restart`, { method: 'POST' });
      const j = await r.json();
      if (j.ok) {
        setAgentToast(`✅ Agent restarted → ${j.provider}`);
      } else {
        setAgentToast(`❌ ${j.message}`);
      }
    } catch {
      setAgentToast('❌ Could not reach backend');
    }
    setTimeout(() => setAgentToast(null), 3000);
  }, []);

  const applyEnv = useCallback(async (key: string, value: string) => {
    setSaving(true);
    const next = await postEnvSettings({ [key]: value });
    if (next) setEnv(next);
    setSaving(false);
    // Auto-restart agent when provider or model changes so it takes effect immediately
    if (key === 'FADE_AI_PROVIDER' || key === 'FADE_AI_MODEL') {
      await restartAgent();
    }
  }, [restartAgent]);

  return (
    <div className="sp-overlay" ref={overlayRef}
      onClick={e => { if (e.target === overlayRef.current) onClose(); }}>
      <div
        className="sp-panel"
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Settings"
        style={{ width: panelW, height: panelH }}
      >
        {/* Resize handles — 4 edges + 4 corners */}
        <div className="sp-rz sp-rz--e"  onMouseDown={startResize('e')} />
        <div className="sp-rz sp-rz--w"  onMouseDown={startResize('w')} />
        <div className="sp-rz sp-rz--s"  onMouseDown={startResize('s')} />
        <div className="sp-rz sp-rz--n"  onMouseDown={startResize('n')} />
        <div className="sp-rz sp-rz--se" onMouseDown={startResize('se')} />
        <div className="sp-rz sp-rz--sw" onMouseDown={startResize('sw')} />
        <div className="sp-rz sp-rz--ne" onMouseDown={startResize('ne')} />
        <div className="sp-rz sp-rz--nw" onMouseDown={startResize('nw')} />

        {/* Agent restart toast */}
        {agentToast && (
          <div style={{
            position: 'absolute', top: 12, left: '50%', transform: 'translateX(-50%)',
            background: agentToast.startsWith('✅') ? '#1a3a2a' : '#3a1a1a',
            border: `1px solid ${agentToast.startsWith('✅') ? '#00d4aa' : '#ff6b6b'}`,
            color: '#fff', padding: '6px 16px', borderRadius: 8, fontSize: 12,
            zIndex: 999, whiteSpace: 'nowrap', boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
            pointerEvents: 'none',
          }}>
            {agentToast}
          </div>
        )}

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
            {!s && tab !== 'ai' && tab !== 'generators' && tab !== 'apis' && (
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

                    {/* ── Vision Provider ── */}
                    <div className="sp-subsection-title">🔍 Vision Provider</div>

                    <div className="sp-row">
                      <label className="sp-label" htmlFor="idx-provider">Provider</label>
                      <select id="idx-provider" className="sp-select" value={ai.indexProvider || 'ollama'}
                        onChange={e => applyAi({ indexProvider: e.target.value })}>
                        <option value="ollama">🖥 Ollama (local, no API key needed)</option>
                        <option value="gemini">✨ Google Gemini (cloud, fast)</option>
                      </select>
                    </div>

                    {/* ── Ollama section ── */}
                    {(ai.indexProvider || 'ollama') === 'ollama' && (<>
                      <div className="sp-row">
                        <label className="sp-label" htmlFor="idx-ollama-host">Ollama Endpoint</label>
                        <input id="idx-ollama-host" className="sp-api-input sp-input--wide"
                          placeholder="http://localhost:11434"
                          defaultValue={env?.OLLAMA_HOST?.value || ''}
                          onBlur={e => { if (e.target.value !== env?.OLLAMA_HOST?.value) applyEnv('OLLAMA_HOST', e.target.value); }}
                          onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                        />
                      </div>

                      <div className="sp-row">
                        <label className="sp-label" htmlFor="set-vision-model">Vision model</label>
                        <select id="set-vision-model" className="sp-select" value={ai.visionModel}
                          onChange={e => applyAi({ visionModel: e.target.value })}>
                          {ai.availableModels.length > 0
                            ? ai.availableModels.map(m => (
                                <option key={m} value={m}>{m}</option>
                              ))
                            : (<>
                                <option value="moondream">moondream (fast, ~1-2s/frame)</option>
                                <option value="llava">llava (balanced)</option>
                                <option value="llava-phi3">llava-phi3 (small)</option>
                              </>)
                          }
                        </select>
                      </div>
                    </>)}

                    {/* ── Gemini section ── */}
                    {(ai.indexProvider || 'ollama') === 'gemini' && (<>
                      <div className="sp-row">
                        <label className="sp-label" htmlFor="idx-gemini-model">Gemini model</label>
                        <select id="idx-gemini-model" className="sp-select" value={ai.indexGeminiModel || 'gemini-1.5-flash'}
                          onChange={e => applyAi({ indexGeminiModel: e.target.value })}>
                          <option value="gemini-1.5-flash">gemini-1.5-flash ★ (fast, cheap)</option>
                          <option value="gemini-1.5-pro">gemini-1.5-pro (best quality)</option>
                          <option value="gemini-2.0-flash">gemini-2.0-flash (latest)</option>
                        </select>
                      </div>
                      <div className="sp-hint">
                        Uses your <strong>GOOGLE_API_KEY</strong> from API Keys tab. No GPU or Ollama needed.
                      </div>
                    </>)}

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
                        {(ai.indexProvider || 'ollama') === 'gemini'
                          ? `~${Math.round(ai.frameInterval * 3)}s per minute of video (API)`
                          : ai.visionModel.startsWith('moondream')
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

                    {/* ── Concurrent Indexing ── */}
                    <div className="sp-subsection-title">Concurrent Indexing</div>

                    <div className="sp-row">
                      <label className="sp-label" htmlFor="set-max-index">Max concurrent jobs</label>
                      <select id="set-max-index" className="sp-select" value={ai.maxConcurrentIndex}
                        onChange={e => applyAi({ maxConcurrentIndex: parseInt(e.target.value) } as any)}>
                        <option value={1}>1 (safest, least RAM)</option>
                        <option value={2}>2 (balanced) ★</option>
                        <option value={3}>3</option>
                        <option value={4}>4</option>
                        <option value={5}>5 (fast, more RAM)</option>
                      </select>
                    </div>

                    {ai.indexQueue && (
                      <div className="sp-row">
                        <label className="sp-label">Queue status</label>
                        <span className="sp-badge sp-badge--info">
                          {ai.indexQueue.active} active / {ai.indexQueue.waiting} waiting
                        </span>
                      </div>
                    )}
                  </>
                )}
              </>
            )}

            {/* ── Agent AI ── */}
            {tab === 'agent' && (
              <>
                {!env ? (
                  <p className="sp-loading">Loading agent settings…</p>
                ) : (
                  <>
                    <p className="sp-hint">
                      Choose which AI model powers the agentic editor. Changes take effect after clicking <strong>Restart Agent</strong>.
                    </p>

                    {/* Provider */}
                    <div className="sp-subsection-title">🤖 Agent Provider</div>

                    <div className="sp-row">
                      <label className="sp-label" htmlFor="agent-provider">Provider</label>
                      <select id="agent-provider" className="sp-select"
                        value={env.FADE_AI_PROVIDER?.value || 'ollama'}
                        onChange={e => applyEnv('FADE_AI_PROVIDER', e.target.value)}>
                        <option value="ollama">🖥 Ollama (Local)</option>
                        <option value="llamacpp">🦙 llama.cpp (Local / Tailscale)</option>
                        <option value="openrouter">🌐 OpenRouter (Free/Paid)</option>
                        <option value="tokenrouter">🔗 TokenRouter</option>
                        <option value="openai">OpenAI</option>
                        <option value="gemini">Google Gemini</option>
                        <option value="claude">Anthropic Claude</option>
                        <option value="groq">⚡ Groq (Fast Free)</option>
                        <option value="tabi">Tabi</option>
                      </select>
                    </div>

                    <div className="sp-row">
                      <label className="sp-label" htmlFor="agent-model">Model Name</label>
                      <input id="agent-model" className="sp-api-input sp-input--wide"
                        placeholder={
                          (env.FADE_AI_PROVIDER?.value || 'ollama') === 'ollama'         ? 'auto-detect' :
                          (env.FADE_AI_PROVIDER?.value || 'ollama') === 'llamacpp'       ? 'auto-detect (llama.cpp ignores this)' :
                          (env.FADE_AI_PROVIDER?.value || 'ollama') === 'openrouter'     ? 'e.g. mistralai/mistral-7b-instruct' :
                          (env.FADE_AI_PROVIDER?.value || 'ollama') === 'openai'         ? 'e.g. gpt-4o-mini' :
                          (env.FADE_AI_PROVIDER?.value || 'ollama') === 'gemini'         ? 'e.g. gemini-1.5-flash' :
                          (env.FADE_AI_PROVIDER?.value || 'ollama') === 'claude'         ? 'e.g. claude-3-5-haiku-20241022' :
                          (env.FADE_AI_PROVIDER?.value || 'ollama') === 'groq'           ? 'e.g. llama3-8b-8192' :
                          (env.FADE_AI_PROVIDER?.value || 'ollama') === 'tokenrouter'    ? 'e.g. z-ai/glm-5.3-free' :
                          'model name'
                        }
                        defaultValue={env.FADE_AI_MODEL?.value || ''}
                        onBlur={e => applyEnv('FADE_AI_MODEL', e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                      />
                    </div>

                    {/* Ollama-specific */}
                    {(env.FADE_AI_PROVIDER?.value || 'ollama') === 'ollama' && (
                      <>
                        <div className="sp-subsection-title">🖥 Ollama Local Server</div>
                        <div className="sp-row">
                          <label className="sp-label" htmlFor="agent-ollama-host">Ollama Endpoint</label>
                          <input id="agent-ollama-host" className="sp-api-input sp-input--wide"
                            placeholder="http://localhost:11434"
                            defaultValue={env.OLLAMA_HOST?.value || ''}
                            onBlur={e => applyEnv('OLLAMA_HOST', e.target.value)}
                            onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                          />
                        </div>
                        {gen && gen.ollamaModels.length > 0 && (
                          <div className="sp-row">
                            <label className="sp-label">Detected models</label>
                            <span className="sp-badge sp-badge--info">
                              {gen.ollamaModels.filter(m => !['moondream','llava','nomic-embed','mxbai'].some(v => m.toLowerCase().includes(v))).join(', ') || 'No tool-capable models'}
                            </span>
                          </div>
                        )}
                        {gen && gen.ollamaModels.length === 0 && (
                          <div className="sp-hint sp-hint--warn">
                            ⚠ Ollama not running or no models installed.<br />
                            <code>ollama serve</code> then <code>ollama pull llama3.2</code>
                          </div>
                        )}
                      </>
                    )}

                    {/* OpenRouter-specific */}
                    {(env.FADE_AI_PROVIDER?.value) === 'openrouter' && (
                      <>
                        <div className="sp-subsection-title">🌐 OpenRouter</div>
                        <div className="sp-hint sp-hint--info">
                          Free models available at <a href="https://openrouter.ai/models?q=free" target="_blank" rel="noreferrer" className="sp-link">openrouter.ai/models →</a>.
                          Get your key at <a href="https://openrouter.ai/keys" target="_blank" rel="noreferrer" className="sp-link">openrouter.ai/keys →</a>
                        </div>
                        <div className="sp-api-row">
                          <span className="sp-api-label">API Key</span>
                          <div className="sp-api-field">
                            <input className="sp-api-input"
                              type={showSecrets['OPENROUTER_API_KEY'] ? 'text' : 'password'}
                              defaultValue={env.OPENROUTER_API_KEY?.value || ''}
                              placeholder="sk-or-..."
                              onBlur={e => { if (e.target.value !== env.OPENROUTER_API_KEY?.value) applyEnv('OPENROUTER_API_KEY', e.target.value); }}
                              onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                            />
                            <button className="sp-api-btn" onClick={() => setShowSecrets(p => ({ ...p, OPENROUTER_API_KEY: !p.OPENROUTER_API_KEY }))}>
                              {showSecrets['OPENROUTER_API_KEY'] ? '🙈' : '👁'}
                            </button>
                            <span className={`sp-api-status ${env.OPENROUTER_API_KEY?.value ? 'sp-api-status--set' : 'sp-api-status--empty'}`}>
                              {env.OPENROUTER_API_KEY?.value ? '✓' : '✗'}
                            </span>
                          </div>
                        </div>
                      </>
                    )}

                    {/* TokenRouter-specific */}
                    {(env.FADE_AI_PROVIDER?.value) === 'tokenrouter' && (
                      <>
                        <div className="sp-subsection-title">🔗 TokenRouter</div>
                        <div className="sp-api-row">
                          <span className="sp-api-label">API Key</span>
                          <div className="sp-api-field">
                            <input className="sp-api-input"
                              type={showSecrets['TOKENROUTER_API_KEY'] ? 'text' : 'password'}
                              defaultValue={env.TOKENROUTER_API_KEY?.value || ''}
                              placeholder="Not set"
                              onBlur={e => { if (e.target.value !== env.TOKENROUTER_API_KEY?.value) applyEnv('TOKENROUTER_API_KEY', e.target.value); }}
                              onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                            />
                            <button className="sp-api-btn" onClick={() => setShowSecrets(p => ({ ...p, TOKENROUTER_API_KEY: !p.TOKENROUTER_API_KEY }))}>
                              {showSecrets['TOKENROUTER_API_KEY'] ? '🙈' : '👁'}
                            </button>
                            <span className={`sp-api-status ${env.TOKENROUTER_API_KEY?.value ? 'sp-api-status--set' : 'sp-api-status--empty'}`}>
                              {env.TOKENROUTER_API_KEY?.value ? '✓' : '✗'}
                            </span>
                          </div>
                        </div>
                        <div className="sp-api-row">
                          <span className="sp-api-label">Base URL</span>
                          <div className="sp-api-field">
                            <input className="sp-api-input" placeholder="https://api.tokenrouter.com/v1"
                              defaultValue={env.TOKENROUTER_BASE_URL?.value || ''}
                              onBlur={e => { if (e.target.value !== env.TOKENROUTER_BASE_URL?.value) applyEnv('TOKENROUTER_BASE_URL', e.target.value); }}
                              onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                            />
                          </div>
                        </div>
                      </>
                    )}

                    {/* OpenAI key */}
                    {(env.FADE_AI_PROVIDER?.value) === 'openai' && (
                      <div className="sp-api-row">
                        <span className="sp-api-label">OpenAI API Key</span>
                        <div className="sp-api-field">
                          <input className="sp-api-input" type={showSecrets['OPENAI_API_KEY'] ? 'text' : 'password'}
                            defaultValue={env.OPENAI_API_KEY?.value || ''} placeholder="sk-..."
                            onBlur={e => { if (e.target.value !== env.OPENAI_API_KEY?.value) applyEnv('OPENAI_API_KEY', e.target.value); }}
                            onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                          />
                          <button className="sp-api-btn" onClick={() => setShowSecrets(p => ({ ...p, OPENAI_API_KEY: !p.OPENAI_API_KEY }))}>
                            {showSecrets['OPENAI_API_KEY'] ? '🙈' : '👁'}
                          </button>
                          <span className={`sp-api-status ${env.OPENAI_API_KEY?.value ? 'sp-api-status--set' : 'sp-api-status--empty'}`}>
                            {env.OPENAI_API_KEY?.value ? '✓' : '✗'}
                          </span>
                        </div>
                      </div>
                    )}

                    {/* Gemini key */}
                    {(env.FADE_AI_PROVIDER?.value) === 'gemini' && (
                      <div className="sp-api-row">
                        <span className="sp-api-label">Google API Key</span>
                        <div className="sp-api-field">
                          <input className="sp-api-input" type={showSecrets['GOOGLE_API_KEY'] ? 'text' : 'password'}
                            defaultValue={env.GOOGLE_API_KEY?.value || ''} placeholder="AIza..."
                            onBlur={e => { if (e.target.value !== env.GOOGLE_API_KEY?.value) applyEnv('GOOGLE_API_KEY', e.target.value); }}
                            onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                          />
                          <button className="sp-api-btn" onClick={() => setShowSecrets(p => ({ ...p, GOOGLE_API_KEY: !p.GOOGLE_API_KEY }))}>
                            {showSecrets['GOOGLE_API_KEY'] ? '🙈' : '👁'}
                          </button>
                          <span className={`sp-api-status ${env.GOOGLE_API_KEY?.value ? 'sp-api-status--set' : 'sp-api-status--empty'}`}>
                            {env.GOOGLE_API_KEY?.value ? '✓' : '✗'}
                          </span>
                        </div>
                      </div>
                    )}

                    {/* Anthropic key */}
                    {(env.FADE_AI_PROVIDER?.value) === 'claude' && (
                      <div className="sp-api-row">
                        <span className="sp-api-label">Anthropic API Key</span>
                        <div className="sp-api-field">
                          <input className="sp-api-input" type={showSecrets['ANTHROPIC_API_KEY'] ? 'text' : 'password'}
                            defaultValue={env.ANTHROPIC_API_KEY?.value || ''} placeholder="sk-ant-..."
                            onBlur={e => { if (e.target.value !== env.ANTHROPIC_API_KEY?.value) applyEnv('ANTHROPIC_API_KEY', e.target.value); }}
                            onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                          />
                          <button className="sp-api-btn" onClick={() => setShowSecrets(p => ({ ...p, ANTHROPIC_API_KEY: !p.ANTHROPIC_API_KEY }))}>
                            {showSecrets['ANTHROPIC_API_KEY'] ? '🙈' : '👁'}
                          </button>
                          <span className={`sp-api-status ${env.ANTHROPIC_API_KEY?.value ? 'sp-api-status--set' : 'sp-api-status--empty'}`}>
                            {env.ANTHROPIC_API_KEY?.value ? '✓' : '✗'}
                          </span>
                        </div>
                      </div>
                    )}

                    {/* Groq key */}
                    {(env.FADE_AI_PROVIDER?.value) === 'groq' && (
                      <div className="sp-api-row">
                        <span className="sp-api-label">Groq API Key</span>
                        <div className="sp-api-field">
                          <input className="sp-api-input" type={showSecrets['GROQ_API_KEY'] ? 'text' : 'password'}
                            defaultValue={env.GROQ_API_KEY?.value || ''} placeholder="gsk_..."
                            onBlur={e => { if (e.target.value !== env.GROQ_API_KEY?.value) applyEnv('GROQ_API_KEY', e.target.value); }}
                            onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                          />
                          <button className="sp-api-btn" onClick={() => setShowSecrets(p => ({ ...p, GROQ_API_KEY: !p.GROQ_API_KEY }))}>
                            {showSecrets['GROQ_API_KEY'] ? '🙈' : '👁'}
                          </button>
                          <span className={`sp-api-status ${env.GROQ_API_KEY?.value ? 'sp-api-status--set' : 'sp-api-status--empty'}`}>
                            {env.GROQ_API_KEY?.value ? '✓' : '✗'}
                          </span>
                        </div>
                      </div>
                    )}

                    {/* llama.cpp-specific */}
                    {(env.FADE_AI_PROVIDER?.value) === 'llamacpp' && (
                      <>
                        <div className="sp-subsection-title">🦙 llama.cpp Server</div>
                        <div className="sp-hint sp-hint--info">
                          Point to any machine running <code>llama-server</code> — localhost, LAN, or Tailscale IP.
                          The server must have <code>--jinja</code> flag enabled for tool-calling support.
                        </div>
                        <div className="sp-row">
                          <label className="sp-label" htmlFor="agent-llamacpp-url">Server URL</label>
                          <input id="agent-llamacpp-url" className="sp-api-input sp-input--wide"
                            placeholder="http://100.88.241.12:8080/v1"
                            defaultValue={env.LLAMACPP_BASE_URL?.value || ''}
                            onBlur={e => { if (e.target.value !== env.LLAMACPP_BASE_URL?.value) applyEnv('LLAMACPP_BASE_URL', e.target.value); }}
                            onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                          />
                        </div>
                        <div className="sp-hint" style={{ marginTop: 4, fontSize: 11 }}>
                          Start llama.cpp:&nbsp;
                          <code>llama-server -m model.gguf --port 8080 --jinja -fa -ngl 99</code>
                        </div>
                      </>
                    )}

                    {/* Restart button */}
                    <div style={{ marginTop: 20, display: 'flex', alignItems: 'center', gap: 12 }}>
                      <button
                        id="agent-restart-btn"
                        style={{ background: 'linear-gradient(135deg,#6c63ff,#00d4aa)', color: '#fff', fontWeight: 600, padding: '8px 20px', borderRadius: 8, border: 'none', cursor: 'pointer', fontSize: 13 }}
                        onClick={restartAgent}
                      >
                        🔄 Restart Agent
                      </button>
                      <span className="sp-hint" style={{ margin: 0, fontSize: 11 }}>
                        Use after entering a new API key. Provider/model changes auto-restart.
                      </span>
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
                      <>
                        <div className="sp-api-row">
                          <span className="sp-api-label">Google API Key</span>
                          <div className="sp-api-field">
                            <input className="sp-api-input"
                              type={showSecrets['IMG_GOOGLE_API_KEY'] ? 'text' : 'password'}
                              defaultValue={env?.GOOGLE_API_KEY?.value || ''}
                              placeholder="AIza..."
                              onBlur={e => { if (e.target.value !== env?.GOOGLE_API_KEY?.value) applyEnv('GOOGLE_API_KEY', e.target.value); }}
                              onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                            />
                            <button className="sp-api-btn" onClick={() => setShowSecrets(p => ({ ...p, IMG_GOOGLE_API_KEY: !p.IMG_GOOGLE_API_KEY }))}>
                              {showSecrets['IMG_GOOGLE_API_KEY'] ? '🙈' : '👁'}
                            </button>
                            <span className={`sp-api-status ${env?.GOOGLE_API_KEY?.value ? 'sp-api-status--set' : 'sp-api-status--empty'}`}>
                              {env?.GOOGLE_API_KEY?.value ? '✓' : '✗'}
                            </span>
                          </div>
                        </div>
                        <div className="sp-hint sp-hint--info">
                          Uses <strong>Gemini Flash Image</strong>. Requires a Google AI API key.
                          <a href="https://aistudio.google.com" target="_blank" rel="noreferrer" className="sp-link"> Get key →</a>
                        </div>
                      </>
                    )}

                    {/* ── Stability AI ── */}
                    {gen.imageProvider === 'stability' && (
                      <>
                        <div className="sp-api-row">
                          <span className="sp-api-label">Stability API Key</span>
                          <div className="sp-api-field">
                            <input className="sp-api-input"
                              type={showSecrets['STABILITY_API_KEY'] ? 'text' : 'password'}
                              defaultValue={env?.STABILITY_API_KEY?.value || ''}
                              placeholder="sk-..."
                              onBlur={e => { if (e.target.value !== env?.STABILITY_API_KEY?.value) applyEnv('STABILITY_API_KEY', e.target.value); }}
                              onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                            />
                            <button className="sp-api-btn" onClick={() => setShowSecrets(p => ({ ...p, STABILITY_API_KEY: !p.STABILITY_API_KEY }))}>
                              {showSecrets['STABILITY_API_KEY'] ? '🙈' : '👁'}
                            </button>
                            <span className={`sp-api-status ${env?.STABILITY_API_KEY?.value ? 'sp-api-status--set' : 'sp-api-status--empty'}`}>
                              {env?.STABILITY_API_KEY?.value ? '✓' : '✗'}
                            </span>
                          </div>
                        </div>
                        <div className="sp-hint sp-hint--info">
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
                      <>
                        <div className="sp-row">
                          <label className="sp-label" htmlFor="img-ollama-host">Ollama Endpoint</label>
                          <input id="img-ollama-host" className="sp-api-input sp-input--wide"
                            placeholder="http://localhost:11434"
                            defaultValue={env?.OLLAMA_HOST?.value || ''}
                            onBlur={e => { if (e.target.value !== env?.OLLAMA_HOST?.value) applyEnv('OLLAMA_HOST', e.target.value); }}
                            onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                          />
                        </div>
                        <div className="sp-row">
                          <label className="sp-label" htmlFor="img-local-model">Model</label>
                          <OllamaModelSelect
                            id="img-local-model"
                            value={gen.imageLocalModel}
                            models={gen.ollamaModels}
                            fallbackLabel="gemma3:4b"
                            onChange={v => applyGen({ imageLocalModel: v })}
                          />
                        </div>
                      </>
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
                      <>
                        <div className="sp-api-row">
                          <span className="sp-api-label">Google API Key</span>
                          <div className="sp-api-field">
                            <input className="sp-api-input"
                              type={showSecrets['TTS_GOOGLE_API_KEY'] ? 'text' : 'password'}
                              defaultValue={env?.GOOGLE_API_KEY?.value || ''}
                              placeholder="AIza..."
                              onBlur={e => { if (e.target.value !== env?.GOOGLE_API_KEY?.value) applyEnv('GOOGLE_API_KEY', e.target.value); }}
                              onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                            />
                            <button className="sp-api-btn" onClick={() => setShowSecrets(p => ({ ...p, TTS_GOOGLE_API_KEY: !p.TTS_GOOGLE_API_KEY }))}>
                              {showSecrets['TTS_GOOGLE_API_KEY'] ? '🙈' : '👁'}
                            </button>
                            <span className={`sp-api-status ${env?.GOOGLE_API_KEY?.value ? 'sp-api-status--set' : 'sp-api-status--empty'}`}>
                              {env?.GOOGLE_API_KEY?.value ? '✓' : '✗'}
                            </span>
                          </div>
                        </div>
                        <div className="sp-row">
                          <label className="sp-label" htmlFor="tts-voice">Voice</label>
                          <select id="tts-voice" className="sp-select"
                            value={gen.ttsGoogleVoice}
                            onChange={e => applyGen({ ttsGoogleVoice: e.target.value })}
                          >
                            {GEMINI_VOICES.map(v => (
                              <option key={v} value={v}>{v} — {VOICE_DESCRIPTIONS[v] ?? ''}</option>
                            ))}
                          </select>
                        </div>
                      </>
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
                      <>
                        <div className="sp-api-row">
                          <span className="sp-api-label">Google API Key</span>
                          <div className="sp-api-field">
                            <input className="sp-api-input"
                              type={showSecrets['VID_GOOGLE_API_KEY'] ? 'text' : 'password'}
                              defaultValue={env?.GOOGLE_API_KEY?.value || ''}
                              placeholder="AIza..."
                              onBlur={e => { if (e.target.value !== env?.GOOGLE_API_KEY?.value) applyEnv('GOOGLE_API_KEY', e.target.value); }}
                              onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                            />
                            <button className="sp-api-btn" onClick={() => setShowSecrets(p => ({ ...p, VID_GOOGLE_API_KEY: !p.VID_GOOGLE_API_KEY }))}>
                              {showSecrets['VID_GOOGLE_API_KEY'] ? '🙈' : '👁'}
                            </button>
                            <span className={`sp-api-status ${env?.GOOGLE_API_KEY?.value ? 'sp-api-status--set' : 'sp-api-status--empty'}`}>
                              {env?.GOOGLE_API_KEY?.value ? '✓' : '✗'}
                            </span>
                          </div>
                        </div>
                        <div className="sp-hint sp-hint--info">
                          Uses <strong>Veo 3.1</strong> — cinematic video with native audio. Generation takes 30–120s.
                          <a href="https://aistudio.google.com" target="_blank" rel="noreferrer" className="sp-link"> Get key →</a>
                        </div>
                      </>
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

      
            {tab === 'apis' && (
              <>
                {!env ? (
                  <p className="sp-loading">Loading API settings…</p>
                ) : (
                  <>
                    <div className="sp-hint sp-hint--info">
                      Keys saved to local <code>.env</code> file. Configure the <strong>Agent AI</strong> tab to change which provider powers the AI editor.
                    </div>

                    {/* ── LLM API Keys ── */}
                    <div className="sp-api-group">
                      <div className="sp-api-group-title"><span className="sp-api-icon">🔑</span> LLM API Keys</div>
                      {([
                        ['OPENAI_API_KEY',      'OpenAI'],
                        ['GOOGLE_API_KEY',      'Google'],
                        ['ANTHROPIC_API_KEY',   'Anthropic'],
                        ['GROQ_API_KEY',        'Groq'],
                        ['OPENROUTER_API_KEY',  'OpenRouter'],
                      ] as [string, string][]).map(([key, label]) => (
                        <div className="sp-api-row" key={key}>
                          <span className="sp-api-label">{label} API Key</span>
                          <div className="sp-api-field">
                            <input
                              className="sp-api-input"
                              type={showSecrets[key] ? 'text' : 'password'}
                              defaultValue={env[key]?.value || ''}
                              placeholder="Not set"
                              onBlur={e => { if (e.target.value !== env[key]?.value) applyEnv(key, e.target.value); }}
                              onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                            />
                            <button className="sp-api-btn"
                              onClick={() => setShowSecrets(p => ({ ...p, [key]: !p[key] }))}>
                              {showSecrets[key] ? '🙈' : '👁'}
                            </button>
                            <span className={`sp-api-status ${env[key]?.value ? 'sp-api-status--set' : 'sp-api-status--empty'}`}>
                              {env[key]?.value ? '✓' : '✗'}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* ── TokenRouter / Tabi ── */}
                    <div className="sp-api-group">
                      <div className="sp-api-group-title"><span className="sp-api-icon">🔗</span> TokenRouter / Tabi</div>
                      {([
                        ['TOKENROUTER_API_KEY',  'TokenRouter Key',  true],
                        ['TOKENROUTER_BASE_URL', 'TokenRouter URL',  false],
                        ['TABI_API_KEY',         'Tabi Key',         true],
                        ['TABI_BASE_URL',        'Tabi URL',         false],
                      ] as [string, string, boolean][]).map(([key, label, isKey]) => (
                        <div className="sp-api-row" key={key}>
                          <span className="sp-api-label">{label}</span>
                          <div className="sp-api-field">
                            <input
                              className="sp-api-input"
                              type={isKey && !showSecrets[key] ? 'password' : 'text'}
                              defaultValue={env[key]?.value || ''}
                              placeholder={isKey ? 'Not set' : 'https://…'}
                              onBlur={e => { if (e.target.value !== env[key]?.value) applyEnv(key, e.target.value); }}
                              onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                            />
                            {isKey && (
                              <>
                                <button className="sp-api-btn"
                                  onClick={() => setShowSecrets(p => ({ ...p, [key]: !p[key] }))}>
                                  {showSecrets[key] ? '🙈' : '👁'}
                                </button>
                                <span className={`sp-api-status ${env[key]?.value ? 'sp-api-status--set' : 'sp-api-status--empty'}`}>
                                  {env[key]?.value ? '✓' : '✗'}
                                </span>
                              </>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* ── Custom Base URLs ── */}
                    <div className="sp-api-group">
                      <div className="sp-api-group-title"><span className="sp-api-icon">🌐</span> Custom Base URLs</div>
                      {([
                        ['ANTHROPIC_BASE_URL',   'Anthropic URL',   'https://api.anthropic.com'],
                        ['OPENROUTER_BASE_URL',  'OpenRouter URL',  'https://openrouter.ai/api/v1'],
                      ] as [string, string, string][]).map(([key, label, ph]) => (
                        <div className="sp-api-row" key={key}>
                          <span className="sp-api-label">{label}</span>
                          <div className="sp-api-field">
                            <input className="sp-api-input" placeholder={ph}
                              defaultValue={env[key]?.value || ''}
                              onBlur={e => { if (e.target.value !== env[key]?.value) applyEnv(key, e.target.value); }}
                              onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* ── Stability / YouTube ── */}
                    <div className="sp-api-group">
                      <div className="sp-api-group-title"><span className="sp-api-icon">🎨</span> Stability AI &amp; YouTube</div>
                      {([
                        ['STABILITY_API_KEY',    'Stability Key',    true],
                        ['YOUTUBE_CLIENT_ID',    'YouTube Client ID', false],
                        ['YOUTUBE_CLIENT_SECRET','YouTube Secret',   true],
                      ] as [string, string, boolean][]).map(([key, label, isSecret]) => (
                        <div className="sp-api-row" key={key}>
                          <span className="sp-api-label">{label}</span>
                          <div className="sp-api-field">
                            <input
                              className="sp-api-input"
                              type={isSecret && !showSecrets[key] ? 'password' : 'text'}
                              defaultValue={env[key]?.value || ''}
                              placeholder="Not set"
                              onBlur={e => { if (e.target.value !== env[key]?.value) applyEnv(key, e.target.value); }}
                              onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                            />
                            {isSecret && (
                              <button className="sp-api-btn"
                                onClick={() => setShowSecrets(p => ({ ...p, [key]: !p[key] }))}>
                                {showSecrets[key] ? '🙈' : '👁'}
                              </button>
                            )}
                            <span className={`sp-api-status ${env[key]?.value ? 'sp-api-status--set' : 'sp-api-status--empty'}`}>
                              {env[key]?.value ? '✓' : '✗'}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>

                    <div className="sp-hint sp-hint--warn">
                      ⚠ Restart the AI agent after changing provider or keys for changes to take full effect.
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
