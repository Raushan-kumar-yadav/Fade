/**
 * EffectsPanel.tsx
 * Left: Effect browser with drag support (draggable onto timeline clips or the applied-effects panel).
 * Right: Applied effects on the selected clip with full param editing:
 *   - FloatSlider / ToggleBool / IntSlider → custom range slider
 *   - Vec2Input → two linked sliders (x, y)
 *   - Vec4Input → RGBA color picker + individual sliders
 */
import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { effectsApi, type EffectInfo, type EffectParamDef } from '../../api/toolsApi'
import { useSelection } from '../../context/selectionContext'
import './EffectsPanel.css'

// ── Types ────────────────────────────────────────────────────────────────────

interface CatalogEntry {
  type: string; name: string; icon: string; category: string; desc: string;
}

const FALLBACK_CATALOG: CatalogEntry[] = [
  { type: 'blur',                name: 'Blur',               icon: '⬡', category: 'Stylize',   desc: 'Gaussian blur' },
  { type: 'brightness_contrast', name: 'Brightness/Contrast',icon: '◑', category: 'Color',     desc: 'Adjust luminance & contrast' },
  { type: 'hsl',                 name: 'HSL',                icon: '◐', category: 'Color',     desc: 'Hue / Saturation / Lightness' },
  { type: 'color_grade',         name: 'Color Grade',        icon: '◧', category: 'Color',     desc: 'Temperature & tint' },
  { type: 'sharpen',             name: 'Sharpen',            icon: '◇', category: 'Stylize',   desc: 'Unsharp mask' },
  { type: 'vignette',            name: 'Vignette',           icon: '◉', category: 'Cinematic', desc: 'Dark edge falloff' },
  { type: 'chroma_key',          name: 'Chroma Key',         icon: '◫', category: 'Keying',    desc: 'Green-screen removal' },
]

// ── Param Controls ───────────────────────────────────────────────────────────

function ScalarSlider({ id, def, onChange }: {
  id: string; def: EffectParamDef
  onChange: (id: string, val: number) => void
}) {
  const min = Array.isArray(def.min) ? def.min[0] : def.min as number
  const max = Array.isArray(def.max) ? def.max[0] : def.max as number
  const val = Array.isArray(def.value) ? def.value[0] : def.value as number
  const [local, setLocal] = useState(val)
  useEffect(() => setLocal(Array.isArray(def.value) ? def.value[0] : def.value as number), [def.value])
  const pct = ((local - min) / (max - min)) * 100

  return (
    <div className="efx-param">
      <label className="efx-param__label">{def.displayName}</label>
      <div className="efx-param__track">
        <div className="efx-param__fill" style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
        <input
          type="range" min={min} max={max} step={(max - min) / 500}
          value={local}
          className="efx-param__slider"
          onChange={e => setLocal(parseFloat(e.target.value))}
          onMouseUp={e => onChange(id, parseFloat((e.target as HTMLInputElement).value))}
          onTouchEnd={e => onChange(id, parseFloat((e.target as HTMLInputElement).value))}
        />
      </div>
      <span className="efx-param__val">{local.toFixed(3)}</span>
    </div>
  )
}

function ToggleParam({ id, def, onChange }: {
  id: string; def: EffectParamDef
  onChange: (id: string, val: number) => void
}) {
  const val = Array.isArray(def.value) ? def.value[0] : def.value as number
  return (
    <div className="efx-param efx-param--toggle">
      <label className="efx-param__label">{def.displayName}</label>
      <button
        className={`efx-toggle ${val >= 0.5 ? 'efx-toggle--on' : ''}`}
        onClick={() => onChange(id, val >= 0.5 ? 0 : 1)}
      >
        {val >= 0.5 ? 'ON' : 'OFF'}
      </button>
    </div>
  )
}

