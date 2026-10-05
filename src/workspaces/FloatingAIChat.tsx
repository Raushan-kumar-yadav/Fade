import { useState, useRef, useEffect, useCallback } from 'react'
import './FloatingAIChat.css'
import PlanWidget from './PlanWidget'

// Types

type MsgRole = 'ai' | 'user' | 'tool_call' | 'tool_result' | 'error' | 'skill_progress'
type Phase   = 'idle' | 'thinking' | 'responding' | 'tool' | 'skill' | 'checkpoint'

interface SkillStepState {
  order: number
  name: string
  tool: string
  status: 'pending' | 'running' | 'done' | 'failed'
  checkpoint?: string
}

interface Message {
  id: string
  role: MsgRole
  text: string
  toolName?: string
  toolArgs?: Record<string, unknown>
  toolStatus?: 'running' | 'done'
  streaming?: boolean
  // For skill_progress role:
  skillName?: string
  skillVersion?: string
  skillSteps?: SkillStepState[]
  skillDone?: boolean
  skillError?: string
}

interface AgentStatus {
  phase: Phase
  label: string
  tool?: string
}

const uid = () => Math.random().toString(36).slice(2, 9)

 
const _WELCOME_TEXTS: Record<string, string> = {
  video: "🎬 Hi! I'm your **Video Agent**. I can edit the timeline, place clips, add effects, transitions, text overlays, animations, and export your video. What would you like to create?",
  image: "🖼️ Hi! I'm your **Image Agent**. I can create and edit image compositions, add layers, apply filters, generate images, and adjust any visual element. What would you like to design?",
  audio: "🎵 Hi! I'm your **Audio Agent**. I can adjust volumes, generate voiceovers (TTS), transcribe speech, remove silence, and manage your audio tracks. How can I help?",
  pdf: "📄 Hi! I'm your **Doc Agent**. I can create PDF documents, add pages, populate them with content, and export reports. What document shall we build?",
  director: "🎯 Hi! I'm the **Director**. Give me a high-level brief — like 'make a social media campaign using these clips' — and I'll plan the work, create compositions for each platform, and dispatch tasks to the specialized agents. What's the goal?",
  home: "🤖 Hi! I'm your **AI Assistant**. I can help you search for content, answer questions about your project, and guide you to the right workspace. What do you need?",
  ai: "🤖 Hi! I'm your **AI Assistant**. How can I help you today?",
  export: "📦 Hi! I'm your **Export Agent**. I can configure export settings, start renders, and monitor export progress. What format do you need?",
}

function makeWelcome(agentId: string): Message {
  const text = _WELCOME_TEXTS[agentId] ?? _WELCOME_TEXTS.video
  return { id: 'welcome', role: 'ai', text }
}

const _storeMessages: Map<string, Message[]> = new Map()
const _storeHistory: Map<string, { role: string; text: string }[]> = new Map()
const _storeInput: Map<string, string> = new Map()

// Max conversation turns kept in memory  
const MAX_HISTORY = 10  // 5 user + 5 ai turns

function getStore(agentId: string) {
  if (!_storeMessages.has(agentId)) _storeMessages.set(agentId, [makeWelcome(agentId)])
  if (!_storeHistory.has(agentId)) _storeHistory.set(agentId, [])
  if (!_storeInput.has(agentId)) _storeInput.set(agentId, '')
 
  const h = _storeHistory.get(agentId)!
  if (h.length > MAX_HISTORY) _storeHistory.set(agentId, h.slice(-MAX_HISTORY))
  return {
    messages: _storeMessages.get(agentId)!,
    history:  _storeHistory.get(agentId)!,
    input:    _storeInput.get(agentId)!,
  }
}

// Tool icon map  

// Agent identity metadata  
const AGENT_META: Record<string, { name: string; emoji: string; color: string }> = {
  video: { name: 'Video Agent', emoji: '🎬', color: '#7c6fff' },
  image: { name: 'Image Agent', emoji: '🖼️',  color: '#ff6b9d' },
  audio: { name: 'Audio Agent', emoji: '🎵', color: '#00d4aa' },
  pdf: { name: 'Doc Agent', emoji: '📄', color: '#f59e0b' },
  director: { name: 'Director', emoji: '🎯', color: '#e879f9' },
  home: { name: 'AI Assistant', emoji: '🤖', color: '#6b7280' },
  ai: { name: 'AI Assistant', emoji: '🤖', color: '#6b7280' },
  export: { name: 'Export Agent', emoji: '📦', color: '#3b82f6' },
  global: { name: 'AI Director', emoji: '🤖', color: '#7c6fff' },
}

