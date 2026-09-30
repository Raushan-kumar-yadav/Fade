import React, { useState, useEffect, useRef, useCallback } from 'react'
import './TrackingWorkspace.css'

/*   types   */
type DetectionMode = 'face' | 'person' | 'text' | 'image' | 'manual'

interface TrackSummary {
  track_id: string
  label: string
  from_frame: number
  to_frame:   number
  frame_count: number
}

interface JobState {
  job_id: string
  percent: number
  status: string
  done: boolean
  error: string | null
  track_id: string | null
  current_frame: number
  label:        string
}

interface Props {
  /** Clip currently selected in the timeline */
  selectedClipId?: string | null
  videoPath?: string | null
  totalFrames?: number
  fps?: number
}

/*   API helpers   */
const BASE = 'http://localhost:7860'
const api = {
  startTrack: (body: Record<string, unknown>) =>
    fetch(`${BASE}/tracking/start`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.json()),
  progress: (jobId: string) =>
    fetch(`${BASE}/tracking/progress/${jobId}`).then(r => r.json()),
  listTracks: (clipId: string) =>
    fetch(`${BASE}/tracking/tracks/${clipId}`).then(r => r.json()),
  deleteTrack: (trackId: string) =>
    fetch(`${BASE}/tracking/track/${trackId}`, { method: 'DELETE' }).then(r => r.json()),
  cancelJob: (jobId: string) =>
    fetch(`${BASE}/tracking/cancel/${jobId}`, { method: 'POST' }).then(r => r.json()),
  listClips: () =>
    fetch(`${BASE}/timeline/state`).then(r => r.json()),
}

