import { useState, useRef, useEffect, useCallback } from 'react'
import { Allotment } from 'allotment'
import 'allotment/dist/style.css'
import './AIWorkspace.css'

// ── Types ──────────────────────────────────────────────────────────────────────

type MsgRole = 'ai' | 'user' | 'tool_call' | 'tool_result' | 'error'
interface Message {
  id: string
  role: MsgRole
  text: string
  toolName?: string
  toolArgs?: Record<string, unknown>
  streaming?: boolean
}

const uid = () => Math.random().toString(36).slice(2, 9)

// ── Hook: backend port ─────────────────────────────────────────────────────────

function usePort(): number {
  const [port, setPort] = useState<number>((window as any).__FADE_PORT__ ?? 8000)
  useEffect(() => {
    const h = (e: Event) => setPort((e as CustomEvent<number>).detail)
    window.addEventListener('fade:port', h, { once: true })
    return () => window.removeEventListener('fade:port', h)
  }, [])
  return port
}

// ── Chat Panel ─────────────────────────────────────────────────────────────────

interface ChatPanelProps {
  collapsed: boolean
  onToggle: () => void
}

function ChatPanel({ collapsed, onToggle }: ChatPanelProps) {
  const port = usePort()
  const [messages, setMessages] = useState<Message[]>([
    { id: uid(), role: 'ai', text: 'Hello! I\'m your AI Director. I can split clips, add effects, transcribe audio, and more. What would you like to do?' },
  ])
  const [input, setInput]       = useState('')
  const [busy, setBusy]         = useState(false)
  const [aiStatus, setAiStatus] = useState<{
    provider: string;
    model: string;
    ollama_running?: boolean;
    available_models?: string[];
  } | null>(null)
  const bottomRef  = useRef<HTMLDivElement>(null)
  const abortRef   = useRef<AbortController | null>(null)
  const historyRef = useRef<{role: string; text: string}[]>([])

  // Fetch AI status on mount
  useEffect(() => {
    fetch(`http://127.0.0.1:${port}/ai/status`)
      .then(r => r.json())
      .then(d => setAiStatus(d))
      .catch(() => {})
  }, [port])

  const scrollBottom = useCallback(() => {
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)
  }, [])

  const appendMsg = useCallback((msg: Message) => {
    setMessages(prev => [...prev, msg])
    scrollBottom()
  }, [scrollBottom])

  const patchLast = useCallback((patch: Partial<Message>) => {
    setMessages(prev => {
      const copy = [...prev]
      const last = { ...copy[copy.length - 1], ...patch }
      copy[copy.length - 1] = last
      return copy
    })
  }, [])

  async function send() {
    const text = input.trim()
    if (!text || busy) return
    setInput('')
    setBusy(true)

    // Add user message
    appendMsg({ id: uid(), role: 'user', text })
    historyRef.current = [...historyRef.current, { role: 'user', text }]

    // Create placeholder AI message for streaming
    const aiId = uid()
    appendMsg({ id: aiId, role: 'ai', text: '', streaming: true })

    let aiText = ''
    abortRef.current = new AbortController()

    try {
      const res = await fetch(`http://127.0.0.1:${port}/ai/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, history: historyRef.current.slice(-20), port }),
        signal: abortRef.current.signal,
      })

      const reader = res.body!.getReader()
      const decoder = new TextDecoder()

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const raw = decoder.decode(value)
        for (const line of raw.split('\n')) {
          if (!line.startsWith('data: ')) continue
          try {
            const evt = JSON.parse(line.slice(6))

            if (evt.type === 'token') {
              aiText += evt.content
              patchLast({ text: aiText, streaming: true })
              scrollBottom()

            } else if (evt.type === 'tool_call') {
              appendMsg({
                id: uid(),
                role: 'tool_call',
                text: '',
                toolName: evt.name,
                toolArgs: evt.args,
              })

            } else if (evt.type === 'tool_result') {
              appendMsg({
                id: uid(),
                role: 'tool_result',
                text: evt.content,
                toolName: evt.name,
              })
              // Resume streaming placeholder
              const nextId = uid()
              appendMsg({ id: nextId, role: 'ai', text: '', streaming: true })
              aiText = ''

            } else if (evt.type === 'done') {
              patchLast({ streaming: false })
              // Remove empty trailing AI messages
              setMessages(prev => prev.filter((m, i) => i === 0 || m.text !== '' || m.role !== 'ai'))

            } else if (evt.type === 'error') {
              patchLast({ text: `⚠ Error: ${evt.message}`, streaming: false, role: 'error' })
            }
          } catch { /* ignore parse errors */ }
        }
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        patchLast({ text: `⚠ Connection error: ${err.message}`, streaming: false, role: 'error' })
      }
    }

    historyRef.current = [...historyRef.current, { role: 'ai', text: aiText }]
    setBusy(false)
  }

  function stop() {
    abortRef.current?.abort()
    setBusy(false)
  }

  function handleKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  return (
    <div className={`chat-panel${collapsed ? ' chat-panel--collapsed' : ''}`}>
      <div className="chat-panel__header">
        {!collapsed && (
          <span className="chat-header-title">
            AI Director
            {aiStatus && (
              <span className="ai-badge">
                <span className={`ai-dot ${aiStatus.ollama_running === false ? 'ai-dot--off' : 'ai-dot--on'}`} />
                {aiStatus.provider} · {aiStatus.model}
              </span>
            )}
          </span>
        )}
        <button className="chat-panel__toggle" onClick={onToggle} title={collapsed ? 'Expand' : 'Collapse'}>
          {collapsed ? '›' : '‹'}
        </button>
      </div>

      {!collapsed && (
        <>
          <div className="chat-panel__messages">
            {messages.map(m => (
              <MessageBubble key={m.id} msg={m} />
            ))}
            {busy && <div className="ai-thinking"><span/><span/><span/></div>}
            <div ref={bottomRef} />
          </div>

          <TranscribeBar port={port} appendMsg={appendMsg} />

          <div className="chat-panel__input-row">
            <div className="chat-input-wrap">
              <textarea
                className="chat-input"
                placeholder="Ask AI to edit your timeline..."
                value={input}
                rows={2}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKey}
                disabled={busy}
              />
            </div>
            {busy
              ? <button className="chat-send chat-send--stop" onClick={stop} title="Stop">■</button>
              : <button className="chat-send" onClick={send} title="Send (Enter)">↑</button>
            }
          </div>
        </>
      )}
    </div>
  )
}

// ── Message bubble ─────────────────────────────────────────────────────────────

function MessageBubble({ msg }: { msg: Message }) {
  if (msg.role === 'tool_call') {
    return (
      <div className="tool-card tool-card--call">
        <span className="tool-card__icon">⚙</span>
        <div>
          <div className="tool-card__name">{msg.toolName}</div>
          {msg.toolArgs && Object.keys(msg.toolArgs).length > 0 && (
            <pre className="tool-card__args">{JSON.stringify(msg.toolArgs, null, 2)}</pre>
          )}
        </div>
      </div>
    )
  }

  if (msg.role === 'tool_result') {
    const preview = msg.text.length > 200 ? msg.text.slice(0, 200) + '…' : msg.text
    return (
      <div className="tool-card tool-card--result">
        <span className="tool-card__icon">✓</span>
        <div>
          <div className="tool-card__name">{msg.toolName} done</div>
          <div className="tool-card__summary">{preview}</div>
        </div>
      </div>
    )
  }

  return (
    <div className={`chat-msg chat-msg--${msg.role === 'error' ? 'error' : msg.role}`}>
      {msg.role === 'ai' && <div className="chat-msg__avatar">AI</div>}
      <div className="chat-msg__bubble">
        {msg.text || (msg.streaming ? <span className="cursor-blink">▋</span> : null)}
      </div>
    </div>
  )
}

// ── Transcribe bar ─────────────────────────────────────────────────────────────

function TranscribeBar({ port, appendMsg }: {
  port: number
  appendMsg: (m: Message) => void
}) {
  const [assetId, setAssetId]   = useState('')
  const [assets, setAssets]     = useState<{assetId: string; filename: string}[]>([])
  const [running, setRunning]   = useState(false)
  const [addSubs, setAddSubs]   = useState(true)

  useEffect(() => {
    fetch(`http://127.0.0.1:${port}/library/assets`)
      .then(r => r.json())
      .then((list: any[]) => {
        setAssets(list.filter(a => a.type === 'video' || a.type === 'audio'))
        if (list.length > 0) setAssetId(list[0].assetId)
      })
      .catch(() => {})
  }, [port])

  async function transcribe() {
    if (!assetId || running) return
    setRunning(true)
    appendMsg({ id: uid(), role: 'ai', text: '🎙 Transcribing audio with Whisper…' })
    try {
      const res = await fetch(`http://127.0.0.1:${port}/ai/transcribe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ assetId, model: 'small', create_text_clips: addSubs }),
      })
      const data = await res.json()
      const segs = data.segments ?? []
      appendMsg({
        id: uid(), role: 'ai',
        text: `✅ Transcription done — ${segs.length} segments${addSubs ? ', subtitle clips added to track.' : '.'}`,
      })
      if (addSubs) window.dispatchEvent(new CustomEvent('fade:tracks-changed'))
    } catch (e: any) {
      appendMsg({ id: uid(), role: 'error', text: `⚠ Transcribe failed: ${e.message}` })
    }
    setRunning(false)
  }

  if (assets.length === 0) return null

  return (
    <div className="transcribe-bar">
      <select className="transcribe-select" value={assetId} onChange={e => setAssetId(e.target.value)}>
        {assets.map(a => <option key={a.assetId} value={a.assetId}>{a.filename}</option>)}
      </select>
      <label className="transcribe-check">
        <input type="checkbox" checked={addSubs} onChange={e => setAddSubs(e.target.checked)} />
        Add subtitles
      </label>
      <button className="transcribe-btn" onClick={transcribe} disabled={running}>
        {running ? '…' : '🎙 Transcribe'}
      </button>
    </div>
  )
}

// ── AI Workspace root ──────────────────────────────────────────────────────────

export default function AIWorkspace() {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <div className="ai-ws">
      <Allotment>
        <Allotment.Pane minSize={collapsed ? 40 : 280} maxSize={collapsed ? 40 : 440} preferredSize={collapsed ? 40 : 340}>
          <ChatPanel collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} />
        </Allotment.Pane>
        <Allotment.Pane>
          <div className="ai-info-pane">
            <div className="ai-info-pane__inner">
              <div className="ai-info-icon">🤖</div>
              <h3>AI Director</h3>
              <p>Tell the AI what to do with your timeline in plain language.</p>
              <ul>
                <li>"Split the first clip at frame 90"</li>
                <li>"Add a blur effect to clip on track 2"</li>
                <li>"Transcribe the audio and add subtitles"</li>
                <li>"Fade in the first clip over 30 frames"</li>
                <li>"Undo that last action"</li>
              </ul>
            </div>
          </div>
        </Allotment.Pane>
      </Allotment>
    </div>
  )
}


