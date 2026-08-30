 
import { useState, useRef, useEffect, useCallback } from 'react'
import './FloatingAIChat.css'

//   Types  

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

// Module-level persistent store  

const _WELCOME: Message = {
  id: 'welcome',
  role: 'ai',
  text: "Hi! I'm your AI Director. Select a clip on the timeline, then ask me to apply effects, download media, create news videos, or anything else.",
}

// These live outside React  
let _persistedMessages: Message[]   = [_WELCOME]
let _persistedHistory: {role: string; text: string}[] = []
let _persistedInput: string      = ''

// Tools that modify the TIMELINE
const TIMELINE_TOOLS = new Set([
  'split_clip','trim_clip','move_clip','delete_clip','add_text_clip',
  'add_transition','add_transitions_between_all_clips',
  'apply_effect_to_clip','patch_clip_effect','remove_effect',
  'set_effect_param','set_clip_param','undo','redo','place_clip',
  'create_news_video','create_webcomp','add_webcomp_to_timeline',
])

// Tools that modify the LIBRARY
const LIBRARY_TOOLS = new Set([
  'download_videos','download_images','generate_image','create_news_video',
])

//   Port hook  

function usePort(): number {
  const [port, setPort] = useState<number>((window as any).__FADE_PORT__ ?? 8000)
  useEffect(() => {
    const h = (e: Event) => setPort((e as CustomEvent<number>).detail)
    window.addEventListener('fade:port', h, { once: true })
    return () => window.removeEventListener('fade:port', h)
  }, [])
  return port
}

//   Selected clip badge  

function SelectedClipBadge() {
  const [clip, setClip] = useState<{ clipId: string; trackIndex: number } | null>(null)
  useEffect(() => {
    const h = (e: Event) => {
      const d = (e as CustomEvent).detail
      setClip(d?.clipId ? d : null)
    }
    window.addEventListener('fade:clip-selected', h)
    return () => window.removeEventListener('fade:clip-selected', h)
  }, [])
  if (!clip) return null
  return (
    <div className="fchat__clip-badge">
      <span className="fchat__clip-dot" />
      Clip on track {clip.trackIndex} — AI can apply effects
    </div>
  )
}

//   Message Bubble  

function Bubble({ msg }: { msg: Message }) {
  if (msg.role === 'tool_call') {
    return (
      <div className="fchat__tool-card fchat__tool-card--call">
        <span className="fchat__tool-icon">⚙</span>
        <div>
          <div className="fchat__tool-name">{msg.toolName}</div>
          {msg.toolArgs && Object.keys(msg.toolArgs).length > 0 && (
            <pre className="fchat__tool-args">{JSON.stringify(msg.toolArgs, null, 2)}</pre>
          )}
        </div>
      </div>
    )
  }
  if (msg.role === 'tool_result') {
    const preview = msg.text.length > 180 ? msg.text.slice(0, 180) + '…' : msg.text
    return (
      <div className="fchat__tool-card fchat__tool-card--result">
        <span className="fchat__tool-icon">✓</span>
        <div>
          <div className="fchat__tool-name">{msg.toolName} done</div>
          <div className="fchat__tool-summary">{preview}</div>
        </div>
      </div>
    )
  }
  return (
    <div className={`fchat__msg fchat__msg--${msg.role === 'error' ? 'error' : msg.role}`}>
      {msg.role === 'ai' && <div className="fchat__avatar">AI</div>}
      <div className="fchat__bubble">
        {msg.text || (msg.streaming ? <span className="fchat__cursor">▋</span> : null)}
      </div>
    </div>
  )
}

//   Main FloatingAIChat  

interface Props { onClose: () => void }