/*   Component   */
export default function TrackingWorkspace({ selectedClipId, videoPath, totalFrames = 300, fps = 30 }: Props) {
  /* form state */
  const [mode, setMode] = useState<DetectionMode>('face')
  const [fromFrame, setFromFrame] = useState(0)
  const [toFrame, setToFrame] = useState(totalFrames)
  const [label, setLabel] = useState('')
  const [textPattern, setTextPattern] = useState('email|phone')
  const [templatePath, setTemplatePath] = useState('')
  const [manualBbox, setManualBbox] = useState('')
  const [clipId, setClipId] = useState(selectedClipId ?? '')
  const [clipPath, setClipPath] = useState(videoPath ?? '')

  /* clip picker */
  const [timelineClips, setTimelineClips] = useState<{ id: string; name: string; path: string }[]>([])

  /* jobs & tracks */
  const [activeJob, setActiveJob] = useState<JobState | null>(null)
  const [tracks, setTracks] = useState<TrackSummary[]>([])
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  /* sync props */
  useEffect(() => {
    if (selectedClipId) setClipId(selectedClipId)
    if (videoPath) setClipPath(videoPath)
    if (totalFrames) setToFrame(totalFrames)
  }, [selectedClipId, videoPath, totalFrames])

  /* load timeline clips for picker */
  useEffect(() => {
    api.listClips().then(data => {
      const clips: { id: string; name: string; path: string }[] = []
      ;(data.tracks ?? []).forEach((tr: { clips: { clipId: string; name?: string; mediaPath?: string; assetPath?: string }[] }) => {
        ;(tr.clips ?? []).forEach(c => {
          if (c.mediaPath || c.assetPath) {
            clips.push({ id: c.clipId, name: c.name ?? c.clipId.slice(0, 8), path: c.mediaPath ?? c.assetPath ?? '' })
          }
        })
      })
      setTimelineClips(clips)
    }).catch(() => {})
  }, [])

  /* load existing tracks when clip changes */
  const refreshTracks = useCallback(() => {
    if (!clipId) return
    api.listTracks(clipId).then(d => setTracks(d.tracks ?? [])).catch(() => {})
  }, [clipId])

  useEffect(() => { refreshTracks() }, [refreshTracks])

  /* poll active job */
  useEffect(() => {
    if (!activeJob?.job_id || activeJob.done) return
    pollRef.current = setInterval(async () => {
      try {
        const j = await api.progress(activeJob.job_id)
        setActiveJob(prev => prev ? { ...prev, ...j } : j)
        if (j.done || j.error) {
          clearInterval(pollRef.current!)
          if (j.done && !j.error) refreshTracks()
        }
      } catch { clearInterval(pollRef.current!) }
    }, 600)
    return () => clearInterval(pollRef.current!)
  }, [activeJob?.job_id, activeJob?.done, refreshTracks])

  /* start tracking */
  const handleStart = async () => {
    setError(null)
    if (!clipId)   { setError('Select a clip first.'); return }
    if (!clipPath) { setError('Clip video path is required.'); return }
    if (mode === 'image' && !templatePath) { setError('Enter a template image path for Image mode.'); return }
    if (mode === 'manual' && !manualBbox)  { setError('Enter a bounding box (x,y,w,h) for Manual mode.'); return }

    let bbox: number[] | null = null
    if (mode === 'manual') {
      const parts = manualBbox.split(',').map(Number)
      if (parts.length !== 4 || parts.some(isNaN)) { setError('Bbox format: x,y,w,h (pixels)'); return }
      bbox = parts
    }

    try {
      const res = await api.startTrack({
        clip_id: clipId,
        video_path: clipPath,
        from_frame: fromFrame,
        to_frame: toFrame,
        detection_mode: mode,
        label: label || mode,
        text_pattern:   textPattern,
        template_path: templatePath || null,
        initial_bbox:  bbox,
      })
      if (res.job_id) {
        setActiveJob({ job_id: res.job_id, percent: 0, status: 'running', done: false, error: null, track_id: null, current_frame: fromFrame, label: label || mode })
      } else {
        setError(res.detail ?? 'Failed to start tracking.')
      }
    } catch (e: unknown) {
      setError(String(e))
    }
  }

  const handleCancel = async () => {
    if (!activeJob) return
    await api.cancelJob(activeJob.job_id).catch(() => {})
    setActiveJob(prev => prev ? { ...prev, done: true, status: 'cancelled' } : null)
    clearInterval(pollRef.current!)
  }

  const handleDelete = async (trackId: string) => {
    await api.deleteTrack(trackId)
    refreshTracks()
  }

  const handleLinkBlur = async (track: TrackSummary) => {
    window.dispatchEvent(new CustomEvent('fade:add-blur-track', { detail: { track_id: track.track_id, clip_id: clipId } }))
  }

  /* Clip picker section   */
  function ClipPicker() {
    return (
      <div className="tr-field-group">
        <label className="tr-label">Clip</label>
        {timelineClips.length > 0 ? (
          <select
            className="tr-select"
            value={clipId}
            onChange={e => {
              const c = timelineClips.find(x => x.id === e.target.value)
              setClipId(e.target.value)
              if (c) setClipPath(c.path)
            }}
          >
            <option value="">— pick a clip —</option>
            {timelineClips.map(c => (
              <option key={c.id} value={c.id}>{c.name} ({c.id.slice(0,6)})</option>
            ))}
          </select>
        ) : (
          <input className="tr-input" placeholder="clip-id" value={clipId} onChange={e => setClipId(e.target.value)} />
        )}
        <input className="tr-input" placeholder="/path/to/video.mp4" value={clipPath} onChange={e => setClipPath(e.target.value)} />
      </div>
    )
  }

  /* Mode-specific inputs   */
  function ModeParams() {
    if (mode === 'text') return (
      <div className="tr-field-group">
        <label className="tr-label">Text pattern (regex or shorthand)</label>
        <input className="tr-input" value={textPattern} onChange={e => setTextPattern(e.target.value)}
          placeholder="email|phone  or  +91\d{10}  or  @gmail\.com" />
        <span className="tr-hint">Shortcuts: <code>email</code>, <code>phone</code>, or any regex</span>
      </div>
    )
    if (mode === 'image') return (
      <div className="tr-field-group">
        <label className="tr-label">Reference image path (template)</label>
        <input className="tr-input" value={templatePath} onChange={e => setTemplatePath(e.target.value)}
          placeholder="/absolute/path/to/logo.png" />
        <span className="tr-hint">OpenCV template matching — use a cropped version of the target</span>
      </div>
    )
    if (mode === 'manual') return (
      <div className="tr-field-group">
        <label className="tr-label">Initial bounding box (x,y,w,h in pixels)</label>
        <input className="tr-input" value={manualBbox} onChange={e => setManualBbox(e.target.value)}
          placeholder="320,180,200,150" />
        <span className="tr-hint">Pixel coordinates of the target in the start frame</span>
      </div>
    )
    return (
      <div className="tr-hint tr-hint--info">
        {mode === 'face' && '📸 MediaPipe face detection — automatically finds faces in frame ' + fromFrame}
        {mode === 'person' && '🧍 YOLOv8n person detection — finds people in frame ' + fromFrame}
      </div>
    )
  }

  return (
    <div className="tr-workspace">
      <div className="tr-header">
        <span className="tr-icon">🎯</span>
        <div>
          <h2 className="tr-title">Object Tracking</h2>
          <p className="tr-subtitle">Track faces, people, text, or images — then blur or follow them</p>
        </div>
      </div>

      {/*   Clip picker   */}
      <ClipPicker />

      {/*   Frame range   */}
      <div className="tr-row">
        <div className="tr-field-group tr-field-group--half">
          <label className="tr-label">Start frame</label>
          <input type="number" className="tr-input" min={0} value={fromFrame} onChange={e => setFromFrame(Number(e.target.value))} />
        </div>
        <div className="tr-field-group tr-field-group--half">
          <label className="tr-label">End frame</label>
          <input type="number" className="tr-input" min={0} value={toFrame} onChange={e => setToFrame(Number(e.target.value))} />
        </div>
      </div>

      {/*   Label   */}
      <div className="tr-field-group">
        <label className="tr-label">Track label (optional)</label>
        <input className="tr-input" placeholder="e.g. speaker_face" value={label} onChange={e => setLabel(e.target.value)} />
      </div>

      {/*   Tracking type tabs   */}
      <div className="tr-field-group">
        <label className="tr-label">Detection mode</label>
        <div className="tr-mode-tabs">
          {(['face','person','text','image','manual'] as DetectionMode[]).map(m => (
            <button
              key={m}
              className={`tr-mode-tab${mode === m ? ' tr-mode-tab--active' : ''}`}
              onClick={() => setMode(m)}
            >
              {{ face:'😀 Face', person:'🧍 Person', text:'📝 Text', image:'🖼 Image', manual:'✏️ Manual' }[m]}
            </button>
          ))}
        </div>
      </div>

      {/*   Mode-specific params   */}
      <ModeParams />

      {/*   Error   */}
      {error && <div className="tr-error">⚠️ {error}</div>}

      {/*   Start button  */}
      <button
        className={`tr-btn-start${activeJob && !activeJob.done ? ' tr-btn-start--disabled' : ''}`}
        onClick={handleStart}
        disabled={!!(activeJob && !activeJob.done)}
      >
        {activeJob && !activeJob.done ? '⏳ Tracking…' : '▶ Start Tracking'}
      </button>

      {/*   Active job progress   */}
      {activeJob && (
        <div className={`tr-job-card tr-job-card--${activeJob.done ? (activeJob.error ? 'error' : 'done') : 'running'}`}>
          <div className="tr-job-header">
            <span className="tr-job-label">
              {activeJob.done ? (activeJob.error ? '❌' : '✅') : '🔄'} {activeJob.label}
            </span>
            {!activeJob.done && (
              <button className="tr-btn-cancel" onClick={handleCancel}>Cancel</button>
            )}
          </div>
          {activeJob.error ? (
            <p className="tr-job-error">{activeJob.error}</p>
          ) : (
            <>
              <div className="tr-progress-bar">
                <div className="tr-progress-fill" style={{ width: `${activeJob.percent}%` }} />
              </div>
              <span className="tr-progress-label">
                {activeJob.done ? `Done — ${activeJob.frame_count ?? ''} frames tracked` : `${activeJob.percent}% — frame ${activeJob.current_frame}`}
              </span>
              {activeJob.done && activeJob.track_id && (
                <p className="tr-track-id">Track ID: <code>{activeJob.track_id}</code></p>
              )}
            </>
          )}
        </div>
      )}

      {/* ── Existing tracks ── */}
      {tracks.length > 0 && (
        <div className="tr-tracks-section">
          <h3 className="tr-section-title">Completed Tracks</h3>
          {tracks.map(t => (
            <div key={t.track_id} className="tr-track-card">
              <div className="tr-track-info">
                <span className="tr-track-label">🎯 {t.label}</span>
                <span className="tr-track-meta">frames {t.from_frame}–{t.to_frame} · {t.frame_count} pts</span>
                <code className="tr-track-id-small">{t.track_id}</code>
              </div>
              <div className="tr-track-actions">
                <button className="tr-btn-action tr-btn-action--blur" onClick={() => handleLinkBlur(t)} title="Add blur rect that follows this track">
                  🔲 Add Blur
                </button>
                <button className="tr-btn-action tr-btn-action--delete" onClick={() => handleDelete(t.track_id)} title="Delete track">
                  🗑
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/*   Expression hint   */}
      {tracks.length > 0 && (
        <details className="tr-expr-hint">
          <summary>📐 Use in expressions</summary>
          <pre className="tr-expr-code">{`// In any clip's property expression:
pos_x = track("${tracks[0]?.track_id ?? 'TRACK_ID'}", frame, "cx") - comp_w / 2
pos_y = track("${tracks[0]?.track_id ?? 'TRACK_ID'}", frame, "cy") - comp_h / 2
shape_w = track("${tracks[0]?.track_id ?? 'TRACK_ID'}", frame, "w") * 1.1
shape_h = track("${tracks[0]?.track_id ?? 'TRACK_ID'}", frame, "h") * 1.1`}</pre>
        </details>
      )}
    </div>
  )
}