function Vec2Param({ id, def, onChange }: {
  id: string; def: EffectParamDef
  onChange: (id: string, val: number[]) => void
}) {
  const vals = Array.isArray(def.value) ? def.value as number[] : [0, 0]
  const mins = Array.isArray(def.min) ? def.min as number[] : [def.min as number, def.min as number]
  const maxs = Array.isArray(def.max) ? def.max as number[] : [def.max as number, def.max as number]
  const [local, setLocal] = useState(vals)
  useEffect(() => setLocal(Array.isArray(def.value) ? def.value as number[] : [0, 0]), [def.value])

  const commit = (idx: number, v: number) => {
    const next = [...local]; next[idx] = v
    setLocal(next); onChange(id, next)
  }

  return (
    <div className="efx-param-group">
      <label className="efx-param-group__label">{def.displayName}</label>
      {['X', 'Y'].map((lbl, i) => {
        const pct = ((local[i] - mins[i]) / (maxs[i] - mins[i])) * 100
        return (
          <div key={lbl} className="efx-param">
            <label className="efx-param__label efx-param__label--sub">{lbl}</label>
            <div className="efx-param__track">
              <div className="efx-param__fill" style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
              <input type="range" min={mins[i]} max={maxs[i]} step={(maxs[i] - mins[i]) / 500}
                value={local[i]} className="efx-param__slider"
                onChange={e => { const n = [...local]; n[i] = parseFloat(e.target.value); setLocal(n) }}
                onMouseUp={e => commit(i, parseFloat((e.target as HTMLInputElement).value))}
              />
            </div>
            <span className="efx-param__val">{local[i].toFixed(2)}</span>
          </div>
        )
      })}
    </div>
  )
}

function Vec4Param({ id, def, onChange }: {
  id: string; def: EffectParamDef
  onChange: (id: string, val: number[]) => void
}) {
  const vals = Array.isArray(def.value) ? def.value as number[] : [1, 1, 1, 1]
  const [local, setLocal] = useState(vals)
  useEffect(() => setLocal(Array.isArray(def.value) ? def.value as number[] : [1, 1, 1, 1]), [def.value])

  const r8 = Math.round(local[0] * 255)
  const g8 = Math.round(local[1] * 255)
  const b8 = Math.round(local[2] * 255)
  const hex = `#${r8.toString(16).padStart(2,'0')}${g8.toString(16).padStart(2,'0')}${b8.toString(16).padStart(2,'0')}`

  const fromHex = (h: string) => {
    const r = parseInt(h.slice(1,3),16)/255
    const g = parseInt(h.slice(3,5),16)/255
    const b = parseInt(h.slice(5,7),16)/255
    return [r, g, b, local[3]]
  }

  return (
    <div className="efx-param-group">
      <label className="efx-param-group__label">{def.displayName}</label>
      <div className="efx-vec4">
        <input
          type="color"
          className="efx-vec4__swatch"
          value={hex}
          onChange={e => {
            const next = fromHex(e.target.value)
            setLocal(next)
          }}
          onBlur={e => onChange(id, fromHex(e.target.value))}
        />
        <span className="efx-vec4__hex">{hex.toUpperCase()}</span>
        {/* Alpha slider */}
        <div className="efx-param" style={{ flex: 1 }}>
          <label className="efx-param__label efx-param__label--sub">A</label>
          <div className="efx-param__track">
            <div className="efx-param__fill" style={{ width: `${local[3] * 100}%` }} />
            <input type="range" min={0} max={1} step={0.005}
              value={local[3]} className="efx-param__slider"
              onChange={e => { const next = [...local]; next[3] = parseFloat(e.target.value); setLocal(next) }}
              onMouseUp={e => { const next = [...local]; next[3] = parseFloat((e.target as HTMLInputElement).value); setLocal(next); onChange(id, next) }}
            />
          </div>
          <span className="efx-param__val">{local[3].toFixed(2)}</span>
        </div>
      </div>
    </div>
  )
}

function EffectParamControl({ id, def, onCommit }: {
  id: string; def: EffectParamDef
  onCommit: (id: string, val: number | number[]) => void
}) {
  switch (def.type) {
    case 'Vec4Input': return <Vec4Param id={id} def={def} onChange={onCommit} />
    case 'Vec2Input': return <Vec2Param id={id} def={def} onChange={onCommit} />
    case 'ToggleBool': return <ToggleParam id={id} def={def} onChange={onCommit} />
    default: return <ScalarSlider id={id} def={def} onChange={onCommit} />
  }
}