export default function FloatingAIChat({ onClose }: Props) {
  const port      = usePort()

  // Initialise from persistent store
  const [messages, setMessages] = useState<Message[]>(_persistedMessages)
  const [input, setInput] = useState(_persistedInput)
  const [busy, setBusy] = useState(false)

  const bottomRef  = useRef<HTMLDivElement>(null)
  const abortRef   = useRef<AbortController | null>(null)
  const historyRef = useRef(_persistedHistory)

  // Drag state
  const [pos, setPos] = useState({ x: window.innerWidth - 408, y: 72 })
  const dragRef = useRef<{ sx: number; sy: number; ox: number; oy: number } | null>(null)

  // Keep persistent store in sync
  useEffect(() => { _persistedMessages = messages }, [messages])
  useEffect(() => { _persistedInput    = input    }, [input])

  const scrollBottom = useCallback(() => {
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 40)
  }, [])

  const appendMsg = useCallback((msg: Message) => {
    setMessages(prev => { const n = [...prev, msg]; _persistedMessages = n; return n })
    scrollBottom()
  }, [scrollBottom])

  const patchLast = useCallback((patch: Partial<Message>) => {
    setMessages(prev => {
      const copy = [...prev]
      copy[copy.length - 1] = { ...copy[copy.length - 1], ...patch }
      _persistedMessages = copy
      return copy
    })
  }, [])

  // Dispatch UI refresh events based on which tool ran
  const dispatchToolEvents = useCallback((toolName: string) => {
    if (TIMELINE_TOOLS.has(toolName)) {
      window.dispatchEvent(new CustomEvent('fade:tracks-changed'))
    }
    if (LIBRARY_TOOLS.has(toolName)) {
      window.dispatchEvent(new CustomEvent('fade:library-changed'))
    }
    if (toolName.includes('effect')) {
      window.dispatchEvent(new CustomEvent('fade:effects-changed'))
    }
  }, [])

  async function send() {
    const text = input.trim()
    if (!text || busy) return
    setInput(''); _persistedInput = ''
    setBusy(true)

    appendMsg({ id: uid(), role: 'user', text })
    historyRef.current = [...historyRef.current, { role: 'user', text }]
    _persistedHistory = historyRef.current

    const aiId = uid()
    appendMsg({ id: aiId, role: 'ai', text: '', streaming: true })
    let aiText = ''
    abortRef.current = new AbortController()

    try {
      const res = await fetch(`http://127.0.0.1:${port}/ai/chat`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ message: text, history: historyRef.current.slice(-20), port }),
        signal:  abortRef.current.signal,
      })
      const reader  = res.body!.getReader()
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
         
              dispatchToolEvents(evt.name)
            } else if (evt.type === 'done') {
              patchLast({ streaming: false })
              setMessages(prev => {
                const f = prev.filter((m, i) => i === 0 || m.text !== '' || m.role !== 'ai')
                _persistedMessages = f; return f
              })
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
    _persistedHistory = historyRef.current
    setBusy(false)
  }

  // Drag
  function onHeaderMouseDown(e: React.MouseEvent) {
    e.preventDefault()
    dragRef.current = { sx: e.clientX, sy: e.clientY, ox: pos.x, oy: pos.y }
    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return
      setPos({
        x: Math.max(0, Math.min(window.innerWidth  - 390, dragRef.current.ox + ev.clientX - dragRef.current.sx)),
        y: Math.max(0, Math.min(window.innerHeight - 60,  dragRef.current.oy + ev.clientY - dragRef.current.sy)),
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
      {/* Header */}
      <div className="fchat__header" onMouseDown={onHeaderMouseDown}>
        <span className="fchat__title">
          <span className="fchat__status-dot" />
          AI Director
        </span>
        <button className="fchat__close" onClick={onClose} title="Close">✕</button>
      </div>

      <SelectedClipBadge />

      {/* Messages */}
      <div className="fchat__messages">
        {messages.map(m => <Bubble key={m.id} msg={m} />)}
        {busy && (
          <div className="fchat__thinking">
            <span/><span/><span/>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="fchat__input-row">
        <div className="fchat__input-wrap">
          <textarea
            className="fchat__input"
            placeholder="Ask AI to apply effects, create videos, download media…"
            value={input}
            rows={2}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
            disabled={busy}
          />
        </div>
        {busy
          ? <button className="fchat__send fchat__send--stop" onClick={() => { abortRef.current?.abort(); setBusy(false) }}>■</button>
          : <button className="fchat__send" onClick={send}>↑</button>
        }
      </div>
    </div>
  )
}
