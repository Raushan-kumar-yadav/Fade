import { useState } from 'react'
import './ExportWorkspace.css'

interface Format { id: string; label: string; icon: string; desc: string }
interface ExportProp { label: string; options?: string[] }

const FORMATS: Format[] = [
  { id: 'mp4-1080', label: 'MP4 1080p',  icon: '▶', desc: 'H.264, AAC audio' },
  { id: 'mp4-4k', label: 'MP4 4K', icon: '▶', desc: 'H.264, High Bitrate' },
  { id: 'shorts', label: 'YT Shorts',  icon: '▷', desc: '1080×1920, 60s max' },
  { id: 'reels', label: 'IG Reels',   icon: '◈', desc: '1080×1920, AAC' },
  { id: 'gif', label: 'GIF', icon: '◉', desc: 'Animated, 480p' },
  { id: 'webm', label: 'WebM', icon: '▸', desc: 'VP9, open format' },
]

const AI_TOGGLES: string[] = ['Auto Captions','Color Grade','Noise Reduce','Sharpness']
const FPS_OPTIONS: string[] = ['24 fps','30 fps','60 fps']
const RES_OPTIONS: string[] = ['1920×1080','3840×2160','1080×1920','1280×720']

export default function ExportWorkspace() {
  const [selected, setSelected] = useState<string>('mp4-1080')
  const [quality, setQuality] = useState<number>(85)
  const [fps, setFps] = useState<string>('30 fps')
  const [exporting, setExporting] = useState<boolean>(false)
  const [progress,  setProgress]  = useState<number>(0)

  const fmt = FORMATS.find(f => f.id === selected)

  function startExport(): void {
    setExporting(true)
    setProgress(0)
    const interval = setInterval(() => {
      setProgress(p => {
        if (p >= 100) { clearInterval(interval); setExporting(false); return 100 }
        return p + 2
      })
    }, 80)
  }

  return (
    <div className="export-ws">
      {/* Left */}
      <div className="export-ws__left">
        <h2>Export Format</h2>
        <div className="export-formats">
          {FORMATS.map(f => (
            <div key={f.id}
              className={`export-fmt${selected === f.id ? ' export-fmt--active' : ''}`}
              onClick={() => setSelected(f.id)}>
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

      {/* Right */}
      <div className="export-ws__right">
        <h2>Export Settings</h2>
        <div className="export-props">

          <div className="export-prop">
            <label>Format</label>
            <div className="export-prop__value">{fmt?.label}</div>
          </div>

          <div className="export-prop">
            <label>Quality — {quality}%</label>
            <input type="range" min={10} max={100} value={quality}
              onChange={e => setQuality(Number(e.target.value))} />
          </div>

          <div className="export-prop">
            <label>Frame Rate</label>
            <select value={fps} onChange={e => setFps(e.target.value)}>
              {FPS_OPTIONS.map(r => <option key={r}>{r}</option>)}
            </select>
          </div>

          <div className="export-prop">
            <label>Resolution</label>
            <select>{RES_OPTIONS.map(r => <option key={r}>{r}</option>)}</select>
          </div>

          <div className="export-prop">
            <label>AI Effects</label>
            <div className="export-toggles">
              {AI_TOGGLES.map(t => (
                <label key={t} className="export-toggle">
                  <input type="checkbox" defaultChecked={t === 'Auto Captions'} />
                  {t}
                </label>
              ))}
            </div>
          </div>

          <div className="export-prop">
            <label>Output Path</label>
            <div className="export-path">
              <input readOnly value="C:\Users\Videos\fade_export.mp4" />
              <button>Browse</button>
            </div>
          </div>
        </div>

        {exporting && (
          <div className="export-progress">
            <div className="export-progress__bar">
              <div className="export-progress__fill" style={{ width: `${progress}%` }} />
            </div>
            <span>{progress}% — Rendering frames...</span>
          </div>
        )}

        <div className="export-actions">
          <button className="export-btn export-btn--secondary">Preview</button>
          <button className="export-btn export-btn--primary"
            onClick={startExport} disabled={exporting}>
            {exporting ? `Exporting ${progress}%…` : '⬇ Export Video'}
          </button>
        </div>
      </div>
    </div>
  )
}
