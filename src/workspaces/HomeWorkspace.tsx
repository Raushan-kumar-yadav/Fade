import { useState, useEffect } from 'react'
import './HomeWorkspace.css'

const PORT = () => (window as any).__FADE_PORT__ ?? 8000
const api = (path: string, opts?: RequestInit) =>
  fetch(`http://127.0.0.1:${PORT()}${path}`, opts)

interface BackendStatus {
  ready: boolean
  python: string
  port: number | null
}

interface HomeWorkspaceProps { onProjectCreated?: () => void }

export default function HomeWorkspace({ onProjectCreated: _ }: HomeWorkspaceProps) {
  const [status, setStatus] = useState<BackendStatus>({ ready: false, python: '—', port: null })

  useEffect(() => {
    const check = () => {
      api('/health')
        .then(r => r.ok ? r.json() : null)
        .then(d => {
          if (d) setStatus({ ready: true, python: d.python ?? '3.12', port: PORT() })
        })
        .catch(() => setStatus(s => ({ ...s, ready: false })))
    }
    check()
    const t = setInterval(check, 5000)
    return () => clearInterval(t)
  }, [])

  const cards = [
    {
      icon: '🎬',
      title: 'Video Editor',
      desc: 'Multi-track timeline, real-time preview, GPU-accelerated compositing.',
      tab: 'video',
      color: '#6c63ff',
    },
    {
      icon: '🤖',
      title: 'AI Director',
      desc: 'Natural-language edits, auto-download media, generate WebComp animations.',
      tab: 'ai',
      color: '#00d4aa',
    },
    {
      icon: '🎵',
      title: 'Audio Suite',
      desc: 'Waveform editor, AI voiceover (Kokoro TTS), background music.',
      tab: 'audio',
      color: '#ffd60a',
    },
    {
      icon: '📤',
      title: 'Export',
      desc: 'H.264 / NVENC hardware encoding, custom resolution & bitrate.',
      tab: 'export',
      color: '#ff6584',
    },
  ]

  return (
    <div className="home-ws home-ws--welcome">
      {/* Hero */}
      <div className="hw-hero">
        <div className="hw-hero__glow" />
        <h1 className="hw-hero__title">
          Fade
          <span className="hw-hero__badge">Studio</span>
        </h1>
        <p className="hw-hero__sub">Professional AI-powered video editor</p>

        {/* Backend status pill */}
        <div className={`hw-status-pill ${status.ready ? 'hw-status-pill--ok' : 'hw-status-pill--off'}`}>
          <span className="hw-status-pill__dot" />
          {status.ready
            ? `Backend ready · Python ${status.python} · Port ${status.port}`
            : 'Backend connecting…'}
        </div>
      </div>

      {/* Feature cards */}
      <div className="hw-cards">
        {cards.map(c => (
          <div key={c.tab} className="hw-card" style={{ '--card-color': c.color } as any}>
            <div className="hw-card__icon">{c.icon}</div>
            <div className="hw-card__body">
              <div className="hw-card__title">{c.title}</div>
              <div className="hw-card__desc">{c.desc}</div>
            </div>
            <div className="hw-card__shine" />
          </div>
        ))}
      </div>

      {/* Quick tips */}
      <div className="hw-tips">
        <div className="hw-tips__title">Quick Start</div>
        <ul className="hw-tips__list">
          <li>→ Switch to <strong>Video</strong> tab to open the timeline</li>
          <li>→ Drag &amp; drop media into the Library panel to import</li>
          <li>→ Use the <strong>AI</strong> tab to let the AI Director build edits for you</li>
          <li>→ Press <kbd>Space</kbd> to play / pause, <kbd>←</kbd> <kbd>→</kbd> to step frames</li>
        </ul>
      </div>
    </div>
  )
}
