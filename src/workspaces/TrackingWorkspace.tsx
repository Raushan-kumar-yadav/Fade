import React, { useState, useEffect, useRef, useCallback } from 'react'
import './TrackingWorkspace.css'

/* ── types ─────────────────────────────────────────────────────────────── */
type DetectionMode = 'face' | 'person' | 'text' | 'image' | 'manual'

interface ClipMeta {
  clipId: string
  name: string
  videoPath: string
  startFrame: number
  duration: number
  type: string
}

interface AssetMeta {
  assetId: string
  filename: string
  filepath: string
  type: string
}

interface TrackSummary {
  track_id: string
  label: string
  from_frame: number
  to_frame: number
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
  label: string
  frame_count?: number
}

interface Props {
  selectedClipId?: string | null
  totalFrames?: number
  fps?: number
}

/* ── API ────────────────────────────────────────────────────────────────── */
function base() {
  return `http://localhost:${(window as any).__FADE_PORT__ ?? 8000}`
}
const api = {
  timelineState: () => fetch(`${base()}/timeline/state`).then(r => r.json()),
  assets: () => fetch(`${base()}/library/assets`).then(r => r.json()),
  startTrack: (body: Record<string, unknown>) =>
    fetch(`${base()}/tracking/start`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.json()),
  progress: (jobId: string) => fetch(`${base()}/tracking/progress/${jobId}`).then(r => r.json()),
  listTracks: (clipId: string) => fetch(`${base()}/tracking/tracks/${clipId}`).then(r => r.json()),
  deleteTrack: (trackId: string) => fetch(`${base()}/tracking/track/${trackId}`, { method: 'DELETE' }).then(r => r.json()),
  cancelJob: (jobId: string) => fetch(`${base()}/tracking/cancel/${jobId}`, { method: 'POST' }).then(r => r.json()),
}

/* ── helpers ────────────────────────────────────────────────────────────── */
function extractVideoClips(data: any): ClipMeta[] {
  const clips: ClipMeta[] = []
  ;(data?.tracks ?? []).forEach((tr: any) => {
    ;(tr?.clips ?? []).forEach((c: any) => {
      const p = c.mediaPath ?? c.assetPath ?? c.filePath ?? ''
      if (p && (c.type === 'video' || c.clipType === 'video' || !c.type)) {
        clips.push({
          clipId: c.clipId,
          name: c.name ?? c.clipId?.slice(0, 8) ?? 'Clip',
          videoPath: p,
          startFrame: c.startFrame ?? 0,
          duration: c.duration ?? 300,
          type: c.type ?? 'video',
        })
      }
    })
  })
  return clips
}

