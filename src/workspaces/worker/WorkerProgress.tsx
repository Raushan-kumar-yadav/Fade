/**
 * WorkerProgress — Floating circular progress button (top-right).
 * Click to open/close the background-jobs panel.
 *
 * Polls GET /worker/status every 2s for queue depth.
 * Polls GET /worker/jobs every 3s for individual job list.
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import './WorkerProgress.css';

function port(): number { return (window as any).__FADE_PORT__ ?? 8000; }
const base = () => `http://127.0.0.1:${port()}`;

interface WorkerStatus {
  alive: boolean;
  queueDepth: number;
}

interface Job {
  id: string;
  type: string;        // 'waveform' | 'whisper' | ...
  label: string;
  status: 'pending' | 'running' | 'done' | 'error';
  progress?: number;   // 0-1 if available
  message?: string;
}

// In-process job registry — updated by waveform cache poll and future whisper
// We construct this from waveform_cache status exposed by a new /worker/jobs endpoint
async function fetchStatus(): Promise<WorkerStatus> {
  const r = await fetch(`${base()}/worker/status`);
  return r.json();
}

async function fetchJobs(): Promise<Job[]> {
  try {
    const r = await fetch(`${base()}/worker/jobs`);
    if (!r.ok) return [];
    return r.json();
  } catch {
    return [];
  }
}

// ── Icons ─────────────────────────────────────────────────────────────────────

function IconCheck() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
      <path d="M2 6 L5 9 L10 3" stroke="#34d399" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}
function IconSpin() {
  return <span className="wp-job-spin" />;
}
function IconError() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
      <path d="M6 2v5M6 9v1" stroke="#f87171" strokeWidth="1.8" strokeLinecap="round"/>
    </svg>
  );
}
function IconWorker() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
      <circle cx="7" cy="7" r="5" stroke="currentColor" strokeWidth="1.4"/>
      <path d="M7 4v3l2 1.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
    </svg>
  );
}

// ── Circular progress ring ────────────────────────────────────────────────────

interface RingProps {
  progress: number;   // 0-1
  active: boolean;
  hasError: boolean;
}

function Ring({ progress, active, hasError }: RingProps) {
  const R = 8;
  const C = 2 * Math.PI * R;
  const dash = C * (1 - progress);
  const color = hasError ? '#f87171' : active ? '#6366f1' : '#34d399';
  return (
    <svg className="wp-ring" width="24" height="24" viewBox="0 0 24 24">
      {/* Track */}
      <circle cx="12" cy="12" r={R} fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="2"/>
      {/* Progress arc */}
      <circle
        cx="12" cy="12" r={R}
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeDasharray={C}
        strokeDashoffset={dash}
        transform="rotate(-90 12 12)"
        style={{ transition: 'stroke-dashoffset 0.5s ease, stroke 0.3s' }}
      />
    </svg>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function WorkerProgress() {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<WorkerStatus>({ alive: false, queueDepth: 0 });
  const [jobs, setJobs] = useState<Job[]>([]);
  const panelRef = useRef<HTMLDivElement>(null);

  // Poll /worker/status
  useEffect(() => {
    let alive = true;
    async function poll() {
      try {
        const s = await fetchStatus();
        if (alive) setStatus(s);
      } catch { /* backend not ready */ }
    }
    poll();
    const id = setInterval(poll, 2000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  // Poll /worker/jobs when panel is open
  useEffect(() => {
    if (!open) return;
    let alive = true;
    async function poll() {
      const j = await fetchJobs();
      if (alive) setJobs(j);
    }
    poll();
    const id = setInterval(poll, 1500);
    return () => { alive = false; clearInterval(id); };
  }, [open]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open]);

  const pending   = jobs.filter(j => j.status === 'pending' || j.status === 'running');
  const done      = jobs.filter(j => j.status === 'done');
  const errors    = jobs.filter(j => j.status === 'error');
  const total     = jobs.length;
  const progress  = total > 0 ? done.length / total : (status.alive ? 1 : 0);
  const hasActive = status.queueDepth > 0 || pending.length > 0;
  const hasError  = errors.length > 0;

  const jobIcon = (j: Job) => {
    if (j.status === 'done')    return <IconCheck />;
    if (j.status === 'error')   return <IconError />;
    return <IconSpin />;
  };

  const jobTypeLabel = (type: string) => {
    switch(type) {
      case 'waveform': return '〰 Waveform';
      case 'whisper':  return '🎙 Transcribe';
      default:         return type;
    }
  };

  return (
    <div className="wp-root" ref={panelRef}>
      {/* Inline tb-tool-btn style button */}
      <button
        className={`wp-btn${open ? ' wp-btn--open' : ''}${hasActive ? ' wp-btn--active' : ''}`}
        onClick={() => setOpen(o => !o)}
        title="Background Tasks"
        aria-label="Background worker tasks"
      >
        <Ring progress={progress} active={hasActive} hasError={hasError} />
        {hasActive && (
          <span className="wp-badge">{status.queueDepth || pending.length}</span>
        )}
      </button>

      {/* Dropdown panel */}
      {open && (
        <div className="wp-panel">
          <div className="wp-panel__header">
            <span className="wp-panel__title">Background Jobs</span>
            <span className={`wp-panel__status${status.alive ? ' alive' : ' dead'}`}>
              {status.alive ? '● Online' : '○ Offline'}
            </span>
          </div>

          {jobs.length === 0 ? (
            <div className="wp-panel__empty">
              <span className="wp-panel__empty-icon">⚡</span>
              <span>No active jobs</span>
              {!status.alive && (
                <span className="wp-panel__empty-sub">Worker not running</span>
              )}
            </div>
          ) : (
            <>
              {/* Summary bar */}
              <div className="wp-panel__summary">
                <div className="wp-summary-bar">
                  <div
                    className="wp-summary-bar__fill"
                    style={{ width: `${progress * 100}%` }}
                  />
                </div>
                <span className="wp-panel__count">
                  {done.length}/{total} completed
                  {errors.length > 0 && `, ${errors.length} failed`}
                </span>
              </div>

              {/* Job list */}
              <div className="wp-panel__jobs">
                {[...pending, ...done.slice(-6), ...errors].map(j => (
                  <div key={j.id} className={`wp-job wp-job--${j.status}`}>
                    <span className="wp-job__icon">{jobIcon(j)}</span>
                    <div className="wp-job__info">
                      <span className="wp-job__type">{jobTypeLabel(j.type)}</span>
                      <span className="wp-job__label">{j.label}</span>
                    </div>
                    <span className="wp-job__status-text">{j.status}</span>
                  </div>
                ))}
              </div>
            </>
          )}

          {/* Footer */}
          <div className="wp-panel__footer">
            <span className="wp-panel__queue">Queue: {status.queueDepth}</span>
            <button
              className="wp-panel__clear"
              onClick={() => setJobs(prev => prev.filter(j => j.status !== 'done'))}
            >
              Clear done
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
