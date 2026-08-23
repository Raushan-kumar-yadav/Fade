/**
 * FloatingAIChat.tsx
 * A draggable, resizable floating AI chat window for the Video workspace.
 * Same chat logic as AIWorkspace but floating over the timeline.
 */
import { useState, useRef, useEffect, useCallback } from 'react'
import './FloatingAIChat.css'

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

function usePort(): number {
  const [port, setPort] = useState<number>((window as any).__FADE_PORT__ ?? 8000)
  useEffect(() => {
    const h = (e: Event) => setPort((e as CustomEvent<number>).detail)
    window.addEventListener('fade:port', h, { once: true })
    return () => window.removeEventListener('fade:port', h)
  }, [])
  return port
}

// ── Message Bubble ─────────────────────────────────────────────────────────────

function Bubble({ msg }: { msg: Message }) {
  if (msg.role === 'tool_call') {
    return (
      <div className="fchat-tool fchat-tool--call">
        <span className="fchat-tool__icon">⚙</span>
        <div>
          <div className="fchat-tool__name">{msg.toolName}</div>
          {msg.toolArgs && Object.keys(msg.toolArgs).length > 0 && (
            <pre className="fchat-tool__args">{JSON.stringify(msg.toolArgs, null, 2)}</pre>
          )}
        </div>
      </div>
    )
  }
  if (msg.role === 'tool_result') {
    const preview = msg.text.length > 160 ? msg.text.slice(0, 160) + '…' : msg.text
    return (
      <div className="fchat-tool fchat-tool--result">
        <span className="fchat-tool__icon">✓</span>
        <div>
          <div className="fchat-tool__name">{msg.toolName} done</div>
          <div className="fchat-tool__summary">{preview}</div>
        </div>
      </div>
    )
  }
  return (
    <div className={`fchat-msg fchat-msg--${msg.role === 'error' ? 'error' : msg.role}`}>
      {msg.role === 'ai' && <div className="fchat-msg__avatar">AI</div>}
      <div className="fchat-msg__bubble">
        {msg.text || (msg.streaming ? <span className="fchat-cursor">▋</span> : null)}
      </div>
    </div>
  )
}

// ── SelectedClipBadge ─────────────────────────────────────────────────────────

function SelectedClipBadge({ port }: { port: number }) {
  const [clip, setClip] = useState<{ clipId: string; type: string; trackIndex: number } | null>(null)

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail
      setClip(detail?.clipId ? detail : null)
    }
    window.addEventListener('fade:clip-selected', handler)
    return () => window.removeEventListener('fade:clip-selected', handler)
  }, [])

  if (!clip) return null
  return (
    <div className="fchat-clip-badge">
      <span className="fchat-clip-badge__dot" />
      <span>Clip on track {clip.trackIndex} selected — AI can apply effects</span>
    </div>
  )
}

// ── Main FloatingAIChat ───────────────────────────────────────────────────────

interface Props {
  onClose: () => void
}

export default function FloatingAIChat({ onClose }: Props) {
  const port = usePort()
  const [messages, setMessages] = useState<Message[]>([
    { id: uid(), role: 'ai', text: "Hi! I'm your AI Editor. Select a clip on the timeline, then ask me to apply effects, transforms, or anything else." },
  ])
  const [input, setInput]     = useState('')
  const [busy, setBusy]       = useState(false)
  const bottomRef             = useRef<HTMLDivElement>(null)
  const abortRef              = useRef<AbortController | null>(null)
  const historyRef            = useRef<{ role: string; text: string }[]>([])

  // Drag state
  const [pos, setPos]         = useState({ x: window.innerWidth - 420, y: 80 })
  const dragRef               = useRef<{ startX: number; startY: number; ox: number; oy: number } | null>(null)

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
      copy[copy.length - 1] = { ...copy[copy.length - 1], ...patch }
      return copy
    })
  }, [])

  async function send() {
    const text = input.trim()
    if (!text || busy) return
    setInput('')
    setBusy(true)

    appendMsg({ id: uid(), role: 'user', text })
    historyRef.current = [...historyRef.current, { role: 'user', text }]

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
        for (const line of decoder.decode(value).split('\n')) {
          if (!line.startsWith('data: ')) continue
          try {
            const evt = JSON.parse(line.slice(6))
            if (evt.type === 'token') {
              aiText += evt.content
              patchLast({ text: aiText, streaming: true })
              scrollBottom()
            } else if (evt.type === 'tool_call') {
              appendMsg({ id: uid(), role: 'tool_call', text: '', toolName: evt.name, toolArgs: evt.args })
            } else if (evt.type === 'tool_result') {
              appendMsg({ id: uid(), role: 'tool_result', text: evt.content, toolName: evt.name })
              appendMsg({ id: uid(), role: 'ai', text: '', streaming: true })
              aiText = ''
              // Refresh effects panel after tool runs
              window.dispatchEvent(new CustomEvent('fade:effects-changed'))
            } else if (evt.type === 'done') {
              patchLast({ streaming: false })
              setMessages(prev => prev.filter((m, i) => i === 0 || m.text !== '' || m.role !== 'ai'))
            } else if (evt.type === 'error') {
              patchLast({ text: `⚠ ${evt.message}`, streaming: false, role: 'error' })
            }
          } catch { /* ignore */ }
        }
      }
    } catch (err: any) {
      if (err.name !== 'AbortError')
        patchLast({ text: `⚠ ${err.message}`, streaming: false, role: 'error' })
    }

    historyRef.current = [...historyRef.current, { role: 'ai', text: aiText }]
    setBusy(false)
  }

  // Drag handlers
  function onMouseDown(e: React.MouseEvent) {
    e.preventDefault()
    dragRef.current = { startX: e.clientX, startY: e.clientY, ox: pos.x, oy: pos.y }
    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return
      setPos({
        x: Math.max(0, Math.min(window.innerWidth  - 380, dragRef.current.ox + ev.clientX - dragRef.current.startX)),
        y: Math.max(0, Math.min(window.innerHeight - 60,  dragRef.current.oy + ev.clientY - dragRef.current.startY)),
      })
    }
    const onUp = () => {
      dragRef.current = null
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  return (
    <div className="fchat" style={{ left: pos.x, top: pos.y }}>
      {/* Header / drag handle */}
      <div className="fchat__header" onMouseDown={onMouseDown}>
        <span className="fchat__title">
          <span className="fchat__dot" />
          AI Editor
        </span>
        <button className="fchat__close" onClick={onClose} title="Close">✕</button>
      </div>

      <SelectedClipBadge port={port} />

      {/* Messages */}
      <div className="fchat__messages">
        {messages.map(m => <Bubble key={m.id} msg={m} />)}
        {busy && <div className="fchat-thinking"><span/><span/><span/></div>}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="fchat__input-row">
        <textarea
          className="fchat__textarea"
          placeholder="Ask AI to apply effects, trim, transform…"
          value={input}
          rows={2}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
          disabled={busy}
        />
        {busy
          ? <button className="fchat__send fchat__send--stop" onClick={() => { abortRef.current?.abort(); setBusy(false) }}>■</button>
          : <button className="fchat__send" onClick={send}>↑</button>
        }
      </div>
    </div>
  )
}