/* ── component ──────────────────────────────────────────────────────────── */
export default function TrackingWorkspace({ selectedClipId, totalFrames = 300 }: Props) {

  /* ── clip state ─── */
  const [videoClips, setVideoClips]   = useState<ClipMeta[]>([])
  const [selClipId, setSelClipId]     = useState<string>(selectedClipId ?? '')
  const [selClip, setSelClip]         = useState<ClipMeta | null>(null)

  /* ── image assets (for Image / Person reference) ─── */
  const [imageAssets, setImageAssets] = useState<AssetMeta[]>([])
  const [refAssetId, setRefAssetId]   = useState<string>('')   // picked image/person asset

  /* ── form ─── */
  const [mode, setMode]               = useState<DetectionMode>('face')
  const [fromFrame, setFromFrame]     = useState(0)
  const [toFrame, setToFrame]         = useState(totalFrames)
  const [label, setLabel]             = useState('')
  const [textPattern, setTextPattern] = useState('email|phone')
  const [manualBbox, setManualBbox]   = useState('')

  /* ── jobs & tracks ─── */
  const [activeJob, setActiveJob]     = useState<JobState | null>(null)
  const [tracks, setTracks]           = useState<TrackSummary[]>([])
  const [error, setError]             = useState<string | null>(null)
  const pollRef                       = useRef<ReturnType<typeof setInterval> | null>(null)

  /* ── load video clips from timeline ─── */
  const loadClips = useCallback(() => {
    api.timelineState()
      .then(d => setVideoClips(extractVideoClips(d)))
      .catch(() => {})
  }, [])

  /* ── load image assets from library ─── */
  const loadImageAssets = useCallback(() => {
    api.assets()
      .then((arr: AssetMeta[]) =>
        setImageAssets(arr.filter(a => a.type === 'image' || a.type === 'svg'))
      )
      .catch(() => {})
  }, [])

  useEffect(() => { loadClips(); loadImageAssets() }, [loadClips, loadImageAssets])

  /* ── when selectedClipId prop changes (clip selected in timeline) ─── */
  useEffect(() => {
    if (selectedClipId) setSelClipId(selectedClipId)
  }, [selectedClipId])

  /* ── resolve selClip from id ─── */
  useEffect(() => {
    const c = videoClips.find(v => v.clipId === selClipId) ?? null
    setSelClip(c)
    if (c) {
      setFromFrame(c.startFrame)
      setToFrame(c.startFrame + c.duration)
    }
  }, [selClipId, videoClips])

  /* ── load existing tracks when clip changes ─── */
  const refreshTracks = useCallback(() => {
    if (!selClipId) return
    api.listTracks(selClipId).then(d => setTracks(d.tracks ?? [])).catch(() => {})
  }, [selClipId])

  useEffect(() => { refreshTracks() }, [refreshTracks])

  /* ── poll active job ─── */
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

  /* ── start tracking ─── */
  const handleStart = async () => {
    setError(null)
    if (!selClipId || !selClip) { setError('Select a clip from the timeline first.'); return }
    if (!selClip.videoPath)     { setError('Selected clip has no video path.'); return }

    const refAsset = imageAssets.find(a => a.assetId === refAssetId)

    if ((mode === 'image' || mode === 'person') && !refAsset) {
      setError(`Pick a reference image for ${mode} mode.`); return
    }
    if (mode === 'manual' && !manualBbox) {
      setError('Enter a bounding box (x,y,w,h) for Manual mode.'); return
    }

    let bbox: number[] | null = null
    if (mode === 'manual') {
      const parts = manualBbox.split(',').map(Number)
      if (parts.length !== 4 || parts.some(isNaN)) { setError('Bbox format: x,y,w,h (pixels)'); return }
      bbox = parts
    }

    try {
      const res = await api.startTrack({
        clip_id: selClipId,
        video_path: selClip.videoPath,
        from_frame: fromFrame,
        to_frame: toFrame,
        detection_mode: mode,
        label: label || mode,
        text_pattern: textPattern,
        template_path: refAsset?.filepath ?? null,
        initial_bbox: bbox,
      })
      if (res.job_id) {
        setActiveJob({
          job_id: res.job_id, percent: 0, status: 'running', done: false,
          error: null, track_id: null, current_frame: fromFrame, label: label || mode,
        })
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

  const handleAddBlur = (track: TrackSummary) => {
    window.dispatchEvent(new CustomEvent('fade:add-blur-track', {
      detail: { track_id: track.track_id, clip_id: selClipId }
    }))
  }

  const isRunning = !!(activeJob && !activeJob.done)

  /* ── ref image/person picker ─── */
  const RefAssetPicker = ({ label: lbl }: { label: string }) => (
    <div className="tr-field-group">
      <label className="tr-label">{lbl}</label>
      {imageAssets.length === 0 ? (
        <p className="tr-hint tr-hint--warn">No images imported yet — import an image asset first.</p>
      ) : (
        <select
          className="tr-select"
          value={refAssetId}
          onChange={e => setRefAssetId(e.target.value)}
        >
          <option value="">— pick an image —</option>
          {imageAssets.map(a => (
            <option key={a.assetId} value={a.assetId}>
              {a.filename}
            </option>
          ))}
        </select>
      )}
      {refAssetId && imageAssets.find(a => a.assetId === refAssetId) && (
        <span className="tr-hint">{imageAssets.find(a => a.assetId === refAssetId)?.filepath}</span>
      )}
    </div>
  )

  /* ── mode-specific UI ─── */
  const ModeParams = () => {
    if (mode === 'text') return (
      <div className="tr-field-group">
        <label className="tr-label">Text pattern</label>
        <input
          className="tr-input"
          value={textPattern}
          onChange={e => setTextPattern(e.target.value)}
          placeholder="email | phone | @gmail\.com | +91\d{10}"
        />
        <span className="tr-hint">Shortcuts: <code>email</code>, <code>phone</code> — or any regex</span>
      </div>
    )
    if (mode === 'image') return (
      <RefAssetPicker label="Reference image (template to match)" />
    )
    if (mode === 'person') return (
      <RefAssetPicker label="Reference person image (face/body crop)" />
    )
    if (mode === 'manual') return (
      <div className="tr-field-group">
        <label className="tr-label">Bounding box — x, y, w, h (pixels)</label>
        <input
          className="tr-input"
          value={manualBbox}
          onChange={e => setManualBbox(e.target.value)}
          placeholder="320, 180, 200, 150"
        />
        <span className="tr-hint">Pixel coordinates of the target in the start frame</span>
      </div>
    )
    /* face */
    return (
      <div className="tr-hint tr-hint--info">
        MediaPipe face detection — automatically finds all faces in frame {fromFrame}
      </div>
    )
  }

  /* ── render ─────────────────────────────────────────────────────────── */
  return (
    <div className="tr-workspace">

      {/* header */}
      <div className="tr-header">
        <svg className="tr-icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="3"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3"/>
          <path d="M4.93 4.93l2.12 2.12m9.9 9.9 2.12 2.12M4.93 19.07l2.12-2.12m9.9-9.9 2.12-2.12"/>
        </svg>
        <div>
          <h2 className="tr-title">Object Tracking</h2>
          <p className="tr-subtitle">Track faces, people, text or images — then blur or follow them</p>
        </div>
      </div>

      {/* ── clip selector ── */}
      <div className="tr-field-group">
        <label className="tr-label">Clip to track</label>
        {videoClips.length > 0 ? (
          <select
            className="tr-select"
            value={selClipId}
            onChange={e => setSelClipId(e.target.value)}
          >
            <option value="">— select a video clip —</option>
            {videoClips.map(c => (
              <option key={c.clipId} value={c.clipId}>
                {c.name}  ({c.duration} fr)
              </option>
            ))}
          </select>
        ) : (
          <p className="tr-hint tr-hint--warn">
            No video clips on the timeline. Add a video clip first, then select it.
          </p>
        )}

        {/* selected clip info badge */}
        {selClip && (
          <div className="tr-clip-badge">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" width="14" height="14">
              <rect x="2" y="6" width="20" height="12" rx="2"/><path d="m10 9 5 3-5 3V9z"/>
            </svg>
            <span>{selClip.name}</span>
            <span className="tr-clip-badge__meta">{selClip.duration} frames</span>
          </div>
        )}
      </div>

      {/* ── frame range ── */}
      <div className="tr-row">
        <div className="tr-field-group tr-field-group--half">
          <label className="tr-label">Start frame</label>
          <input
            type="number" className="tr-input" min={0}
            value={fromFrame}
            onChange={e => setFromFrame(Number(e.target.value))}
          />
        </div>
        <div className="tr-field-group tr-field-group--half">
          <label className="tr-label">End frame</label>
          <input
            type="number" className="tr-input" min={0}
            value={toFrame}
            onChange={e => setToFrame(Number(e.target.value))}
          />
        </div>
      </div>

      {/* ── label ── */}
      <div className="tr-field-group">
        <label className="tr-label">Track label <span className="tr-optional">(optional)</span></label>
        <input
          className="tr-input"
          placeholder="e.g. speaker_face"
          value={label}
          onChange={e => setLabel(e.target.value)}
        />
      </div>

      {/* ── detection mode tabs ── */}
      <div className="tr-field-group">
        <label className="tr-label">Detection mode</label>
        <div className="tr-mode-tabs">
          {(['face', 'person', 'text', 'image', 'manual'] as DetectionMode[]).map(m => (
            <button
              key={m}
              className={`tr-mode-tab${mode === m ? ' tr-mode-tab--active' : ''}`}
              onClick={() => setMode(m)}
            >
              {({ face: 'Face', person: 'Person', text: 'Text', image: 'Image', manual: 'Manual' } as Record<DetectionMode,string>)[m]}
            </button>
          ))}
        </div>
      </div>

      {/* ── mode-specific params ── */}
      <ModeParams />

      {/* ── error ── */}
      {error && <div className="tr-error">{error}</div>}

      {/* ── start / cancel button ── */}
      {isRunning ? (
        <button className="tr-btn-cancel-big" onClick={handleCancel}>
          Cancel Tracking
        </button>
      ) : (
        <button
          className="tr-btn-start"
          onClick={handleStart}
          disabled={!selClip}
        >
          Start Tracking
        </button>
      )}

      {/* ── active job progress ── */}
      {activeJob && (
        <div className={`tr-job-card tr-job-card--${activeJob.done ? (activeJob.error ? 'error' : 'done') : 'running'}`}>
          <div className="tr-job-header">
            <span className="tr-job-label">{activeJob.label}</span>
            <span className="tr-job-pct">{activeJob.done ? (activeJob.error ? 'Failed' : 'Done') : `${activeJob.percent}%`}</span>
          </div>
          {activeJob.error ? (
            <p className="tr-job-error">{activeJob.error}</p>
          ) : (
            <>
              <div className="tr-progress-bar">
                <div className="tr-progress-fill" style={{ width: `${activeJob.percent}%` }} />
              </div>
              <span className="tr-progress-label">
                {activeJob.done
                  ? `Tracked ${activeJob.frame_count ?? ''} frames`
                  : `Frame ${activeJob.current_frame}`}
              </span>
              {activeJob.done && activeJob.track_id && (
                <code className="tr-track-id-small">ID: {activeJob.track_id}</code>
              )}
            </>
          )}
        </div>
      )}

      {/* ── completed tracks ── */}
      {tracks.length > 0 && (
        <div className="tr-tracks-section">
          <h3 className="tr-section-title">Completed Tracks</h3>
          {tracks.map(t => (
            <div key={t.track_id} className="tr-track-card">
              <div className="tr-track-info">
                <span className="tr-track-label">{t.label}</span>
                <span className="tr-track-meta">frames {t.from_frame}–{t.to_frame} · {t.frame_count} pts</span>
                <code className="tr-track-id-small">{t.track_id.slice(0, 12)}…</code>
              </div>
              <div className="tr-track-actions">
                <button
                  className="tr-btn-action tr-btn-action--blur"
                  onClick={() => handleAddBlur(t)}
                  title="Create a blur rect that follows this track"
                >
                  Add Blur
                </button>
                <button
                  className="tr-btn-action tr-btn-action--delete"
                  onClick={() => handleDelete(t.track_id)}
                  title="Delete track"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── expression hint ── */}
      {tracks.length > 0 && (
        <details className="tr-expr-hint">
          <summary>Use in expressions</summary>
          <pre className="tr-expr-code">{`pos_x = track("${tracks[0]?.track_id ?? 'TRACK_ID'}", frame, "cx") - comp_w / 2
pos_y = track("${tracks[0]?.track_id ?? 'TRACK_ID'}", frame, "cy") - comp_h / 2
shape_w = track("${tracks[0]?.track_id ?? 'TRACK_ID'}", frame, "w") * 1.1`}</pre>
        </details>
      )}
    </div>
  )
}
