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

function getStore(agentId: string) {
  if (!_storeMessages.has(agentId)) _storeMessages.set(agentId, [makeWelcome(agentId)])
  if (!_storeHistory.has(agentId)) _storeHistory.set(agentId,  [])
  if (!_storeInput.has(agentId)) _storeInput.set(agentId, '')
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
  get_timeline_state: '??',
  get_library: '??',
  get_library_assets: '??',
  place_clip: '??',
  add_text_clip: '??',
  add_shape_clip: '??',
  split_clip: '??',
  trim_clip: '??',
  move_clip: '??',
  delete_clip: '???',
  add_transition: '??',
  add_transitions_between_all_clips: '??',
  apply_effect_to_clip: '?',
  download_videos: '??',
  download_images: '???',
  schedule_download: '?',
  generate_image: '??',
  search_video_scenes: '??',
  get_asset_context: '??',
  get_clip_context: '??',
  describe_clip: '??',
  describe_selected_clip: '??',
  get_timeline_context: '??',
  create_news_video: '??',
  create_webcomp: '??',
  generate_tts: '???',
  check_job_status: '??',
  animate_property: '??',
  apply_curve_preset: '??',
  search_news: '??',
  find_free_overlay_track: '???',
  add_track: '?',
  remove_silence: '??',
  generate_captions: '??',
  undo: '??',
  redo: '??',
  export_video: '??',
  stop_indexing: '??',
  set_clip_volume: '??',
  mute_clip: '??',
  get_clip_volume: '??',
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
      Clip on track {clip.trackIndex} � AI can apply effects
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
    const icon = TOOL_ICONS[msg.toolName ?? ''] ?? '??'
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
                {expanded ? '? hide args' : '? show args'}
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
    const icon = TOOL_ICONS[msg.toolName ?? ''] ?? '?'
    const MAX = 200
    const preview = msg.text.length > MAX ? msg.text.slice(0, MAX) + '�' : msg.text
    const truncated = msg.text.length > MAX
    return (
      <div className="fchat__tool-card fchat__tool-card--result">
        <span className="fchat__tool-icon">{icon}</span>
        <div className="fchat__tool-body">
          <div className="fchat__tool-name">{msg.toolName} <span className="fchat__tool-done">done</span></div>
          <div className="fchat__tool-summary">{expanded ? msg.text : preview}</div>
          {truncated && (
            <button className="fchat__tool-expand" onClick={() => setExpanded(v => !v)}>
              {expanded ? '? less' : '? more'}
            </button>
          )}
        </div>
        <span className="fchat__tool-badge fchat__tool-badge--done">?</span>
      </div>
    )
  }

  return (
    <div className={`fchat__msg fchat__msg--${msg.role === 'error' ? 'error' : msg.role}`}>
      {msg.role === 'ai' && (
        <div className={`fchat__avatar ${msg.streaming ? 'fchat__avatar--pulse' : ''}`}>AI</div>
      )}
      <div className="fchat__bubble">
        {msg.text || (msg.streaming ? <span className="fchat__cursor">?</span> : null)}
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
    setInput('')
    setSkillRun(null)
    inSkillPlan.current = false
    setBusy(true)
    setStatus({ phase: 'thinking', label: 'Thinking�' })

    appendMsg({ id: uid(), role: 'user', text })
    historyRef.current = [...historyRef.current, { role: 'user', text }]
    _storeHistory.set(agentId, historyRef.current)

    const aiId = uid()
    appendMsg({ id: aiId, role: 'ai', text: '', streaming: true })
    let aiText = ''
    // ID of the AI bubble currently being streamed into
    let currentBubbleId = aiId
    abortRef.current = new AbortController()

    try {
      const res = await fetch(`http://127.0.0.1:${port}/ai/chat`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ message: text, history: historyRef.current.slice(-20), port, agent: agentId }),
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
              aiText += evt.content
              // Patch by ID so we always hit the right bubble regardless of position
              setMessages(prev => prev.map(m =>
                m.id === currentBubbleId ? { ...m, text: aiText, streaming: true } : m
              ))
              scrollBottom()

            } else if (evt.type === 'tool_call') {
              setMessages(prev => {
                const last = prev[prev.length - 1]
                if (last?.role === 'ai' && !last.text) {
                  const n = prev.slice(0, -1); return n
                }
                return prev
              })
              appendMsg({ id: uid(), role: 'tool_call', text: '', toolName: evt.name, toolArgs: evt.args })

            } else if (evt.type === 'tool_result') {
              appendMsg({ id: uid(), role: 'tool_result', text: evt.content, toolName: evt.name })
              // Always open a new AI bubble after a tool result.
              // Subsequent tokens (reasoning / follow-up) need a target to stream into.
              const afterToolId = uid()
              currentBubbleId = afterToolId
              aiText = ''
              appendMsg({ id: afterToolId, role: 'ai', text: '', streaming: true })
              dispatchToolEvents(evt.name)
              // Export tool � dispatch overlay event
              if ((evt.name === 'export_video' || evt.name === 'set_integrity_registration') && typeof evt.content === 'string') {
                // Export job signal -> show ExportProgressOverlay
                const mJob = evt.content.match(/EXPORT_JOB_ID:([\w-]+)/)
                if (mJob) {
                  window.dispatchEvent(new CustomEvent('fade:export-started', { detail: { jobId: mJob[1] } }))
                }
                // Integrity toggle signal -> set checkbox in ExportWorkspace
                const mInt = evt.content.match(/INTEGRITY_ENABLED:([01])/)
                if (mInt) {
                  window.dispatchEvent(new CustomEvent('fade:integrity-toggle', { detail: { enabled: mInt[1] === '1' } }))
                }
              }

            } else if (evt.type === 'done') {
              // Mark the current bubble as finished
              setMessages(prev => prev.map(m =>
                m.id === currentBubbleId ? { ...m, streaming: false } : m
              ))
              // Remove any remaining empty AI bubbles (unfilled placeholders)
              setMessages(prev => prev.filter((m, i) => i === 0 || m.text !== '' || m.role !== 'ai'))

            } else if (evt.type === 'error') {
              patchLast({ text: `? ${evt.message}`, streaming: false, role: 'error' })
            }
          } catch { /* ignore parse errors */ }
        }
      }
    } catch (err: any) {
      if (err.name !== 'AbortError')
        patchLast({ text: `? ${err.message}`, streaming: false, role: 'error' })
    }

    historyRef.current = [...historyRef.current, { role: 'ai', text: aiText }]
    _storeHistory.set(agentId, historyRef.current)
    setStatus({ phase: 'idle', label: '' })
    setBusy(false)
  }

  function stop() {
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
        <button className="fchat__close" onClick={onClose} title="Close">?</button>
      </div>

      {/* ONE status indicator � shown only while busy, labels from backend */}
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
        <div className={`fchat__input-wrap ${glowClass}`}>
          <textarea
            ref={inputRef}
            className="fchat__input"
            placeholder={busy ? 'AI is working�' : 'Ask AI to edit, download media, create videos�'}
            value={input}
            rows={2}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
            disabled={busy}
          />
        </div>
        {busy
          ? <button className="fchat__send fchat__send--stop" onClick={stop} title="Stop">�</button>
          : <button className="fchat__send" onClick={send} title="Send (Enter)">?</button>
        }
      </div>

      {/* Resize handle � bottom-right corner */}
      <div className="fchat__resize-handle" onMouseDown={onResizeMouseDown} />
    </div>
  )
}
