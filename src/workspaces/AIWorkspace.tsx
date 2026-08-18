import { useState, useRef } from 'react'
import { Allotment } from 'allotment'
import 'allotment/dist/style.css'
import './AIWorkspace.css'

interface Message {
  role: 'ai' | 'user'
  text: string
}

const INITIAL_MESSAGES: Message[] = [
  { role: 'ai', text: 'Hello! Upload or attach a video frame and I will analyze it for you.' },
  { role: 'user', text: 'Can you zoom in at the pause point around frame 120?' },
  { role: 'ai', text: "Sure! I'll add a zoom-in animation from frame 118 to 135 using Newton ease. Applying now..." },
]

interface ChatPanelProps {
  collapsed: boolean
  onToggle:  () => void
}

function ChatPanel({ collapsed, onToggle }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>(INITIAL_MESSAGES)
  const [input, setInput] = useState<string>('')
  const bottomRef = useRef<HTMLDivElement>(null)

  function send(): void {
    if (!input.trim()) return
    setMessages(m => [...m, { role: 'user', text: input }])
    setInput('')
    setTimeout(() => {
      setMessages(m => [...m, { role: 'ai', text: 'Processing your request and applying effects to the timeline...' }])
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, 800)
  }

  function handleKey(e: React.KeyboardEvent<HTMLTextAreaElement>): void {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  return (
    <div className={`chat-panel${collapsed ? ' chat-panel--collapsed' : ''}`}>
      <div className="chat-panel__header">
        {!collapsed && <span>AI Director</span>}
        <button className="chat-panel__toggle" onClick={onToggle} title={collapsed ? 'Expand' : 'Collapse'}>
          {collapsed ? '›' : '‹'}
        </button>
      </div>

      {!collapsed && (
        <>
          <div className="chat-panel__messages">
            {messages.map((m, i) => (
              <div key={i} className={`chat-msg chat-msg--${m.role}`}>
                {m.role === 'ai' && <div className="chat-msg__avatar">AI</div>}
                <div className="chat-msg__bubble">{m.text}</div>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>

          <div className="chat-panel__toolbar">
            <button className="chat-tool-btn" title="Attach frame">⊕</button>
            <button className="chat-tool-btn" title="Screenshot">◈</button>
            <button className="chat-tool-btn" title="Timeline">◉</button>
          </div>

          <div className="chat-panel__input-row">
            <div className="chat-input-wrap">
              <textarea
                className="chat-input"
                placeholder="Describe an effect or ask AI..."
                value={input}
                rows={2}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKey}
              />
            </div>
            <button className="chat-send" onClick={send}>↑</button>
          </div>
        </>
      )}
    </div>
  )
}

function VideoPort() {
  const [playing, setPlaying] = useState<boolean>(false)
  const [frame,   setFrame]   = useState<number>(0)
  const TOTAL = 300

  const timeStr = (f: number): string =>
    `${String(Math.floor(f / 30)).padStart(2, '0')}:${String(f % 30).padStart(2, '0')}`

  return (
    <div className="ai-videoport">
      <div className="ai-videoport__screen">
        <div className="ai-videoport__placeholder">
          <span>◈</span>
          <p>Drop video or click to import</p>
        </div>
      </div>

      <div className="ai-seeker">
        <span className="ai-seeker__time">{timeStr(frame)}</span>
        <input type="range" min={0} max={TOTAL} value={frame}
          className="ai-seeker__track"
          onChange={e => setFrame(Number(e.target.value))} />
        <span className="ai-seeker__time">{timeStr(TOTAL)}</span>
      </div>

      <div className="ai-controls">
        <button className="ctrl-btn" onClick={() => setFrame(f => Math.max(0, f - 1))}>⏮</button>
        <button className="ctrl-btn" onClick={() => setFrame(f => Math.max(0, f - 10))}>⏪</button>
        <button className="ctrl-btn ctrl-btn--play" onClick={() => setPlaying(p => !p)}>
          {playing ? '⏸' : '▶'}
        </button>
        <button className="ctrl-btn" onClick={() => setFrame(f => Math.min(TOTAL, f + 10))}>⏩</button>
        <button className="ctrl-btn" onClick={() => setFrame(f => Math.min(TOTAL, f + 1))}>⏭</button>
        <div className="ctrl-sep" />
        <button className="ctrl-btn">📌 Attach Frame</button>
      </div>
    </div>
  )
}

export default function AIWorkspace() {
  const [collapsed, setCollapsed] = useState<boolean>(false)

  return (
    <div className="ai-ws">
      <Allotment>
        <Allotment.Pane minSize={collapsed ? 40 : 260} maxSize={collapsed ? 40 : 420} preferredSize={collapsed ? 40 : 320}>
          <ChatPanel collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} />
        </Allotment.Pane>
        <Allotment.Pane>
          <VideoPort />
        </Allotment.Pane>
      </Allotment>
    </div>
  )
}
