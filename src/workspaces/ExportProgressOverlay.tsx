import { useState, useEffect, useRef, useCallback } from 'react'
import './ExportProgressOverlay.css'

interface ExportProgress {
  jobId: string
  frame: number
  total: number
  percent: number
  done: boolean
  error: string | null
  path: string | null
  status?: string
}

const PORT = () => (window as any).__FADE_PORT__ ?? 8000

export default function ExportProgressOverlay() {
  const [jobId, setJobId] = useState<string | null>(null)
  const [progress, setProgress] = useState<ExportProgress | null>(null)
  const [visible, setVisible] = useState(false)
  const [dismissing, setDismissing] = useState(false)

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const elecClean  = useRef<(() => void) | null>(null)
  const dismissRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const stopPoll = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
    elecClean.current?.(); elecClean.current = null
  }, [])

  const dismiss = useCallback(() => {
    setDismissing(true)
    dismissRef.current = setTimeout(() => {
      setVisible(false)
      setJobId(null)
      setProgress(null)
      setDismissing(false)
    }, 500)
  }, [])

  const cancel = useCallback(async () => {
    if (!jobId) return
    stopPoll()
    const elec = (window as any).electronAPI
    if (elec?.cancelExport) {
      elec.cancelExport()
    } else {
      await fetch(`http://127.0.0.1:${PORT()}/export/cancel/${jobId}`, { method: 'POST' }).catch(() => {})
    }
    dismiss()
  }, [jobId, stopPoll, dismiss])

  // Listen for AI agent export event
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<{ jobId: string }>).detail
      if (!detail?.jobId) return
      const jid = detail.jobId

      stopPoll()
      if (dismissRef.current) { clearTimeout(dismissRef.current); dismissRef.current = null }

      setJobId(jid)
      setVisible(true)
      setDismissing(false)
      setProgress({ jobId: jid, frame: 0, total: 0, percent: 0, done: false, error: null, path: null })

      const elec = (window as any).electronAPI

      //   Electron native path  
      if (jid === 'native' && elec?.onExportProgress) {
        elecClean.current = elec.onExportProgress(
          (p: { frame: number; total: number; done: boolean; error: string; status?: string }) => {
            const pct = p.total > 0 ? Math.round((p.frame / p.total) * 100) : 0
            setProgress({
              jobId: 'native', frame: p.frame, total: p.total,
              percent: pct, done: p.done, error: p.error || null,
              path: null, status: p.status,
            })
            if (p.done) { stopPoll(); if (!p.error) setTimeout(dismiss, 4000) }
          }
        )
        return
      }

      //   Python REST polling path  
      pollRef.current = setInterval(async () => {
        try {
          const r = await fetch(`http://127.0.0.1:${PORT()}/export/progress/${jid}`)
          if (!r.ok) { stopPoll(); return }
          const p: ExportProgress = await r.json()
          setProgress(p)
          if (p.done) { stopPoll(); if (!p.error) setTimeout(dismiss, 4000) }
        } catch { stopPoll() }
      }, 500)
    }

    window.addEventListener('fade:export-started', handler)
    return () => {
      window.removeEventListener('fade:export-started', handler)
      stopPoll()
      if (dismissRef.current) clearTimeout(dismissRef.current)
    }
  }, [stopPoll, dismiss])

  if (!visible) return null

  const pct = progress?.percent ?? 0
  const done = progress?.done    ?? false
  const hasError = !!progress?.error

  return (
    <div className={`exp-ov ${dismissing ? 'exp-ov--out' : 'exp-ov--in'}`}>
      {/* Header row */}
      <div className="exp-ov__header">
        <span className="exp-ov__icon">
          {hasError ? '❌' : done ? '✅' : '📤'}
        </span>
        <span className="exp-ov__title">
          {hasError ? 'Export failed' : done ? 'Export complete' : 'Exporting…'}
        </span>
        {(done || hasError) && (
          <button className="exp-ov__close" onClick={dismiss} aria-label="Close">✕</button>
        )}
      </div>

      {/* Progress bar */}
      {!done && !hasError && (
        <div className="exp-ov__track">
          <div className="exp-ov__fill" style={{ width: `${pct}%` }} />
        </div>
      )}

      {/* Status */}
      <div className="exp-ov__status">
        {hasError ? (
          <span className="exp-ov__error-msg">{progress?.error}</span>
        ) : done ? (
          <span className="exp-ov__done-msg">
            Saved successfully · closing in 4 s
            {progress?.path && <><br /><code className="exp-ov__path">{progress.path}</code></>}
          </span>
        ) : (
          <span className="exp-ov__running">
            <span className="exp-ov__pct">{pct}%</span>
            {(progress?.total ?? 0) > 0 && (
              <span className="exp-ov__frames">frame {progress!.frame} / {progress!.total}</span>
            )}
            {progress?.status && <span className="exp-ov__phase">{progress.status}</span>}
          </span>
        )}
      </div>

      {/* Cancel */}
      {!done && !hasError && (
        <button className="exp-ov__cancel" onClick={cancel}>Cancel</button>
      )}
    </div>
  )
}
