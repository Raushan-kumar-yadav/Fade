import { useState, useRef, useEffect } from 'react'
import './ExportWorkspace.css'
import { exportApi, type ExportProgress } from '../api/toolsApi'

interface Format { id: string; label: string; icon: string; desc: string; w: number; h: number; ext: string }

const FORMATS: Format[] = [
  { id: 'mp4-1080',  label: 'MP4 1080p',   icon: '▶', desc: 'H.264, AAC · 1920×1080', w: 1920, h: 1080, ext: 'mp4' },
  { id: 'mp4-4k',    label: 'MP4 4K',      icon: '▶', desc: 'H.264 · 3840×2160',      w: 3840, h: 2160, ext: 'mp4' },
  { id: 'mp4-720',   label: 'MP4 720p',    icon: '▷', desc: 'H.264 · 1280×720',       w: 1280, h:  720, ext: 'mp4' },
  { id: 'shorts',    label: 'YT Shorts',   icon: '↕', desc: '1080×1920, 60s max',     w: 1080, h: 1920, ext: 'mp4' },
  { id: 'reels',     label: 'IG Reels',    icon: '◈', desc: '1080×1920, AAC',         w: 1080, h: 1920, ext: 'mp4' },
  { id: 'webm',      label: 'WebM VP9',    icon: '▸', desc: 'Open format · 1920×1080',w: 1920, h: 1080, ext: 'webm' },
  { id: 'gif',       label: 'GIF',         icon: '◉', desc: 'Animated · 854×480',     w:  854, h:  480, ext: 'gif' },
]

const FPS_OPTIONS   = ['24', '25', '30', '50', '60']
const PRESET_OPTIONS= ['ultrafast','superfast','veryfast','faster','fast','medium','slow','slower','veryslow']
const AUDIO_SR      = [{ v: '44100', l: '44.1 kHz' }, { v: '48000', l: '48 kHz' }]
const AUDIO_CH      = [{ v: '2', l: 'Stereo' }, { v: '6', l: '5.1 Surround' }]
const AUDIO_BR      = ['96k','128k','192k','256k','320k']

function estimatedMB(w: number, h: number, fpsVal: number, durSec: number, kbps: number): string {
  const totalKb = kbps * durSec
  return (totalKb / 8 / 1024).toFixed(0) + ' MB'
}

