import { useState, useEffect, useCallback } from 'react'
import './PlanWidget.css'

// Types

interface PlanStep {
  step_id: string
  order: number
  description: string
  tool_name: string
  status: 'pending' | 'running' | 'done' | 'skipped' | 'failed'
  error?: string | null
}

interface Plan {
  plan_id: string
  goal: string
  status: 'planning' | 'executing' | 'paused' | 'done' | 'failed'
  agent_type: string
  progress: { total: number; done: number; percent: number; failed: number; running: number }
  steps: PlanStep[]
}

// Constants

const STATUS_ICON: Record<string, string> = {
  pending: '○',
  running: '⟳',
  done:    '✓',
  skipped: '⊘',
  failed:  '✗',
}

const STATUS_COLOR: Record<string, string> = {
  pending: 'rgba(255,255,255,0.25)',
  running: '#a5b4fc',
  done:    '#86efac',
  skipped: 'rgba(255,255,255,0.2)',
  failed:  '#fca5a5',
}

// API helpers

const API = 'http://127.0.0.1:8000/ai/plans'

async function fetchActivePlan(): Promise<Plan | null> {
  try {
    const r = await fetch(`${API}/active/current`)
    const d = await r.json()
    return d.plan ?? null
  } catch { return null }
}

async function apiSkip(stepId: string)  { await fetch(`${API}/steps/${stepId}/skip`, { method: 'POST' }) }
async function apiRetry(stepId: string) { await fetch(`${API}/steps/${stepId}/retry`, { method: 'POST' }) }
async function apiPause(planId: string) { await fetch(`${API}/${planId}/pause`, { method: 'POST' }) }
async function apiResume(planId: string){ await fetch(`${API}/${planId}/resume`, { method: 'POST' }) }
async function apiCancel(planId: string){ await fetch(`${API}/${planId}/cancel`, { method: 'POST' }) }
async function apiInsert(planId: string, afterOrder: number, description: string, toolName: string) {
  await fetch(`${API}/${planId}/steps/insert`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ after_order: afterOrder, description, tool_name: toolName }),
  })
}
async function apiEdit(stepId: string, description: string, toolName: string) {
  await fetch(`${API}/steps/${stepId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ description, tool_name: toolName }),
  })
}

// Step row

function StepRow({
  step, planId, onRefresh, isLast,
}: {
  step: PlanStep
  planId: string
  onRefresh: () => void
  isLast: boolean
}) {
  const [editing, setEditing]     = useState(false)
  const [editDesc, setEditDesc]   = useState(step.description)
  const [editTool, setEditTool]   = useState(step.tool_name)
  const [inserting, setInserting] = useState(false)
  const [newDesc, setNewDesc]     = useState('')
  const [newTool, setNewTool]     = useState('')

  const canEdit   = step.status === 'pending'
  const canSkip   = step.status === 'pending' || step.status === 'failed'
  const canRetry  = step.status === 'failed' || step.status === 'skipped' || step.status === 'done'

  const handleSaveEdit = async () => {
    await apiEdit(step.step_id, editDesc, editTool)
    setEditing(false)
    onRefresh()
  }

  const handleInsert = async () => {
    if (!newDesc.trim()) return
    await apiInsert(planId, step.order, newDesc, newTool)
    setInserting(false)
    setNewDesc('')
    setNewTool('')
    onRefresh()
  }

  return (
    <div className={`pw-step pw-step--${step.status}`}>
      {/* Connector line */}
      <div className="pw-step-connector">
        <div className="pw-step-dot" style={{ color: STATUS_COLOR[step.status] }}>
          <span className={`pw-step-icon ${step.status === 'running' ? 'pw-spin' : ''}`}>
            {STATUS_ICON[step.status]}
          </span>
        </div>
        {!isLast && <div className="pw-step-line" />}
      </div>

      <div className="pw-step-body">
        {/* Step main row */}
        {editing ? (
          <div className="pw-edit-form">
            <input
              className="pw-edit-input"
              value={editDesc}
              onChange={e => setEditDesc(e.target.value)}
              placeholder="Step description"
            />
            <input
              className="pw-edit-input pw-edit-input--tool"
              value={editTool}
              onChange={e => setEditTool(e.target.value)}
              placeholder="tool_name"
            />
            <div className="pw-edit-actions">
              <button className="pw-btn pw-btn--primary" onClick={handleSaveEdit}>Save</button>
              <button className="pw-btn" onClick={() => setEditing(false)}>Cancel</button>
            </div>
          </div>
        ) : (
          <div className="pw-step-content">
            <div className="pw-step-order">#{step.order}</div>
            <div className="pw-step-info">
              <div className="pw-step-desc">{step.description}</div>
              {step.tool_name && (
                <div className="pw-step-tool">{step.tool_name}</div>
              )}
              {step.error && (
                <div className="pw-step-error">✗ {step.error}</div>
              )}
            </div>
            <div className="pw-step-actions">
              {canEdit && (
                <button className="pw-action" title="Edit step" onClick={() => setEditing(true)}>✏</button>
              )}
              {canSkip && (
                <button className="pw-action pw-action--warn" title="Skip step"
                  onClick={async () => { await apiSkip(step.step_id); onRefresh() }}>⊘</button>
              )}
              {canRetry && (
                <button className="pw-action pw-action--ok" title="Retry step"
                  onClick={async () => { await apiRetry(step.step_id); onRefresh() }}>↺</button>
              )}
              <button className="pw-action pw-action--dim" title="Insert step after this"
                onClick={() => setInserting(v => !v)}>+</button>
            </div>
          </div>
        )}

        {/* Insert step form */}
        {inserting && (
          <div className="pw-insert-form">
            <div className="pw-insert-label">Insert after step #{step.order}</div>
            <input
              className="pw-edit-input"
              value={newDesc}
              onChange={e => setNewDesc(e.target.value)}
              placeholder="New step description..."
              autoFocus
            />
            <input
              className="pw-edit-input pw-edit-input--tool"
              value={newTool}
              onChange={e => setNewTool(e.target.value)}
              placeholder="tool_name (optional)"
            />
            <div className="pw-edit-actions">
              <button className="pw-btn pw-btn--primary" onClick={handleInsert}>Insert</button>
              <button className="pw-btn" onClick={() => setInserting(false)}>Cancel</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// Main Plan Widget

interface Props {
  port?: number
  onPlanChange?: (plan: Plan | null) => void
}

export default function PlanWidget({ port = 8000, onPlanChange }: Props) {
  const [plan, setPlan]         = useState<Plan | null>(null)
  const [loading, setLoading]   = useState(false)
  const [collapsed, setCollapsed] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    const p = await fetchActivePlan()
    setPlan(p)
    onPlanChange?.(p)
    setLoading(false)
  }, [onPlanChange])

  // Poll every 3s while plan is executing
  useEffect(() => {
    refresh()
    const interval = setInterval(() => {
      if (plan?.status === 'executing' || plan?.status === 'planning') refresh()
    }, 3000)
    return () => clearInterval(interval)
  }, [plan?.status])

  // Listen for plan events from chat window
  useEffect(() => {
    const handler = () => refresh()
    window.addEventListener('fade:plan-changed', handler)
    return () => window.removeEventListener('fade:plan-changed', handler)
  }, [refresh])

  if (!plan) return null

  const pct = plan.progress.percent
  const done = plan.progress.done
  const total = plan.progress.total

  return (
    <div className={`pw-panel ${plan.status === 'done' ? 'pw-panel--done' : ''} ${plan.status === 'paused' ? 'pw-panel--paused' : ''}`}>
      {/* Header */}
      <div className="pw-header" onClick={() => setCollapsed(v => !v)}>
        <div className="pw-header-left">
          <span className="pw-header-icon">📋</span>
          <div className="pw-header-info">
            <div className="pw-goal">{plan.goal.slice(0, 60)}{plan.goal.length > 60 ? '…' : ''}</div>
            <div className="pw-meta">
              <span className={`pw-status-dot pw-status-dot--${plan.status}`} />
              <span className="pw-status-label">{plan.status}</span>
              <span className="pw-divider">·</span>
              <span className="pw-count">{done}/{total} steps</span>
            </div>
          </div>
        </div>

        <div className="pw-header-right">
          {/* Plan controls */}
          {plan.status === 'executing' && (
            <button className="pw-ctrl pw-ctrl--pause" title="Pause plan"
              onClick={async e => { e.stopPropagation(); await apiPause(plan.plan_id); refresh() }}>
              ⏸
            </button>
          )}
          {plan.status === 'paused' && (
            <button className="pw-ctrl pw-ctrl--resume" title="Resume plan"
              onClick={async e => { e.stopPropagation(); await apiResume(plan.plan_id); refresh() }}>
              ▶
            </button>
          )}
          {plan.status !== 'done' && plan.status !== 'failed' && (
            <button className="pw-ctrl pw-ctrl--cancel" title="Cancel plan"
              onClick={async e => {
                e.stopPropagation()
                if (confirm('Cancel this plan?')) { await apiCancel(plan.plan_id); refresh() }
              }}>
              ✕
            </button>
          )}
          <button className="pw-ctrl pw-ctrl--refresh" title="Refresh" onClick={e => { e.stopPropagation(); refresh() }}>
            {loading ? '⟳' : '↻'}
          </button>
          <span className="pw-chevron">{collapsed ? '▶' : '▼'}</span>
        </div>
      </div>

      {/* Progress bar */}
      <div className="pw-progress-bar">
        <div
          className={`pw-progress-fill pw-progress-fill--${plan.status}`}
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* Steps */}
      {!collapsed && (
        <div className="pw-steps">
          {plan.steps.map((step, idx) => (
            <StepRow
              key={step.step_id}
              step={step}
              planId={plan.plan_id}
              onRefresh={refresh}
              isLast={idx === plan.steps.length - 1}
            />
          ))}
        </div>
      )}
    </div>
  )
}
