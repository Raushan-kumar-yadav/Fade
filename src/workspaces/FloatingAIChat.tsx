import { useState, useRef, useEffect, useCallback } from 'react'
import './FloatingAIChat.css'

// Types

type MsgRole = 'ai' | 'user' | 'tool_call' | 'tool_result' | 'error'
type Phase   = 'idle' | 'thinking' | 'responding' | 'tool'

interface Message {
  id: string
  role: MsgRole
  text: string
  toolName?: string
  toolArgs?: Record<string, unknown>
  streaming?: boolean
}

interface AgentStatus {
  phase: Phase
  label: string
  tool?: string
}

const uid = () => Math.random().toString(36).slice(2, 9)

// Persistent module-level store  

const _WELCOME: Message = {
  id: 'welcome',
  role: 'ai',
  text: "Hi! I'm your AI Director. Ask me to apply effects, download media, create news videos, animate clips, or anything else.",
}

let _persistedMessages: Message[]                       = [_WELCOME]
let _persistedHistory: { role: string; text: string }[] = []
let _persistedInput: string                             = ''

// Tool icon map  

const TOOL_ICONS: Record<string, string> = {
  get_timeline_state: '🎬',
  get_library: '📚',
  get_library_assets: '📚',
  place_clip: '📌',
  add_text_clip: '✍️',
  add_shape_clip: '🔷',
  split_clip: '✂️',
  trim_clip: '✂️',
  move_clip: '↔️',
  delete_clip: '🗑️',
  add_transition: '🌊',
  add_transitions_between_all_clips: '🌊',
  apply_effect_to_clip: '✨',
  download_videos: '⬇️',
  download_images: '🖼️',
  schedule_download: '⏳',
  generate_image: '🎨',
  search_video_scenes: '🔍',
  get_asset_context: '🔍',
  get_clip_context: '🔍',
  describe_clip: '🔍',
  describe_selected_clip: '🔍',
  get_timeline_context: '📋',
  create_news_video: '📰',
  create_webcomp: '🌐',
  generate_tts: '🎙️',
  check_job_status: '⏱️',
  animate_property: '🎭',
  apply_curve_preset: '📈',
  search_news: '📡',
  find_free_overlay_track: '🎞️',
  add_track: '➕',
  remove_silence: '🔇',
  generate_captions: '💬',
  undo: '↩️',
  redo: '↪️',
  export_video: '📤',
  stop_indexing: '⏹️',
  set_clip_volume: '🔉',
  mute_clip: '🔇',
  get_clip_volume: '🔊',
}

const TIMELINE_TOOLS = new Set([
  'split_clip','trim_clip','move_clip','delete_clip','add_text_clip',
  'add_transition','add_transitions_between_all_clips',
  'apply_effect_to_clip','patch_clip_effect','remove_effect',
  'set_effect_param','set_clip_param','undo','redo','place_clip',
  'create_news_video','create_webcomp','add_webcomp_to_timeline',
])
const LIBRARY_TOOLS = new Set([
  'download_videos','download_images','generate_image','create_news_video',
])

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

// Selected clip badge

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

// Single status bar — the ONLY status indicator in the whole widget

function StatusBar({ status }: { status: AgentStatus }) {
  if (status.phase === 'idle') return null
  return (
    <div className={`fchat__status-bar fchat__status-bar--${status.phase}`}>
      <span className="fchat__status-spinner" />
      <span className="fchat__status-label">{status.label}</span>
    </div>
  )
}

// Message Bubble