export default function ExportWorkspace() {
  const [selected,    setSelected]    = useState<string>('mp4-1080')
  const [fps,         setFps]         = useState<string>('30')
  const [outputPath,  setOutputPath]  = useState<string>('fade_export.mp4')
  const [jobId,       setJobId]       = useState<string | null>(null)
  const [progress,    setProgress]    = useState<ExportProgress | null>(null)
  const [webcompPhase, setWebcompPhase] = useState<{ active: boolean; done: number; total: number } | null>(null)

  // Quality controls
  const [qualityMode, setQualityMode] = useState<'crf' | 'bitrate'>('crf')
  const [crf,         setCrf]         = useState<number>(22)
  const [videoBr,     setVideoBr]     = useState<string>('8')   // in Mbps
  const [preset,      setPreset]      = useState<string>('medium')

  // Audio controls
  const [audioBr,     setAudioBr]     = useState<string>('192k')
  const [audioSR,     setAudioSR]     = useState<string>('48000')
  const [audioCh,     setAudioCh]     = useState<string>('2')

  const pollRef    = useRef<ReturnType<typeof setInterval> | null>(null)
  const cleanupRef = useRef<(() => void) | null>(null)
  const wcCleanup  = useRef<(() => void) | null>(null)

  const fmt = FORMATS.find(f => f.id === selected)!

  const stopPoll = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  }
  useEffect(() => () => { stopPoll(); cleanupRef.current?.(); wcCleanup.current?.() }, [])

  // Resolve real Videos folder from Electron on mount
  useEffect(() => {
    const api = (window as any).electronAPI
    if (!api?.getAppPath) return
    api.getAppPath('videos').then((videosDir: string | null) => {
      const sep = videosDir?.includes('/') ? '/' : '\\'
      const dir = videosDir ?? ''
      setOutputPath(dir ? `${dir}${sep}fade_export.${fmt.ext}` : `fade_export.${fmt.ext}`)
    }).catch(() => {})
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Update default output path extension when format changes
  useEffect(() => {
    setOutputPath(p => {
      const base = p.replace(/\.[^.]+$/, '')
      return `${base}.${fmt.ext}`
    })
  }, [selected, fmt.ext])

  // Rough duration estimate from playback state
  const [durSec, setDurSec] = useState<number>(10)
  useEffect(() => {
    const api = (window as any).electronAPI
    if (!api) return
    api.getPort?.().then(async (port: number | null) => {
      if (!port) return
      try {
        const r = await fetch(`http://127.0.0.1:${port}/playback/state`)
        const s = await r.json()
        if (s.totalFrames) setDurSec(s.totalFrames / parseFloat(fps))
      } catch {}
    })
  }, [fps])

  async function startExport() {
    const api = (window as any).electronAPI

    // ── Native GPU export path ────────────────────────────────────────────────
    if (api?.startExport && api?.onExportProgress) {
      setJobId('native')
      setProgress({ jobId: 'native', frame: 0, total: 0, percent: 0, done: false, error: null, path: null })
      setWebcompPhase(null)

      cleanupRef.current?.()
      wcCleanup.current?.()

      // Listen for WebComp pre-render phase
      if (api.onExportWebcompPhase) {
        wcCleanup.current = api.onExportWebcompPhase(
          (p: { active: boolean; done: number; total: number }) => {
            setWebcompPhase(p.total > 0 ? p : null)
          }
        )
      }

      cleanupRef.current = api.onExportProgress(
        (p: { frame: number; total: number; done: boolean; error: string; status?: string }) => {
          const pct = p.total > 0 ? Math.round((p.frame / p.total) * 100) : 0
          setProgress({
            jobId: 'native', frame: p.frame, total: p.total,
            percent: pct, done: p.done, error: p.error || null,
            path: p.done && !p.error ? outputPath : null,
            status: p.status,
          })
          if (p.done) {
            cleanupRef.current?.(); cleanupRef.current = null
            wcCleanup.current?.();  wcCleanup.current  = null
            setJobId(null)
            setWebcompPhase(null)
          }
        }
      )

      api.startExport({
        outputPath,
        width:        fmt.w,
        height:       fmt.h,
        fps:          parseFloat(fps),
        codec:        'auto',
        videoBitrate: `${videoBr}M`,
        crf:          qualityMode === 'crf' ? crf : -1,
        preset,
        audioBitrate: audioBr,
        audioSampleRate: parseInt(audioSR),
        audioChannels:   parseInt(audioCh),
      })
      return
    }

    // ── Python software-render fallback ───────────────────────────────────────
    try {
      const res = await exportApi.start({
        outputPath,
        width:    fmt.w,
        height:   fmt.h,
        fps:      parseFloat(fps),
        formatId: selected,
        videoBitrate: `${videoBr}M`,
        crf:      qualityMode === 'crf' ? crf : -1,
        preset,
        audioBitrate: audioBr,
        audioSampleRate: parseInt(audioSR),
        audioChannels:   parseInt(audioCh),
      })
      setJobId(res.jobId)
      setProgress({ jobId: res.jobId, frame: 0, total: res.total, percent: 0, done: false, error: null, path: null })
      pollRef.current = setInterval(async () => {
        try {
          const p = await exportApi.progress(res.jobId)
          setProgress(p)
          if (p.done) stopPoll()
        } catch { stopPoll() }
      }, 500)
    } catch (err: any) {
      alert(`Export failed: ${err.message}`)
    }
  }

  async function cancelExport() {
    const api = (window as any).electronAPI
    if (jobId === 'native') {
      api?.cancelExport()
      cleanupRef.current?.(); cleanupRef.current = null
      wcCleanup.current?.();  wcCleanup.current  = null
    } else if (jobId) {
      await exportApi.cancel(jobId); stopPoll()
    }
    setProgress(null); setJobId(null); setWebcompPhase(null)
  }

  function browseOutput() {
    const api = (window as any).electronAPI
    if (api?.showSaveDialog) {
      api.showSaveDialog({
        filters:     [{ name: 'Video', extensions: [fmt.ext] }],
        defaultPath: outputPath,
      }).then((p: string | undefined) => { if (p) setOutputPath(p) })
    }
  }

  const exporting = !!jobId && !progress?.done
  const pct       = progress?.percent ?? 0
  const wcPct     = webcompPhase && webcompPhase.total > 0
    ? Math.round((webcompPhase.done / webcompPhase.total) * 100) : 0
  const estSize   = estimatedMB(fmt.w, fmt.h, parseFloat(fps), durSec,
    qualityMode === 'crf' ? (3000 + (28 - crf) * 400) : parseFloat(videoBr) * 1000)

  return (
    <div className="export-ws">
      {/* ── Left: Format selector ─────────────────────────────────────── */}
      <div className="export-ws__left">
        <h2>Output Format</h2>
        <div className="export-formats">
          {FORMATS.map(f => (
            <div key={f.id}
              className={`export-fmt${selected === f.id ? ' export-fmt--active' : ''}`}
              onClick={() => !exporting && setSelected(f.id)}>
              <span className="export-fmt__icon">{f.icon}</span>
              <div>
                <div className="export-fmt__label">{f.label}</div>
                <div className="export-fmt__desc">{f.desc}</div>
              </div>
              {selected === f.id && <span className="export-fmt__check">✓</span>}
            </div>
          ))}
        </div>
      </div>

      {/* ── Right: Settings + Progress ────────────────────────────────── */}
      <div className="export-ws__right">
        <h2>Export Settings</h2>
        <div className="export-props">

          {/* Resolution + FPS */}
          <div className="export-prop-row">
            <div className="export-prop">
              <label>Resolution</label>
              <div className="export-prop__value">{fmt.w} × {fmt.h}</div>
            </div>
            <div className="export-prop">
              <label>Frame Rate</label>
              <select value={fps} onChange={e => setFps(e.target.value)} disabled={exporting}>
                {FPS_OPTIONS.map(r => <option key={r} value={r}>{r} fps</option>)}
              </select>
            </div>
          </div>

          {/* Video quality */}
          <div className="export-section">
            <div className="export-section__title">Video Quality</div>
            <div className="export-toggle-row">
              <button
                className={`export-mode-btn${qualityMode === 'crf' ? ' active' : ''}`}
                onClick={() => setQualityMode('crf')} disabled={exporting}>
                CRF (Quality)
              </button>
              <button
                className={`export-mode-btn${qualityMode === 'bitrate' ? ' active' : ''}`}
                onClick={() => setQualityMode('bitrate')} disabled={exporting}>
                Bitrate
              </button>
            </div>

            {qualityMode === 'crf' ? (
              <div className="export-prop">
                <label>Quality — CRF {crf} {crf <= 18 ? '(Lossless)' : crf <= 23 ? '(High)' : crf <= 28 ? '(Medium)' : '(Low)'}</label>
                <input type="range" min={12} max={35} value={crf}
                  onChange={e => setCrf(parseInt(e.target.value))} disabled={exporting} />
                <div className="export-slider-labels"><span>Best</span><span>Fastest</span></div>
              </div>
            ) : (
              <div className="export-prop">
                <label>Video Bitrate — {videoBr} Mbps</label>
                <input type="range" min={2} max={40} value={parseFloat(videoBr)}
                  onChange={e => setVideoBr(e.target.value)} disabled={exporting} />
                <div className="export-slider-labels"><span>2 Mbps</span><span>40 Mbps</span></div>
              </div>
            )}

            <div className="export-prop">
              <label>Encoder Preset</label>
              <select value={preset} onChange={e => setPreset(e.target.value)} disabled={exporting}>
                {PRESET_OPTIONS.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
          </div>

          {/* Audio */}
          <div className="export-section">
            <div className="export-section__title">Audio</div>
            <div className="export-prop-row">
              <div className="export-prop">
                <label>Sample Rate</label>
                <select value={audioSR} onChange={e => setAudioSR(e.target.value)} disabled={exporting}>
                  {AUDIO_SR.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
                </select>
              </div>
              <div className="export-prop">
                <label>Channels</label>
                <select value={audioCh} onChange={e => setAudioCh(e.target.value)} disabled={exporting}>
                  {AUDIO_CH.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
                </select>
              </div>
              <div className="export-prop">
                <label>Bitrate</label>
                <select value={audioBr} onChange={e => setAudioBr(e.target.value)} disabled={exporting}>
                  {AUDIO_BR.map(b => <option key={b} value={b}>{b}</option>)}
                </select>
              </div>
            </div>
          </div>

          {/* Output path */}
          <div className="export-prop">
            <label>Output Path</label>
            <div className="export-path">
              <input
                value={outputPath}
                onChange={e => setOutputPath(e.target.value)}
                disabled={exporting}
                placeholder="Select output path…"
              />
              <button onClick={browseOutput} disabled={exporting}>Browse</button>
            </div>
          </div>

          {/* Estimated size */}
          <div className="export-estimate">
            <span>Estimated size:</span>
            <strong>{estSize}</strong>
            <span>· ~{Math.round(durSec)}s at {fps} fps</span>
          </div>
        </div>

        {/* ── Progress ─────────────────────────────────────────────── */}
        {webcompPhase && webcompPhase.total > 0 && (
          <div className="export-progress export-progress--phase">
            <div className="export-progress__label">
              <span className="export-phase-badge">Preparing overlays…</span>
              <span>{wcPct}% ({webcompPhase.done}/{webcompPhase.total} frames)</span>
            </div>
            <div className="export-progress__bar">
              <div className="export-progress__fill export-progress__fill--webcomp"
                style={{ width: `${wcPct}%` }} />
            </div>
          </div>
        )}

        {progress && (
          <div className="export-progress">
            {!webcompPhase?.active && (
              <div className="export-progress__label">
                {progress.done && !progress.error
                  ? <span className="export-done">✓ Export complete</span>
                  : progress.error
                    ? <span className="export-error">✗ {progress.error}</span>
                    : progress.status === 'audio'
                      ? <span className="export-phase-badge export-phase-badge--audio">🎵 Muxing audio…</span>
                      : <span>Encoding… {pct}% — frame {progress.frame} / {progress.total}</span>
                }
              </div>
            )}
            <div className="export-progress__bar">
              <div className="export-progress__fill" style={{ width: `${pct}%` }} />
            </div>
            {progress.done && !progress.error && progress.path && (
              <div className="export-done-path">📁 {progress.path}</div>
            )}
          </div>
        )}

        <div className="export-actions">
          {exporting
            ? <button className="export-btn export-btn--cancel" onClick={cancelExport}>✕ Cancel</button>
            : <button className="export-btn export-btn--primary" onClick={startExport}>⬇ Export Video</button>
          }
        </div>
      </div>
    </div>
  )
}

