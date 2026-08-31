import { useState, useEffect } from 'react'
import { Allotment } from 'allotment'
import 'allotment/dist/style.css'
import ViewportWidget from './viewport/ViewportWidget'
import './AIWorkspace.css'

// Port hook  

function usePort(): number {
  const [port, setPort] = useState<number>((window as any).__FADE_PORT__ ?? 8000)
  useEffect(() => {
    const h = (e: Event) => setPort((e as CustomEvent<number>).detail)
    window.addEventListener('fade:port', h, { once: true })
    return () => window.removeEventListener('fade:port', h)
  }, [])
  return port
}

// AI Status sidebar  

function AISidebar() {
  const port = usePort()
  const [aiStatus, setAiStatus] = useState<{
    provider: string
    model: string
    ollama_running?: boolean
  } | null>(null)

  useEffect(() => {
    fetch(`http://127.0.0.1:${port}/ai/status`)
      .then(r => r.json())
      .then(d => setAiStatus(d))
      .catch(() => {})
  }, [port])

  return (
    <div className="ai-sidebar">
      {/* Header */}
      <div className="ai-sidebar__header">
        <div className="ai-sidebar__logo">
          <span className="ai-sidebar__logo-icon">✦</span>
          AI Director
        </div>
        <div className="ai-sidebar__tagline">Powered by your local model</div>
      </div>

      {/* Model badge */}
      {aiStatus && (
        <div className="ai-sidebar__model-card">
          <div className="ai-sidebar__model-row">
            <span className={`ai-sidebar__dot ${aiStatus.ollama_running === false ? 'ai-sidebar__dot--off' : 'ai-sidebar__dot--on'}`} />
            <span className="ai-sidebar__model-provider">{aiStatus.provider}</span>
          </div>
          <div className="ai-sidebar__model-name">{aiStatus.model || 'auto-detect'}</div>
        </div>
      )}

      {/* Open chat button */}
      <button
        className="ai-sidebar__open-btn"
        onClick={() => window.dispatchEvent(new CustomEvent('fade:ai-toggle'))}
      >
        <span className="ai-sidebar__open-icon">💬</span>
        Open AI Chat
      </button>

      {/* Tips */}
      <div className="ai-sidebar__tips">
        <div className="ai-sidebar__tips-title">What can I do?</div>
        {[
          { icon: '✂️', text: 'Split, trim & rearrange clips' },
          { icon: '✨', text: 'Apply & animate effects' },
          { icon: '⬇️', text: 'Download footage & images' },
          { icon: '📰', text: 'Generate news videos automatically' },
          { icon: '🎙️', text: 'Transcribe audio to captions' },
          { icon: '🎨', text: 'Generate AI images for your project' },
          { icon: '🌊', text: 'Add transitions between all clips' },
        ].map(tip => (
          <div key={tip.icon} className="ai-sidebar__tip">
            <span className="ai-sidebar__tip-icon">{tip.icon}</span>
            <span>{tip.text}</span>
          </div>
        ))}
      </div>

      {/* Keyboard shortcut hint */}
      <div className="ai-sidebar__shortcut">
        <span className="ai-sidebar__shortcut-key">🤖</span> button on Video tab also opens the chat
      </div>
    </div>
  )
}

// AI Workspace root  

export default function AIWorkspace() {
  return (
    <div className="ai-ws">
      <Allotment>
         
        <Allotment.Pane minSize={240} maxSize={360} preferredSize={300}>
          <AISidebar />
        </Allotment.Pane>

         
        <Allotment.Pane minSize={320}>
          <div className="ai-viewport-pane">
            <ViewportWidget />
          </div>
        </Allotment.Pane>
      </Allotment>
    </div>
  )
}