function Bubble({ msg }: { msg: Message }) {
  const [expanded, setExpanded] = useState(false)

  if (msg.role === 'tool_call') {
    const icon = TOOL_ICONS[msg.toolName ?? ''] ?? '⚙️'
    const hasArgs = msg.toolArgs && Object.keys(msg.toolArgs).length > 0
    const argsStr = hasArgs ? JSON.stringify(msg.toolArgs, null, 2) : ''
    return (
      <div className="fchat__tool-card fchat__tool-card--call">
        <span className="fchat__tool-icon fchat__tool-icon--spin">{icon}</span>
        <div className="fchat__tool-body">
          <div className="fchat__tool-name">{msg.toolName}</div>
          {hasArgs && (
            <>
              <button
                className="fchat__tool-expand"
                onClick={() => setExpanded(v => !v)}
              >
                {expanded ? '▲ hide args' : '▼ show args'}
              </button>
              {expanded && (
                <pre className="fchat__tool-args">{argsStr}</pre>
              )}
            </>
          )}
        </div>
        <span className="fchat__tool-badge fchat__tool-badge--running">running</span>
      </div>
    )
  }

  if (msg.role === 'tool_result') {
    const icon = TOOL_ICONS[msg.toolName ?? ''] ?? '✓'
    const MAX = 200
    const preview = msg.text.length > MAX ? msg.text.slice(0, MAX) + '…' : msg.text
    const truncated = msg.text.length > MAX
    return (
      <div className="fchat__tool-card fchat__tool-card--result">
        <span className="fchat__tool-icon">{icon}</span>
        <div className="fchat__tool-body">
          <div className="fchat__tool-name">{msg.toolName} <span className="fchat__tool-done">done</span></div>
          <div className="fchat__tool-summary">{expanded ? msg.text : preview}</div>
          {truncated && (
            <button className="fchat__tool-expand" onClick={() => setExpanded(v => !v)}>
              {expanded ? '▲ less' : '▼ more'}
            </button>
          )}
        </div>
        <span className="fchat__tool-badge fchat__tool-badge--done">✓</span>
      </div>
    )
  }

  return (
    <div className={`fchat__msg fchat__msg--${msg.role === 'error' ? 'error' : msg.role}`}>
      {msg.role === 'ai' && (
        <div className={`fchat__avatar ${msg.streaming ? 'fchat__avatar--pulse' : ''}`}>AI</div>
      )}
      <div className="fchat__bubble">
        {msg.text || (msg.streaming ? <span className="fchat__cursor">▋</span> : null)}
      </div>
    </div>
  )
}

// Main FloatingAIChat

interface Props { onClose: () => void }

