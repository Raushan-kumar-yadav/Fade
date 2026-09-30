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

type IntegrityState =
  | { phase: 'idle' }
  | { phase: 'registering' }
  | { phase: 'done'; artifactId: string; tx: string | null; wmPath: string | null }
  | { phase: 'error'; message: string }

const PORT = () => (window as any).__FADE_PORT__ ?? 8000

async function registerIntegrity(videoPath: string): Promise<{ artifactId: string; tx: string | null; wmPath: string | null }> {
  const r = await fetch(`http://127.0.0.1:${PORT()}/integrity/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ video_path: videoPath }),
  })
  if (!r.ok) {
    const d = await r.json().catch(() => ({}))
    throw new Error(d.detail ?? `Server error ${r.status}`)
  }
  const d = await r.json()
  return {
    artifactId: d.artifact_id,
    tx: d.batch?.tx ?? null,
    wmPath: d.watermarked_output_path ?? null,
  }
}

function downloadProof(artifactId: string) {
  const url = `http://127.0.0.1:${PORT()}/integrity/proof/${artifactId}`
  const a = document.createElement('a')
  a.href = url
  a.download = `${artifactId}.proof.json`
  a.click()
}

export default function ExportProgressOverlay() {
  const [jobId, setJobId] = useState<string | null>(null)
  const [progress, setProgress] = useState<ExportProgress | null>(null)
  const [visible, setVisible] = useState(false)
  const [dismissing, setDismissing] = useState(false)
  const [integrity, setIntegrity] = useState<IntegrityState>({ phase: 'idle' })

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
      setIntegrity({ phase: 'idle' })
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
      setIntegrity({ phase: 'idle' })
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

  const handleRegister = async () => {
    if (!progress?.path) return
    setIntegrity({ phase: 'registering' })
    try {
      const result = await registerIntegrity(progress.path)
      setIntegrity({ phase: 'done', ...result })
    } catch (err: any) {
      setIntegrity({ phase: 'error', message: err.message ?? 'Registration failed' })
    }
  }

  return (
    <div className={`exp-ov ${dismissing ? 'exp-ov--out' : 'exp-ov--in'}`}>
      {/* Header row */}
      <div className="exp-ov__header">
        <span className="exp-ov__icon">
          {hasError ? '?' : done ? '?' : '??'}
        </span>
        <span className="exp-ov__title">
          {hasError ? 'Export failed' : done ? 'Export complete' : 'Exporting.'}
        </span>
        {(done || hasError) && (
          <button className="exp-ov__close" onClick={dismiss} aria-label="Close">?</button>
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
            Saved successfully closing in 4 s
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

      {/* ── Integrity Registration Section ────────────────────────────── */}
      {done && !hasError && progress?.path && (
        <div className="exp-ov__integrity">
          {integrity.phase === 'idle' && (
            <>
              <div className="exp-ov__integrity-title">
                <span className="exp-ov__integrity-shield">&#x1F512;</span>
                Register for Integrity Verification?
              </div>
              <div className="exp-ov__integrity-steps">
                <span>&#x2022; SHA-256 exact fingerprint</span>
                <span>&#x2022; Perceptual hash (survives re-encoding)</span>
                <span>&#x2022; Invisible watermark embedded in pixels</span>
              </div>
              <div className="exp-ov__integrity-actions">
                <button className="exp-ov__integrity-btn exp-ov__integrity-btn--primary" onClick={handleRegister}>
                  Register + Watermark
                </button>
                <button className="exp-ov__integrity-btn exp-ov__integrity-btn--skip" onClick={dismiss}>
                  Skip
                </button>
              </div>
            </>
          )}

          {integrity.phase === 'registering' && (
            <div className="exp-ov__integrity-progress">
              <span className="exp-ov__integrity-spinner" />
              <span className="exp-ov__integrity-registering-text">
                Hashing &bull; Computing fingerprint &bull; Embedding watermark&hellip;
              </span>
            </div>
          )}

          {integrity.phase === 'done' && (
            <div className="exp-ov__integrity-result">
              <div className="exp-ov__integrity-ok">&#x2705; Registered on tamper-evident ledger</div>
              <div className="exp-ov__integrity-meta">
                <span className="exp-ov__integrity-label">Artifact ID</span>
                <code className="exp-ov__integrity-value">{integrity.artifactId}</code>
              </div>
              {integrity.tx && (
                <div className="exp-ov__integrity-meta">
                  <span className="exp-ov__integrity-label">Ledger TX</span>
                  <code className="exp-ov__integrity-value" title={integrity.tx}>
                    {integrity.tx.slice(0, 20)}&hellip;
                  </code>
                </div>
              )}
              <div className="exp-ov__integrity-proof-btns">
                <button
                  className="exp-ov__integrity-btn exp-ov__integrity-btn--proof"
                  onClick={() => downloadProof(integrity.artifactId)}
                >
                  &#x2B07; Download Proof JSON
                </button>
                {integrity.wmPath && (
                  <button
                    className="exp-ov__integrity-btn exp-ov__integrity-btn--wm"
                    onClick={() => {
                      const elec = (window as any).electronAPI
                      if (elec?.showItemInFolder) elec.showItemInFolder(integrity.wmPath)
                    }}
                    title={integrity.wmPath}
                  >
                    &#x1F4C2; Open Watermarked Copy
                  </button>
                )}
              </div>
            </div>
          )}

          {integrity.phase === 'error' && (
            <div className="exp-ov__integrity-error">
              <span>&#x26A0;&#xFE0F; Registration failed: {integrity.message}</span>
              <button className="exp-ov__integrity-btn exp-ov__integrity-btn--retry" onClick={handleRegister}>
                Retry
              </button>
            </div>
          )}
        </div>
      )}
      {/* ─────────────────────────────────────────────────────────────── */}
    </div>
  )
}
