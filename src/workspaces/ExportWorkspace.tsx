import { useState, useRef, useEffect } from 'react'
import './ExportWorkspace.css'
import { exportApi, type ExportProgress } from '../api/toolsApi'

interface Format { id: string; label: string; icon: string; desc: string; w: number; h: number }

const FORMATS: Format[] = [
  { id: 'mp4-1080',  label: 'MP4 1080p',   icon: '▶', desc: 'H.264, AAC audio',     w: 1920, h: 1080 },
  { id: 'mp4-4k',    label: 'MP4 4K',      icon: '▶', desc: 'H.264, High Bitrate',  w: 3840, h: 2160 },
  { id: 'shorts',    label: 'YT Shorts',   icon: '▷', desc: '1080×1920, 60s max',   w: 1080, h: 1920 },
  { id: 'reels',     label: 'IG Reels',    icon: '◈', desc: '1080×1920, AAC',        w: 1080, h: 1920 },
  { id: 'gif',       label: 'GIF',         icon: '◉', desc: 'Animated, 480p',        w:  854, h:  480 },
  { id: 'webm',      label: 'WebM',        icon: '▸', desc: 'VP9, open format',      w: 1920, h: 1080 },
]

const FPS_OPTIONS = ['24', '30', '60']

export default function ExportWorkspace() {
  const [selected,    setSelected]    = useState<string>('mp4-1080')
  const [fps,         setFps]         = useState<string>('30')
  const [outputPath,  setOutputPath]  = useState<string>('C:\\Users\\Videos\\fade_export.mp4')
  const [jobId,       setJobId]       = useState<string | null>(null)
  const [progress,    setProgress]    = useState<ExportProgress | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fmt = FORMATS.find(f => f.id === selected)!

  const stopPoll = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  }

  useEffect(() => stopPoll, [])

  async function startExport() {
    try {
      const res = await exportApi.start({
        outputPath,
        width:  fmt.w,
        height: fmt.h,
        fps:    parseFloat(fps),
        formatId: selected,
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
    if (!jobId) return
    await exportApi.cancel(jobId)
    stopPoll()
    setProgress(null)
    setJobId(null)
  }

  function browseOutput() {
    const ipc = (window as any).electronAPI
    if (ipc?.showSaveDialog) {
      ipc.showSaveDialog({ filters: [{ name: 'Video', extensions: ['mp4', 'webm'] }] })
        .then((p: string | undefined) => { if (p) setOutputPath(p) })
    }
  }

  const exporting = !!jobId && !progress?.done
  const pct       = progress?.percent ?? 0

  return (
    <div className="export-ws">
      <div className="export-ws__left">
        <h2>Export Format</h2>
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

      <div className="export-ws__right">
        <h2>Export Settings</h2>
        <div className="export-props">

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

          <div className="export-prop">
            <label>Encoder</label>
            <div className="export-prop__value">Auto (NVENC → QSV → x264)</div>
          </div>

          <div className="export-prop">
            <label>Output Path</label>
            <div className="export-path">
              <input readOnly value={outputPath} />
              <button onClick={browseOutput} disabled={exporting}>Browse</button>
            </div>
          </div>
        </div>

        {progress && (
          <div className="export-progress">
            <div className="export-progress__bar">
              <div className="export-progress__fill" style={{ width: `${pct}%` }} />
            </div>
            {progress.done && !progress.error && (
              <span className="export-done">✓ Done — {progress.path}</span>
            )}
            {progress.error && (
              <span className="export-error">✗ {progress.error}</span>
            )}
            {!progress.done && (
              <span>{pct}% — frame {progress.frame} / {progress.total}</span>
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
