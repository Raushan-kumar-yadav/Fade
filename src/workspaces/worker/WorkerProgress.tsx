/**
 * WorkerProgress - Floating circular progress button (top-right).
 * Sources: /worker/jobs (waveform cache) + /jobs/ (TTS/image/video, SSE + poll)
 */
import React, { useState, useEffect, useRef } from 'react';
import './WorkerProgress.css';

function port(): number { return (window as any).__FADE_PORT__ ?? 8000; }
const base = () => `http://127.0.0.1:${port()}`;

interface WorkerStatus { alive: boolean; queueDepth: number; }

interface Job {
  id: string;
  type: string;
  label: string;
  status: 'pending' | 'running' | 'done' | 'error';
  progress?: number;
  message?: string;
  error?: string;
  _source?: 'worker' | 'jobs';
}

function IconCheck() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
      <path d="M2 6 L5 9 L10 3" stroke="#34d399" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}
function IconSpin() { return <span className="wp-job-spin" />; }
function IconError() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
      <path d="M6 2v5M6 9v1" stroke="#f87171" strokeWidth="1.8" strokeLinecap="round"/>
    </svg>
  );
}

function Ring({ progress, active, hasError }: { progress: number; active: boolean; hasError: boolean }) {
  const R = 8, C = 2 * Math.PI * R;
  const dash = C * (1 - Math.max(0, Math.min(1, progress)));
  const color = hasError ? '#f87171' : active ? '#6366f1' : '#34d399';
  return (
    <svg className="wp-ring" width="24" height="24" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r={R} fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="2"/>
      <circle cx="12" cy="12" r={R} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round"
        strokeDasharray={C} strokeDashoffset={dash} transform="rotate(-90 12 12)"
        style={{ transition: 'stroke-dashoffset 0.5s ease, stroke 0.3s' }}
      />
    </svg>
  );
}

function jobTypeLabel(type: string): string {
  switch (type) {
    case 'waveform':       return '\u303f Waveform';
    case 'whisper':        return '\uD83C\uDF99 Transcribe';
    case 'video_download': return '\u2b07 Download Video';
    case 'image_download': return '\u2b07 Download Image';
    case 'image_generate': return '\uD83C\uDFA8 Generate Image';
    case 'tts_generate':   return '\uD83D\uDD0A Generate TTS';
    case 'video_index':    return '\uD83D\uDD0D Index Video';
    case 'image_index':    return '\uD83D\uDD0D Index Image';
    default:               return type.replace(/_/g, ' ');
  }
}

async function fetchWorkerStatus(): Promise<WorkerStatus> {
  const r = await fetch(`${base()}/worker/status`);
  return r.json();
}

async function fetchWorkerJobs(): Promise<Job[]> {
  try {
    const r = await fetch(`${base()}/worker/jobs`);
    if (!r.ok) return [];
    const arr: any[] = await r.json();
    return arr.map(j => ({ ...j, _source: 'worker' as const }));
  } catch { return []; }
}

async function fetchMediaJobs(): Promise<Job[]> {
  try {
    const r = await fetch(`${base()}/jobs/?active_only=false`);
    if (!r.ok) return [];
    const data = await r.json();
    const arr: any[] = data.jobs ?? [];
    return arr.map(j => ({
      id: j.jobId, type: j.type, label: j.label,
      status: j.status, progress: j.progress,
      message: j.message, error: j.error,
      _source: 'jobs' as const,
    }));
  } catch { return []; }
}

