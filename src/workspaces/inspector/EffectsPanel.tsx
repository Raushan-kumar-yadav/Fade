import { useState, useEffect, useCallback, useRef } from 'react'
import { effectsApi, type EffectInfo } from '../../api/toolsApi'
import { useSelection } from '../../context/selectionContext'
import './EffectsPanel.css'

interface CatalogEntry {
  type: string; name: string; icon: string; category: string; desc: string;
}

const FALLBACK_CATALOG: CatalogEntry[] = [
  { type: 'blur',                name: 'Blur',               icon: '◈', category: 'Stylize',   desc: 'Gaussian blur' },
  { type: 'brightness_contrast', name: 'Brightness/Contrast',icon: '◑', category: 'Color',     desc: 'Adjust luminance' },
  { type: 'hsl',                 name: 'HSL',                icon: '◐', category: 'Color',     desc: 'Hue / Sat / Light' },
  { type: 'color_grade',         name: 'Color Grade',        icon: '◧', category: 'Color',     desc: 'Temperature & tint' },
  { type: 'sharpen',             name: 'Sharpen',            icon: '◇', category: 'Stylize',   desc: 'Unsharp mask' },
  { type: 'vignette',            name: 'Vignette',           icon: '◉', category: 'Cinematic', desc: 'Dark edge falloff' },
  { type: 'chroma_key',          name: 'Chroma Key',         icon: '◫', category: 'Keying',    desc: 'Green-screen removal' },
]

function EffectCard({ entry, onApply, onDragStart }: {
  entry: CatalogEntry
  onApply: (type: string) => void
  onDragStart: (type: string) => void
}) {
  return (
    <div
      className="efx-card"
      draggable
      onDragStart={() => onDragStart(entry.type)}
      onDoubleClick={() => onApply(entry.type)}
      title={`Double-click or drag onto clip to apply\n${entry.desc}`}
    >
      <span className="efx-card__icon">{entry.icon}</span>
      <div className="efx-card__info">
        <div className="efx-card__name">{entry.name}</div>
        <div className="efx-card__desc">{entry.desc}</div>
      </div>
      <button className="efx-card__add" onClick={() => onApply(entry.type)} title="Apply to selected clip">+</button>
    </div>
  )
}

function ParamSlider({ label, value, min, max, onChange }: {
  label: string; value: number; min: number; max: number
  onChange: (v: number) => void
}) {
  const [local, setLocal] = useState(value)
  useEffect(() => setLocal(value), [value])
  const pct = ((local - min) / (max - min)) * 100

  return (
    <div className="efx-param">
      <label className="efx-param__label">{label.replace(/_/g, ' ')}</label>
      <div className="efx-param__track">
        <div className="efx-param__fill" style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
        <input
          type="range" min={min} max={max} step={(max - min) / 400}
          value={local}
          className="efx-param__slider"
          onChange={e => setLocal(parseFloat(e.target.value))}
          onMouseUp={e => onChange(parseFloat((e.target as HTMLInputElement).value))}
        />
      </div>
      <span className="efx-param__val">{local.toFixed(2)}</span>
    </div>
  )
}

function AppliedEffect({ eff, clipId, onRefresh }: {
  eff: EffectInfo; clipId: string; onRefresh: () => void
}) {
  const [open, setOpen] = useState(true)

  const patch = useCallback(async (body: { enabled?: boolean; params?: Record<string, number> }) => {
    await effectsApi.patch(clipId, eff.effectId, body)
    onRefresh()
  }, [clipId, eff.effectId, onRefresh])

  return (
    <div className={`efx-applied${eff.enabled ? '' : ' efx-applied--disabled'}`}>
      <div className="efx-applied__header">
        <input
          type="checkbox" checked={eff.enabled}
          onChange={() => patch({ enabled: !eff.enabled })}
          className="efx-applied__check"
        />
        <span className="efx-applied__name" onClick={() => setOpen(o => !o)}>
          {open ? '▾' : '▸'} {eff.name}
        </span>
        <button className="efx-applied__del" onClick={async () => {
          await effectsApi.remove(clipId, eff.effectId)
          onRefresh()
        }}>✕</button>
      </div>
      {open && (
        <div className="efx-applied__params">
          {Object.entries(eff.params).map(([key, [val, min, max]]) => (
            <ParamSlider
              key={key}
              label={key}
              value={val}
              min={min}
              max={max}
              onChange={v => patch({ params: { [key]: v } })}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export default function EffectsPanel() {
  const { selected } = useSelection()
  const clipId = selected?.clipId ?? null

  const [catalog,  setCatalog]  = useState<CatalogEntry[]>(FALLBACK_CATALOG)
  const [applied,  setApplied]  = useState<EffectInfo[]>([])
  const [search,   setSearch]   = useState('')
  const [category, setCategory] = useState('All')
  const [dragging, setDragging] = useState<string | null>(null)
  const [dropping, setDropping] = useState(false)

  const dragTypeRef = useRef<string | null>(null)

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

  async function applyEffect(effectType: string) {
    if (!clipId) return
    await effectsApi.add(clipId, effectType)
    loadApplied()
  }

  const categories = ['All', ...Array.from(new Set(catalog.map(e => e.category)))]

  const filtered = catalog.filter(e => {
    const matchCat = category === 'All' || e.category === category
    const matchSrc = e.name.toLowerCase().includes(search.toLowerCase())
    return matchCat && matchSrc
  })

  return (
    <div className="efx-panel">
      {/* Left: Effect Browser */}
      <div className="efx-browser">
        <div className="efx-browser__header">
          <span className="efx-browser__title">Effect Library</span>
        </div>
        <input
          className="efx-browser__search"
          placeholder="Search effects…"
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
              onDragStart={type => { dragTypeRef.current = type; setDragging(type) }}
            />
          ))}
        </div>
        <div className="efx-browser__hint">
          Double-click or drag onto a clip to apply
        </div>
      </div>

      {/* Right: Applied effects on selected clip */}
      <div
        className={`efx-applied-panel${dropping ? ' efx-applied-panel--drop' : ''}`}
        onDragOver={e => { e.preventDefault(); setDropping(true) }}
        onDragLeave={() => setDropping(false)}
        onDrop={async e => {
          e.preventDefault()
          setDropping(false)
          const type = dragTypeRef.current
          if (type) await applyEffect(type)
          dragTypeRef.current = null
          setDragging(null)
        }}
      >
        <div className="efx-applied-panel__header">
          <span className="efx-applied-panel__title">
            {clipId ? `Applied Effects` : 'No Clip Selected'}
          </span>
          {applied.length > 0 && (
            <span className="efx-applied-panel__count">{applied.length}</span>
          )}
        </div>

        {!clipId && (
          <div className="efx-empty">
            <div className="efx-empty__icon">◈</div>
            <div>Select a clip on the timeline<br/>to apply and edit effects</div>
          </div>
        )}

        {clipId && applied.length === 0 && (
          <div className="efx-empty">
            <div className="efx-empty__icon">◈</div>
            <div>Drop an effect here or<br/>double-click one from the library</div>
          </div>
        )}

        {clipId && applied.map(eff => (
          <AppliedEffect key={eff.effectId} eff={eff} clipId={clipId} onRefresh={loadApplied} />
        ))}
      </div>
    </div>
  )
}