export default function FloatingAIChat({ onClose }: Props) {
  const port = usePort()

  const [messages, setMessages] = useState<Message[]>(_persistedMessages)
  const [input,    setInput]    = useState(_persistedInput)
  const [busy,     setBusy]     = useState(false)
  const [status,   setStatus]   = useState<AgentStatus>({ phase: 'idle', label: '' })

  // Widget position & size
  const [pos,  setPos]  = useState({ x: window.innerWidth - 440, y: 72 })
  const [size, setSize] = useState({ w: 420, h: 520 })

  const bottomRef  = useRef<HTMLDivElement>(null)
  const abortRef   = useRef<AbortController | null>(null)
  const historyRef = useRef(_persistedHistory)
  const inputRef   = useRef<HTMLTextAreaElement>(null)
  const dragRef    = useRef<{ sx: number; sy: number; ox: number; oy: number } | null>(null)
  const resizeRef  = useRef<{ sx: number; sy: number; ow: number; oh: number } | null>(null)

  // Sync persistent store
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

  const dispatchToolEvents = useCallback((toolName: string) => {
    if (TIMELINE_TOOLS.has(toolName))
      window.dispatchEvent(new CustomEvent('fade:tracks-changed'))
    if (LIBRARY_TOOLS.has(toolName))
      window.dispatchEvent(new CustomEvent('fade:library-changed'))
    if (toolName.includes('effect'))
      window.dispatchEvent(new CustomEvent('fade:effects-changed'))
  }, [])

  async function send() {
    const text = input.trim()
    if (!text || busy) return
    setInput(''); _persistedInput = ''
    setBusy(true)
    setStatus({ phase: 'thinking', label: 'Thinking…' })

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

            if (evt.type === 'status') {
              // Label comes directly from backend — never hardcoded here
              setStatus({ phase: evt.phase as Phase, label: evt.label, tool: evt.tool })

            } else if (evt.type === 'token') {
              aiText += evt.content
              patchLast({ text: aiText, streaming: true })
              scrollBottom()

            } else if (evt.type === 'tool_call') {
              setMessages(prev => {
                const last = prev[prev.length - 1]
                if (last?.role === 'ai' && !last.text) {
                  const n = prev.slice(0, -1); _persistedMessages = n; return n
                }
                return prev
              })
              appendMsg({ id: uid(), role: 'tool_call', text: '', toolName: evt.name, toolArgs: evt.args })

            } else if (evt.type === 'tool_result') {
              appendMsg({ id: uid(), role: 'tool_result', text: evt.content, toolName: evt.name })
              appendMsg({ id: uid(), role: 'ai', text: '', streaming: true })
              aiText = ''
              dispatchToolEvents(evt.name)
              // Export tool — dispatch overlay event
              if (evt.name === 'export_video' && typeof evt.content === 'string') {
                const m = evt.content.match(/EXPORT_JOB_ID:([\w-]+)/)
                if (m) {
                  window.dispatchEvent(new CustomEvent('fade:export-started', { detail: { jobId: m[1] } }))
                }
              }

            } else if (evt.type === 'done') {
              patchLast({ streaming: false })
              setMessages(prev => {
                const f = prev.filter((m, i) => i === 0 || m.text !== '' || m.role !== 'ai')
                _persistedMessages = f; return f
              })

            } else if (evt.type === 'error') {
              patchLast({ text: `⚠ ${evt.message}`, streaming: false, role: 'error' })
            }
          } catch { /* ignore parse errors */ }
        }
      }
    } catch (err: any) {
      if (err.name !== 'AbortError')
        patchLast({ text: `⚠ ${err.message}`, streaming: false, role: 'error' })
    }

    historyRef.current = [...historyRef.current, { role: 'ai', text: aiText }]
    _persistedHistory = historyRef.current
    setStatus({ phase: 'idle', label: '' })
    setBusy(false)
  }

  function stop() {
    abortRef.current?.abort()
    setStatus({ phase: 'idle', label: '' })
    setBusy(false)
  }

  // ── Drag to move ────────────────────────────────────────────────────────────

  function onHeaderMouseDown(e: React.MouseEvent) {
    if ((e.target as HTMLElement).closest('.fchat__close')) return
    e.preventDefault()
    dragRef.current = { sx: e.clientX, sy: e.clientY, ox: pos.x, oy: pos.y }
    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return
      setPos({
        x: Math.max(0, Math.min(window.innerWidth  - size.w, dragRef.current.ox + ev.clientX - dragRef.current.sx)),
        y: Math.max(0, Math.min(window.innerHeight - 60,     dragRef.current.oy + ev.clientY - dragRef.current.sy)),
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

  // ── Drag to resize (bottom-right handle) ────────────────────────────────────

  function onResizeMouseDown(e: React.MouseEvent) {
    e.preventDefault()
    e.stopPropagation()
    resizeRef.current = { sx: e.clientX, sy: e.clientY, ow: size.w, oh: size.h }
    const onMove = (ev: MouseEvent) => {
      if (!resizeRef.current) return
      setSize({
        w: Math.max(320, Math.min(800, resizeRef.current.ow + ev.clientX - resizeRef.current.sx)),
        h: Math.max(300, Math.min(900, resizeRef.current.oh + ev.clientY - resizeRef.current.sy)),
      })
    }
    const onUp = () => {
      resizeRef.current = null
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  // Input glow state
  const glowClass =
    status.phase === 'thinking'   ? 'fchat__input-wrap--thinking'  :
    status.phase === 'responding' ? 'fchat__input-wrap--responding' :
    status.phase === 'tool'       ? 'fchat__input-wrap--tool'       : ''

  return (
    <div
      className={`fchat ${busy ? 'fchat--busy' : ''}`}
      style={{ left: pos.x, top: pos.y, width: size.w, height: size.h }}
    >
      {/* Header — drag to move */}
      <div className="fchat__header" onMouseDown={onHeaderMouseDown}>
        <span className="fchat__title">
          {/* Single static green online dot — no animation, no phase colour */}
          <span className="fchat__online-dot" />
          AI Director
        </span>
        <button className="fchat__close" onClick={onClose} title="Close">✕</button>
      </div>

      {/* ONE status indicator — shown only while busy, labels from backend */}
      <StatusBar status={status} />

      <SelectedClipBadge />

      {/* Messages */}
      <div className="fchat__messages">
        {messages.map(m => <Bubble key={m.id} msg={m} />)}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="fchat__input-row">
        <div className={`fchat__input-wrap ${glowClass}`}>
          <textarea
            ref={inputRef}
            className="fchat__input"
            placeholder={busy ? 'AI is working…' : 'Ask AI to edit, download media, create videos…'}
            value={input}
            rows={2}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
            disabled={busy}
          />
        </div>
        {busy
          ? <button className="fchat__send fchat__send--stop" onClick={stop} title="Stop">■</button>
          : <button className="fchat__send" onClick={send} title="Send (Enter)">↑</button>
        }
      </div>

      {/* Resize handle — bottom-right corner */}
      <div className="fchat__resize-handle" onMouseDown={onResizeMouseDown} />
    </div>
  )
}