export default function WorkerProgress() {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<WorkerStatus>({ alive: false, queueDepth: 0 });
  const [workerJobs, setWorkerJobs] = useState<Job[]>([]);
  const [mediaJobs, setMediaJobs] = useState<Job[]>([]);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try { const s = await fetchWorkerStatus(); if (alive) setStatus(s); } catch {}
    };
    poll();
    const id = setInterval(poll, 2000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  useEffect(() => {
    let alive = true;
    const poll = async () => { const j = await fetchWorkerJobs(); if (alive) setWorkerJobs(j); };
    poll();
    const id = setInterval(poll, 3000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  useEffect(() => {
    let alive = true;
    const poll = async () => { const j = await fetchMediaJobs(); if (alive) setMediaJobs(j); };
    poll();
    const id = setInterval(poll, 2000);

    let es: EventSource | null = null;
    try {
      es = new EventSource(`${base()}/events`);
      es.addEventListener('job', (e: MessageEvent) => {
        try {
          const job = JSON.parse(e.data);
          if (!job?.jobId) return;
          setMediaJobs(prev => {
            const idx = prev.findIndex(j => j.id === job.jobId);
            const mapped: Job = {
              id: job.jobId, type: job.type, label: job.label,
              status: job.status, progress: job.progress,
              message: job.message, error: job.error, _source: 'jobs',
            };
            if (idx === -1) return [mapped, ...prev];
            const next = [...prev]; next[idx] = mapped; return next;
          });
        } catch {}
      });
    } catch {}
    return () => { alive = false; clearInterval(id); es?.close(); };
  }, []);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const allJobs: Job[] = (() => {
    const map = new Map<string, Job>();
    for (const j of [...workerJobs, ...mediaJobs]) map.set(j.id, j);
    const order: Record<string, number> = { pending: 0, running: 1, error: 2, done: 3 };
    return Array.from(map.values()).sort((a, b) => (order[a.status] ?? 9) - (order[b.status] ?? 9));
  })();

  const pending   = allJobs.filter(j => j.status === 'pending' || j.status === 'running');
  const done      = allJobs.filter(j => j.status === 'done');
  const errors    = allJobs.filter(j => j.status === 'error');
  const total     = allJobs.length;
  const progress  = total > 0 ? done.length / total : (status.alive ? 1 : 0);
  const hasActive = status.queueDepth > 0 || pending.length > 0;
  const hasError  = errors.length > 0;
  const visible   = [...pending, ...errors, ...done.slice(0, 6)];

  const jobIcon = (j: Job) => {
    if (j.status === 'done')  return <IconCheck />;
    if (j.status === 'error') return <IconError />;
    return <IconSpin />;
  };

  return (
    <div className="wp-root" ref={panelRef}>
      <button
        className={`wp-btn${open ? ' wp-btn--open' : ''}${hasActive ? ' wp-btn--active' : ''}`}
        onClick={() => setOpen(o => !o)}
        title="Background Tasks" aria-label="Background worker tasks"
      >
        <Ring progress={progress} active={hasActive} hasError={hasError} />
        {hasActive && <span className="wp-badge">{pending.length || status.queueDepth}</span>}
      </button>

      {open && (
        <div className="wp-panel">
          <div className="wp-panel__header">
            <span className="wp-panel__title">Background Jobs</span>
            <span className={`wp-panel__status${status.alive ? ' alive' : ' dead'}`}>
              {status.alive ? '\u25cf Online' : '\u25cb Offline'}
            </span>
          </div>

          {visible.length === 0 ? (
            <div className="wp-panel__empty">
              <span className="wp-panel__empty-icon">\u26a1</span>
              <span>No active jobs</span>
              {!status.alive && <span className="wp-panel__empty-sub">Worker not running</span>}
            </div>
          ) : (
            <>
              <div className="wp-panel__summary">
                <div className="wp-summary-bar">
                  <div className="wp-summary-bar__fill" style={{ width: `${progress * 100}%` }} />
                </div>
                <span className="wp-panel__count">
                  {done.length}/{total} completed{errors.length > 0 && `, ${errors.length} failed`}
                </span>
              </div>

              <div className="wp-panel__jobs">
                {visible.map(j => (
                  <div key={j.id} className={`wp-job wp-job--${j.status}`}>
                    <span className="wp-job__icon">{jobIcon(j)}</span>
                    <div className="wp-job__info">
                      <span className="wp-job__type">{jobTypeLabel(j.type)}</span>
                      <span className="wp-job__label">{j.message || j.label}</span>
                      {j.status === 'error' && j.error && (
                        <span className="wp-job__error">{j.error.slice(0, 80)}</span>
                      )}
                    </div>
                    {(j.status === 'running' || j.status === 'pending') && (j.progress ?? 0) > 0 && (
                      <div className="wp-job__prog-wrap">
                        <div className="wp-job__prog" style={{ width: `${(j.progress ?? 0) * 100}%` }} />
                      </div>
                    )}
                    <span className="wp-job__status-text">{j.status}</span>
                  </div>
                ))}
              </div>
            </>
          )}

          <div className="wp-panel__footer">
            <span className="wp-panel__queue">Queue: {status.queueDepth}</span>
            <div style={{ display: 'flex', gap: 6 }}>
              <button className="wp-panel__clear" onClick={async () => {
                try {
                  const port = (window as any).__FADE_PORT__ ?? 8000;
                  await fetch(`http://127.0.0.1:${port}/jobs/clear-stuck?older_than_s=15`, { method: 'DELETE' });
                } catch { /* ignore */ }
              }} title="Mark all stuck pending jobs as failed">Clear stuck</button>
              <button className="wp-panel__clear" onClick={() => {
                setWorkerJobs(prev => prev.filter(j => j.status !== 'done'));
                setMediaJobs(prev => prev.filter(j => j.status !== 'done'));
              }}>Clear done</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