const TOOL_ICONS: Record<string, string> = {
  get_timeline_state: '\u{1F4CB}',
  get_library: '\u{1F4DA}',
  get_library_assets: '\u{1F4C2}',
  place_clip: '\u{1F3AC}',
  add_text_clip: '\u{1F524}',
  add_shape_clip: '\u{1F536}',
  split_clip: '\u2702\uFE0F',
  trim_clip: '\u2702\uFE0F',
  move_clip: '\u{1F4E6}',
  delete_clip: '\u{1F5D1}\uFE0F',
  add_transition: '\u{1F504}',
  add_transitions_between_all_clips: '\u{1F504}',
  apply_effect_to_clip: '\u2728',
  download_videos: '\u{1F4E5}',
  download_images: '\u{1F5BC}\uFE0F',
  schedule_download: '\u{1F4E5}',
  generate_image: '\u{1F3A8}',
  search_video_scenes: '\u{1F50D}',
  get_asset_context: '\u{1F4D6}',
  get_clip_context: '\u{1F4D6}',
  describe_clip: '\u{1F441}\uFE0F',
  describe_selected_clip: '\u{1F441}\uFE0F',
  get_timeline_context: '\u{1F4CB}',
  create_news_video: '\u{1F4F0}',
  create_webcomp: '\u{1F3A8}',
  generate_tts: '\u{1F5E3}\uFE0F',
  check_job_status: '\u{1F552}',
  animate_property: '\u{1F3AC}',
  apply_curve_preset: '\u{1F4C8}',
  search_news: '\u{1F4F0}',
  find_free_overlay_track: '\u{1F50D}',
  add_track: '\u2795',
  remove_silence: '\u{1F507}',
  generate_captions: '\u{1F4AC}',
  undo: '\u21A9\uFE0F',
  redo: '\u21AA\uFE0F',
  export_video: '\u{1F4E4}',
  stop_indexing: '\u{1F6D1}',
  set_clip_volume: '\u{1F50A}',
  mute_clip: '\u{1F507}',
  get_clip_volume: '\u{1F50A}',
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

 
function StatusBar({ status }: { status: AgentStatus }) {
  if (status.phase === 'idle') return null
  return (
    <div className={`fchat__status-bar fchat__status-bar--${status.phase}`}>
      <span className="fchat__status-spinner" />
      <span className="fchat__status-label">{status.label}</span>
    </div>
  )
}

// Skill Progress Card

const STEP_STATUS_ICON: Record<string, string> = {
  pending: '○',
  running: '⟳',
  done:    '✓',
  failed:  '✕',
}

function SkillProgressCard({ msg }: { msg: Message }) {
  const [open, setOpen] = useState(false)
  const steps = msg.skillSteps ?? []
  const total = steps.length
  const done  = steps.filter(s => s.status === 'done').length
  const pct   = total > 0 ? Math.round(done / total * 100) : 0
  const current = steps.find(s => s.status === 'running')
  const currentLabel = current ? `${current.order}. ${current.name.replace(/_/g, ' ')}` : ''
  const compType = msg.skillName?.includes('video') ? '🎬'
    : msg.skillName?.includes('social') || msg.skillName?.includes('post') ? '🖼'
    : msg.skillName?.includes('product') ? '📦' : '📚'

  return (
    <div className={`fchat__skill-card fchat__skill-card--dock ${msg.skillDone ? 'fchat__skill-card--done' : ''} ${msg.skillError ? 'fchat__skill-card--error' : ''}`}>
      {/* Header — click to expand/collapse */}
      <div className="fchat__skill-header fchat__skill-header--click" onClick={() => setOpen(v => !v)}>
        <span className="fchat__skill-icon">{compType}</span>
        <div className="fchat__skill-title">
          <span className="fchat__skill-name">{(msg.skillName ?? '').replace(/_/g, ' ')}</span>
          {msg.skillVersion && <span className="fchat__skill-version">v{msg.skillVersion}</span>}
          {!open && currentLabel && <span className="fchat__skill-current">{currentLabel}</span>}
        </div>
        <span className={`fchat__skill-state-badge ${
          msg.skillDone ? 'fchat__skill-state-badge--done'
          : msg.skillError ? 'fchat__skill-state-badge--error'
          : 'fchat__skill-state-badge--running'
        }`}>
          {msg.skillDone ? '✅ done' : msg.skillError ? '✕ failed' : '⟳ running'}
        </span>
        <span className="fchat__skill-chevron">{open ? '▼' : '▶'}</span>
      </div>

      {/* Progress bar */}
      {total > 0 && (
        <div className="fchat__skill-progress-row">
          <div className="fchat__skill-progress-bar">
            <div
              className={`fchat__skill-progress-fill ${msg.skillDone ? 'fchat__skill-progress-fill--done' : ''}`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <span className="fchat__skill-progress-label">{done}/{total}</span>
        </div>
      )}

      {/* Steps list (expanded only) */}
      {open && <div className="fchat__skill-steps">
        {steps.map(s => (
          <div
            key={s.order}
            className={`fchat__skill-step fchat__skill-step--${s.status}`}
          >
            <span className={`fchat__skill-step-icon ${
              s.status === 'running' ? 'fchat__skill-step-icon--spin' : ''
            }`}>
              {STEP_STATUS_ICON[s.status]}
            </span>
            <span className="fchat__skill-step-name">{s.name.replace(/_/g, ' ')}</span>
            <span className="fchat__skill-step-tool">{s.tool}</span>
            {s.checkpoint && s.status === 'done' && (
              <span className="fchat__skill-checkpoint">{s.checkpoint}</span>
            )}
          </div>
        ))}
      </div>}

      {/* Error */}
      {msg.skillError && (
        <div className="fchat__skill-error">✕ {msg.skillError}</div>
      )}
    </div>
  )
}

// Message Bubble

function Bubble({ msg }: { msg: Message }) {
  const [expanded, setExpanded] = useState(false)

  // Skill progress card
  if (msg.role === 'skill_progress') {
    return <SkillProgressCard msg={msg} />
  }

  if (msg.role === 'tool_call') {
    const icon = TOOL_ICONS[msg.toolName ?? ''] ?? '\u2699\uFE0F'
    const isDone = msg.toolStatus === 'done'
    const hasArgs = msg.toolArgs && Object.keys(msg.toolArgs).length > 0
    const argsStr = hasArgs ? JSON.stringify(msg.toolArgs, null, 2) : ''
    const MAX = 200
    const hasResult = isDone && msg.text
    const preview = hasResult && msg.text.length > MAX ? msg.text.slice(0, MAX) + '\u2026' : msg.text
    const truncated = hasResult && msg.text.length > MAX
    return (
      <div className={`fchat__tool-card ${isDone ? 'fchat__tool-card--done' : 'fchat__tool-card--running'}`}>
        <span className={`fchat__tool-icon ${isDone ? '' : 'fchat__tool-icon--spin'}`}>{icon}</span>
        <div className="fchat__tool-body">
          <div className="fchat__tool-name">
            {msg.toolName}
            {isDone && <span className="fchat__tool-done">{'\u2713'} done</span>}
          </div>
          {hasResult && (
            <div className="fchat__tool-summary">{expanded ? msg.text : preview}</div>
          )}
          {(truncated || (hasArgs && !isDone)) && (
            <button className="fchat__tool-expand" onClick={() => setExpanded(v => !v)}>
              {expanded ? '\u25BC less' : '\u25B6 ' + (truncated ? 'more' : 'args')}
            </button>
          )}
          {expanded && hasArgs && !hasResult && (
            <pre className="fchat__tool-args">{argsStr}</pre>
          )}
        </div>
        <span className={`fchat__tool-badge ${isDone ? 'fchat__tool-badge--done' : 'fchat__tool-badge--running'}`}>
          {isDone ? '\u2713' : 'RUN'}
        </span>
      </div>
    )
  }

  if (msg.role === 'tool_result') {
    return null
  }


  return (
    <div className={`fchat__msg fchat__msg--${msg.role === 'error' ? 'error' : msg.role}`}>
      {msg.role === 'ai' && (
        <div className={`fchat__avatar ${msg.streaming ? 'fchat__avatar--pulse' : ''}`}>AI</div>
      )}
      <div className="fchat__bubble">
        {msg.text
          ? msg.text
          : msg.streaming
            ? <span className="fchat__thinking"><span /><span /><span /></span>
            : null}
      </div>
    </div>
  )
}

// Main FloatingAIChat

interface Props { onClose: () => void; contained?: boolean; agentId?: string }

export default function FloatingAIChat({ onClose, contained = false, agentId = 'global' }: Props) {
  const port = usePort()

  const store = getStore(agentId)
  const [messages, setMessages] = useState<Message[]>(() => getStore(agentId).messages)
  const [input,    setInput]    = useState(() => getStore(agentId).input)
  const [busy,     setBusy]     = useState(false)
  const [status,   setStatus]   = useState<AgentStatus>({ phase: 'idle', label: '' })
  const [activePlanId, setActivePlanId] = useState<string | null>(null)
  // Skill run lives OUTSIDE the message stream so it never hijacks LLM output
  const [skillRun, setSkillRun] = useState<Message | null>(null)
  const patchSkill = useCallback((fn: (m: Message) => Message) => {
    setSkillRun(prev => (prev ? fn(prev) : prev))
  }, [])
 
  const inSkillPlan = useRef(false)

  // Widget position & size
  const [pos,  setPos]  = useState(() => contained ? { x: 20, y: 50 } : { x: window.innerWidth - 440, y: 72 })
  const [size, setSize] = useState({ w: 420, h: 520 })
  // Dropped asset chip
  const [droppedAsset, setDroppedAsset] = useState<{ assetId: string; filename: string; type: string } | null>(null)
  const [isDragOver, setIsDragOver] = useState(false)

  const bottomRef  = useRef<HTMLDivElement>(null)
  const abortRef   = useRef<AbortController | null>(null)
  const historyRef = useRef(getStore(agentId).history)
  const inputRef   = useRef<HTMLTextAreaElement>(null)
  const dragRef    = useRef<{ sx: number; sy: number; ox: number; oy: number } | null>(null)
  const resizeRef  = useRef<{ sx: number; sy: number; ow: number; oh: number } | null>(null)

  // Sync per-agent store
  useEffect(() => { _storeMessages.set(agentId, messages) }, [agentId, messages])
  useEffect(() => { _storeInput.set(agentId, input)       }, [agentId, input])

  const scrollBottom = useCallback(() => {
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 40)
  }, [])

  const appendMsg = useCallback((msg: Message) => {
    setMessages(prev => { const n = [...prev, msg]; return n })
    scrollBottom()
  }, [scrollBottom])

  const patchLast = useCallback((patch: Partial<Message>) => {
    setMessages(prev => {
      const copy = [...prev]
      copy[copy.length - 1] = { ...copy[copy.length - 1], ...patch }
      
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
    // Build message — append dropped asset context if any
    const assetCtx = droppedAsset
      ? `\n[Asset: ${droppedAsset.filename} | id:${droppedAsset.assetId}]`
      : ''
    const fullText = text + assetCtx
    const assetId  = droppedAsset?.assetId ?? null
    setDroppedAsset(null)
    setInput('')
    setSkillRun(null)
    inSkillPlan.current = false
    setBusy(true)
    setStatus({ phase: 'thinking', label: 'Thinking…' })

    appendMsg({ id: uid(), role: 'user', text: fullText })
    // Cap history at MAX_HISTORY before pushing the new message
    const cappedHistory = historyRef.current.slice(-MAX_HISTORY)
    historyRef.current = [...cappedHistory, { role: 'user', text: fullText }]
    _storeHistory.set(agentId, historyRef.current)

    const aiId = uid()
    appendMsg({ id: aiId, role: 'ai', text: '', streaming: true })
    let aiText = ''
    // ID of the AI bubble currently being streamed into
    let currentBubbleId = aiId
    let lastToolCardId = ''
    // Map of toolName 
    const toolCardIds = new Map<string, string>()
 
    let pendingAiBubbleId = ''

    abortRef.current = new AbortController()

    try {
      // Detect "continue" / "ok" / "proceed" — these should NOT carry full history
      // because the LLM would re-execute old tasks from the history.
      const isContinue = /^(continue|ok|proceed|yes|go|next|sure|do it|run it|execute)$/i.test(fullText.trim())
      // Keep only last 3 turns (6 msgs). For continue-type msgs: only last 1 AI reply for context.
      const historySlice = isContinue
        ? historyRef.current.slice(-2)   // just the last AI reply for context
        : historyRef.current.slice(-6)   // last 3 turns

      const res = await fetch(`http://127.0.0.1:${port}/ai/chat`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ message: fullText, history: historySlice, port, agent: agentId, asset_id: assetId }),
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
              // Label comes directly from backend
              setStatus({ phase: evt.phase as Phase, label: evt.label, tool: evt.tool })

            } else if (evt.type === 'skill_detected') {
              setStatus({ phase: 'skill', label: `📚 Skill: ${evt.skill} (${evt.steps} steps)…` })
              inSkillPlan.current = true
              setSkillRun({
                id: `skill-${aiId}`,
                role: 'skill_progress',
                text: '',
                skillName: evt.skill,
                skillVersion: evt.version,
                skillSteps: [],
                skillDone: false,
              })
              scrollBottom()

            } else if (evt.type === 'plan_created') {
              const plan = evt.plan
              // Mark that we're in a plan — critical for token routing
              inSkillPlan.current = true
              // Open the Plan Preview Widget
              if (plan?.plan_id) setActivePlanId(plan.plan_id)
              if (plan?.steps) {
                const steps: SkillStepState[] = (plan.steps as any[]).map((s: any) => ({
                  order: s.order ?? 0,
                  name: s.tool_name ?? `Step ${s.order}`,
                  tool: s.tool_name ?? '',
                  status: (s.status === 'done' ? 'done' : 'pending') as SkillStepState['status'],
                }))
                setSkillRun(prev => ({
                  ...(prev ?? { id: `skill-${aiId}`, role: 'skill_progress' as const, text: '',
                                skillName: evt.skill ?? 'auto_plan', skillDone: false }),
                  skillSteps: steps,
                }))
              }
              setStatus({ phase: 'skill', label: `📋 Plan ready — ${plan?.steps?.length ?? '?'} steps` })
              window.dispatchEvent(new CustomEvent('fade:plan-changed'))

            } else if (evt.type === 'step_start') {
              setStatus({ phase: 'skill', label: `[${evt.order}] ${evt.name} — ${evt.tool ?? ''}…` })
              patchSkill(m => {
                const steps = (m.skillSteps ?? []).map((s: SkillStepState) =>
                  s.order === evt.order ? { ...s, status: 'running' as const } : s
                )
                return { ...m, skillSteps: steps }
              })
              // Start a fresh AI bubble for this step's output
              const stepBubbleId = `${aiId}-step-${evt.order}`
              currentBubbleId = stepBubbleId
              aiText = ''
              appendMsg({ id: stepBubbleId, role: 'ai', text: '', streaming: true })
              scrollBottom()

            } else if (evt.type === 'step_done') {
              // Mark the current step's bubble as finished streaming
              setMessages(prev => prev.map(m =>
                m.id === currentBubbleId ? { ...m, streaming: false } : m
              ))
              // Remove any empty AI bubbles left over from this step
              setMessages(prev => prev.filter((m, i) => i === 0 || m.text !== '' || m.role !== 'ai'))
              patchSkill(m => {
                const steps = (m.skillSteps ?? []).map((s: SkillStepState) =>
                  s.order === evt.order
                    ? { ...s, status: 'done' as const, checkpoint: evt.checkpoint }
                    : s
                )
                return { ...m, skillSteps: steps }
              })
              if (evt.checkpoint) {
                setStatus({ phase: 'checkpoint', label: `🏁 Checkpoint: ${evt.checkpoint}` })
              }
              window.dispatchEvent(new CustomEvent('fade:plan-changed'))
              scrollBottom()

            } else if (evt.type === 'step_failed') {
              patchSkill(m => {
                const steps = (m.skillSteps ?? []).map((s: SkillStepState) =>
                  s.order === evt.order ? { ...s, status: 'failed' as const } : s
                )
                return { ...m, skillSteps: steps, skillError: evt.error ?? 'Step failed' }
              })
              window.dispatchEvent(new CustomEvent('fade:plan-changed'))
              setStatus({ phase: 'idle', label: '' })

            } else if (evt.type === 'skill_done') {
              inSkillPlan.current = false
              patchSkill(m => ({ ...m, skillDone: true }))
              window.dispatchEvent(new CustomEvent('fade:plan-changed'))
              setStatus({ phase: 'idle', label: '' })
              scrollBottom()

            } else if (evt.type === 'token') {
              // Lazily create AI bubble if we only have a pending ID (post-tool, pre-token)
              if (pendingAiBubbleId && pendingAiBubbleId === currentBubbleId) {
                appendMsg({ id: pendingAiBubbleId, role: 'ai', text: '', streaming: true })
                pendingAiBubbleId = ''
              }
              aiText += evt.content
              // Patch by ID so we always hit the right bubble regardless of position
              setMessages(prev => prev.map(m =>
                m.id === currentBubbleId ? { ...m, text: aiText, streaming: true } : m
              ))
              scrollBottom()

            } else if (evt.type === 'tool_call') {
              // Remove trailing empty AI bubble before showing tool card
              setMessages(prev => {
                const last = prev[prev.length - 1]
                if (last?.role === 'ai' && !last.text) return prev.slice(0, -1)
                return prev
              })
              // Track by name so parallel tool calls all get resolved
              const toolCardId = `tool-${evt.name}-${Date.now()}`
              toolCardIds.set(evt.name, toolCardId)
              appendMsg({ id: toolCardId, role: 'tool_call', text: '', toolName: evt.name, toolArgs: evt.args, toolStatus: 'running' })

            } else if (evt.type === 'tool_result') {
              // Update the matching tool_call card: running -> done
              const matchId = toolCardIds.get(evt.name) ?? lastToolCardId
              toolCardIds.delete(evt.name)
              setMessages(prev => prev.map(m =>
                m.id === matchId ? { ...m, text: evt.content, toolStatus: 'done' } : m
              ))
              // Don't eagerly create an AI bubble here — create it lazily on first token
              // so parallel tool calls don't produce ghost empty bubbles.
              // Just prepare the IDs; the token handler will create the bubble if needed.
              pendingAiBubbleId = uid()
              currentBubbleId = pendingAiBubbleId
              aiText = ''
              dispatchToolEvents(evt.name)
              // Export tool — dispatch overlay event
              if ((evt.name === 'export_video' || evt.name === 'set_integrity_registration') && typeof evt.content === 'string') {
                const mJob = evt.content.match(/EXPORT_JOB_ID:([\w-]+)/)
                if (mJob) window.dispatchEvent(new CustomEvent('fade:export-started', { detail: { jobId: mJob[1] } }))
                const mInt = evt.content.match(/INTEGRITY_ENABLED:([01])/)
                if (mInt) window.dispatchEvent(new CustomEvent('fade:integrity-toggle', { detail: { enabled: mInt[1] === '1' } }))
              }

            } else if (evt.type === 'done') {
              // Mark the current bubble as finished
              // Clear pending bubble id — if it was never materialized, the filter below drops it
              pendingAiBubbleId = ''
              setMessages(prev => prev.map(m =>
                m.id === currentBubbleId ? { ...m, streaming: false } : m
              ))
              // Remove any remaining empty AI bubbles (unfilled placeholders)
              setMessages(prev => prev.filter((m, i) => i === 0 || m.text !== '' || m.role !== 'ai'))

            } else if (evt.type === 'error') {
              patchLast({ text: `❌ ${evt.message}`, streaming: false, role: 'error' })
            }
          } catch { /* ignore parse errors */ }
        }
      }
    } catch (err: any) {
      if (err.name !== 'AbortError')
        patchLast({ text: `\u274C ${err.message}`, streaming: false, role: 'error' })
    }

    historyRef.current = [...historyRef.current, { role: 'ai', text: aiText }]
    _storeHistory.set(agentId, historyRef.current)
    setStatus({ phase: 'idle', label: '' })
    setBusy(false)
  }

  function stop() {
    // Tell the backend to stop the current skill/plan execution
    fetch(`http://127.0.0.1:${port}/ai/cancel`, { method: 'POST' }).catch(() => {})
    // Then abort the SSE stream
    abortRef.current?.abort()
    setStatus({ phase: 'idle', label: '' })
    setBusy(false)
  }

  // -- Drag to move ------------------------------------------------------------

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

  // -- Drag to resize (bottom-right handle) ------------------------------------

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
    status.phase === 'thinking'    ? 'fchat__input-wrap--thinking'  :
    status.phase === 'responding'  ? 'fchat__input-wrap--responding' :
    status.phase === 'tool'        ? 'fchat__input-wrap--tool'       :
    status.phase === 'skill'       ? 'fchat__input-wrap--tool'       :
    status.phase === 'checkpoint'  ? 'fchat__input-wrap--responding' : ''

  return (
    <div
      className={`fchat ${busy ? 'fchat--busy' : ''}${contained ? ' fchat--contained' : ''}`}
      style={{ left: pos.x, top: pos.y, width: size.w, height: size.h }}
    >
      {/* Header — drag to move */}
      <div className="fchat__header" onMouseDown={onHeaderMouseDown}>
        <span className="fchat__title">
          {/* Agent identity dot */}
          <span className="fchat__online-dot" />
          {AGENT_META[agentId]?.emoji ?? '🤖'} {AGENT_META[agentId]?.name ?? 'AI Director'}
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

      {/* Pinned dock — plan + skill execution. Collapsed by default, never blocks chat output. */}
      {(activePlanId || skillRun) && (
        <div className="fchat__dock">
          {activePlanId && (
            <PlanWidget
              port={port}
              onPlanChange={p => {
                if (!p || p.status === 'done' || p.status === 'failed') {
                  // Keep visible for 4s after done so user sees final state
                  setTimeout(() => setActivePlanId(null), 4000)
                }
              }}
            />
          )}
          {!activePlanId && skillRun && <SkillProgressCard msg={skillRun} />}
        </div>
      )}

      {/* Input */}
      <div className="fchat__input-row">
        {/* Dropped asset chip */}
        {droppedAsset && (
          <div className="fchat__drop-chip">
            <img
              src={`http://127.0.0.1:${port}/library/thumbnail/${droppedAsset.assetId}`}
              alt={droppedAsset.filename}
              className="fchat__drop-chip-thumb"
              onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
            />
            <span className="fchat__drop-chip-name">{droppedAsset.filename}</span>
            <span className="fchat__drop-chip-type">{droppedAsset.type}</span>
            <button
              className="fchat__drop-chip-remove"
              onClick={() => setDroppedAsset(null)}
              title="Remove"
            >×</button>
          </div>
        )}

        <div className="fchat__input-bottom">
          <div
            className={`fchat__input-wrap ${glowClass}${isDragOver ? ' fchat__input-wrap--drop' : ''}`}
            onDragOver={e => {
              const hasFadeAsset =
                e.dataTransfer.types.includes('application/fade-asset') ||
                e.dataTransfer.types.includes('application/fade-scene-hit')
              if (hasFadeAsset) { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; setIsDragOver(true) }
            }}
            onDragLeave={() => setIsDragOver(false)}
            onDrop={e => {
              e.preventDefault()
              setIsDragOver(false)
              const raw = e.dataTransfer.getData('application/fade-asset') ||
                          e.dataTransfer.getData('application/fade-scene-hit')
              if (!raw) return
              try {
                const asset = JSON.parse(raw)
                setDroppedAsset({
                  assetId:  asset.assetId  ?? asset.id ?? '',
                  filename: asset.filename ?? asset.name ?? 'asset',
                  type:     asset.type     ?? asset.contentType ?? 'media',
                })
                inputRef.current?.focus()
              } catch {}
            }}
          >
            {isDragOver && (
              <div className="fchat__drop-overlay">
                <span>Drop to attach asset</span>
              </div>
            )}
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
            : <button className="fchat__send" onClick={send} title="Send (Enter)">▶</button>
          }
        </div>
      </div>

      {/* Resize handle — bottom-right corner */}
      <div className="fchat__resize-handle" onMouseDown={onResizeMouseDown} />
    </div>
  )
}