// ── Effect Card (browser) ────────────────────────────────────────────────────

function EffectCard({ entry, onApply, onDragStart }: {
  entry: CatalogEntry
  onApply: (type: string) => void
  onDragStart: (type: string, e: React.DragEvent) => void
}) {
  return (
    <div
      className="efx-card"
      draggable
      onDragStart={e => onDragStart(entry.type, e)}
      onDoubleClick={() => onApply(entry.type)}
      title={`Double-click or drag onto a clip\n${entry.desc}`}
    >
      <span className="efx-card__icon">{entry.icon}</span>
      <div className="efx-card__info">
        <div className="efx-card__name">{entry.name}</div>
        <div className="efx-card__desc">{entry.desc}</div>
      </div>
      <button
        className="efx-card__add"
        onClick={e => { e.stopPropagation(); onApply(entry.type) }}
        title="Apply to selected clip"
      >＋</button>
    </div>
  )
}

// ── Applied Effect Row ───────────────────────────────────────────────────────

function AppliedEffect({ eff, clipId, onRefresh }: {
  eff: EffectInfo; clipId: string; onRefresh: () => void
}) {
  const [open, setOpen] = useState(true)
  const [localEff, setLocalEff] = useState(eff)
  useEffect(() => setLocalEff(eff), [eff])

  const patch = useCallback(async (body: { enabled?: boolean; params?: Record<string, number | number[]> }) => {
    const updated = await effectsApi.patch(clipId, eff.effectId, body) as EffectInfo
    if (updated?.params) setLocalEff(updated)
    onRefresh()
  }, [clipId, eff.effectId, onRefresh])

  const paramEntries = Object.entries(localEff.params)

  return (
    <div className={`efx-applied${localEff.enabled ? '' : ' efx-applied--disabled'}`}>
      <div className="efx-applied__header">
        <input
          type="checkbox"
          checked={localEff.enabled}
          onChange={() => patch({ enabled: !localEff.enabled })}
          className="efx-applied__check"
          title={localEff.enabled ? 'Disable effect' : 'Enable effect'}
        />
        <span className="efx-applied__name" onClick={() => setOpen(o => !o)}>
          <span className="efx-applied__arrow">{open ? '▾' : '▸'}</span>
          {localEff.name}
        </span>
        <span className="efx-applied__type-badge">{localEff.type}</span>
        <button
          className="efx-applied__del"
          title="Remove effect"
          onClick={async () => { await effectsApi.remove(clipId, eff.effectId); onRefresh() }}
        >✕</button>
      </div>

      {open && (
        <div className="efx-applied__params">
          {paramEntries.length === 0 && (
            <div className="efx-applied__no-params">No parameters</div>
          )}
          {paramEntries.map(([pid, def]) => (
            <EffectParamControl
              key={pid}
              id={pid}
              def={def}
              onCommit={(id, val) => patch({ params: { [id]: val as any } })}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ── Main EffectsPanel ────────────────────────────────────────────────────────

export default function EffectsPanel() {
  const { selected } = useSelection()
  const clipId = selected?.clipId ?? null

  const [catalog,  setCatalog]  = useState<CatalogEntry[]>(FALLBACK_CATALOG)
  const [applied,  setApplied]  = useState<EffectInfo[]>([])
  const [search,   setSearch]   = useState('')
  const [category, setCategory] = useState('All')
  const [dropping, setDropping] = useState(false)

  const dragTypeRef = useRef<string | null>(null)

  // Load catalog from backend
  useEffect(() => {
    const port = (window as any).__FADE_PORT__ ?? 8000
    fetch(`http://127.0.0.1:${port}/effects/catalog`)
      .then(r => r.json())
      .then(d => { if (d.effects) setCatalog(d.effects) })
      .catch(() => {})
  }, [])

  const loadApplied = useCallback(async () => {
    if (!clipId) { setApplied([]); return }
    try {
      const r = await effectsApi.list(clipId)
      setApplied(r.effects ?? [])
    } catch { setApplied([]) }
  }, [clipId])

  useEffect(() => { loadApplied() }, [loadApplied])

  // Refresh when effect dropped on a clip from the timeline
  useEffect(() => {
    const handler = (e: Event) => {
      const targetId = (e as CustomEvent<string>).detail
      if (!targetId || targetId === clipId) loadApplied()
    }
    window.addEventListener('fade:effects-changed', handler)
    return () => window.removeEventListener('fade:effects-changed', handler)
  }, [clipId, loadApplied])

  async function applyEffect(effectType: string) {
    if (!clipId) return
    await effectsApi.add(clipId, effectType)
    loadApplied()
    window.dispatchEvent(new CustomEvent('fade:effects-changed', { detail: clipId }))
  }

  const categories = useMemo(
    () => ['All', ...Array.from(new Set(catalog.map(e => e.category)))],
    [catalog]
  )

  const filtered = useMemo(() => catalog.filter(e => {
    const matchCat = category === 'All' || e.category === category
    const matchSrc = e.name.toLowerCase().includes(search.toLowerCase()) ||
                     e.desc.toLowerCase().includes(search.toLowerCase())
    return matchCat && matchSrc
  }), [catalog, category, search])

  const handleDragStart = (type: string, e: React.DragEvent) => {
    dragTypeRef.current = type
    // MIME type used by TimelineClip to detect effect drags
    e.dataTransfer.setData('application/fade-effect', type)
    e.dataTransfer.effectAllowed = 'copy'
  }

  return (
    <div className="efx-panel">

      {/* ── Left: Effect Browser ── */}
      <div className="efx-browser">
        <div className="efx-browser__header">
          <span className="efx-browser__title">Effect Library</span>
          <span className="efx-browser__hint-icon" title="Drag onto a clip or double-click">⋮⋮</span>
        </div>

        <input
          className="efx-browser__search"
          placeholder="🔍 Search effects…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />

        <div className="efx-browser__cats">
          {categories.map(c => (
            <button
              key={c}
              className={`efx-cat${category === c ? ' efx-cat--active' : ''}`}
              onClick={() => setCategory(c)}
            >{c}</button>
          ))}
        </div>

        <div className="efx-browser__list">
          {filtered.map(e => (
            <EffectCard
              key={e.type}
              entry={e}
              onApply={applyEffect}
              onDragStart={handleDragStart}
            />
          ))}
          {filtered.length === 0 && (
            <div className="efx-browser__empty">No effects found</div>
          )}
        </div>

        <div className="efx-browser__footer">
          Drag onto timeline clip or double-click to apply
        </div>
      </div>

      {/* ── Right: Applied Effects ── */}
      <div
        className={`efx-applied-panel${dropping ? ' efx-applied-panel--drop' : ''}`}
        onDragOver={e => {
          if (e.dataTransfer.types.includes('application/fade-effect')) {
            e.preventDefault(); setDropping(true)
          }
        }}
        onDragLeave={() => setDropping(false)}
        onDrop={async e => {
          e.preventDefault(); setDropping(false)
          const type = e.dataTransfer.getData('application/fade-effect') || dragTypeRef.current
          if (type) await applyEffect(type)
          dragTypeRef.current = null
        }}
      >
        <div className="efx-applied-panel__header">
          <span className="efx-applied-panel__title">
            {clipId ? 'Applied Effects' : 'No Clip Selected'}
          </span>
          {applied.length > 0 && (
            <span className="efx-applied-panel__count">{applied.length}</span>
          )}
        </div>

        {!clipId && (
          <div className="efx-empty">
            <div className="efx-empty__icon">🎬</div>
            <div>Select a clip on the timeline<br/>to apply and edit effects</div>
          </div>
        )}

        {clipId && applied.length === 0 && !dropping && (
          <div className="efx-empty">
            <div className="efx-empty__icon">✦</div>
            <div>Drop an effect here or<br/>double-click one from the library</div>
          </div>
        )}

        {dropping && (
          <div className="efx-empty efx-empty--drop">
            <div className="efx-empty__icon">⊕</div>
            <div>Release to apply effect</div>
          </div>
        )}

        {clipId && applied.map(eff => (
          <AppliedEffect
            key={eff.effectId}
            eff={eff}
            clipId={clipId}
            onRefresh={loadApplied}
          />
        ))}
      </div>
    </div>
  )
}
