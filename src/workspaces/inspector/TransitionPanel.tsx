import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  transitionApi,
  type TransitionInfo,
  type TransitionCatalogEntry,
} from '../../api/toolsApi';
import './TransitionPanel.css';

// ── Types ─────────────────────────────────────────────────────────────────────

interface Props {
  /** If provided, show the editor for an existing transition */
  selected?: TransitionInfo | null;
  onSelect?: (tr: TransitionInfo | null) => void;
}

// ── Catalog card ──────────────────────────────────────────────────────────────

function CatalogCard({ entry, onDragStart }: {
  entry: TransitionCatalogEntry;
  onDragStart: (e: React.DragEvent, typeId: string) => void;
}) {
  return (
    <div
      className="tr-card"
      draggable
      onDragStart={e => onDragStart(e, entry.typeId)}
      title={entry.desc}
    >
      <span className="tr-card__icon">{entry.icon}</span>
      <span className="tr-card__name">{entry.name}</span>
    </div>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────

export default function TransitionPanel({ selected, onSelect }: Props) {
  const [catalog, setCatalog] = useState<TransitionCatalogEntry[]>([]);
  const [activeEntry, setActiveEntry] = useState<TransitionCatalogEntry | null>(null);
  const [tr, setTr] = useState<TransitionInfo | null>(selected ?? null);

  useEffect(() => {
    transitionApi.catalog().then(r => setCatalog(r.transitions)).catch(() => {});
  }, []);

  useEffect(() => { setTr(selected ?? null); }, [selected]);

  // When a different transition is selected, look up its catalog entry
  useEffect(() => {
    if (!tr) { setActiveEntry(null); return; }
    setActiveEntry(catalog.find(c => c.typeId === tr.typeId) ?? null);
  }, [tr, catalog]);

  const onDragStart = useCallback((e: React.DragEvent, typeId: string) => {
    e.dataTransfer.setData('application/fade-transition', typeId);
    e.dataTransfer.effectAllowed = 'copy';
  }, []);

  const patchParam = useCallback(async (key: string, val: number) => {
    if (!tr) return;
    const updated = await transitionApi.patch(tr.transId, { params: { [key]: val } });
    setTr(updated);
    onSelect?.(updated);
    window.dispatchEvent(new CustomEvent('fade:transition-changed'));
  }, [tr, onSelect]);

  const patchDuration = useCallback(async (dur: number) => {
    if (!tr) return;
    const updated = await transitionApi.patch(tr.transId, { duration: Math.max(1, dur) });
    setTr(updated);
    onSelect?.(updated);
    window.dispatchEvent(new CustomEvent('fade:transition-changed'));
  }, [tr, onSelect]);

  const patchType = useCallback(async (typeId: string) => {
    if (!tr) return;
    const updated = await transitionApi.patch(tr.transId, { typeId });
    setTr(updated);
    onSelect?.(updated);
    window.dispatchEvent(new CustomEvent('fade:transition-changed'));
  }, [tr, onSelect]);

  const removeTr = useCallback(async () => {
    if (!tr) return;
    await transitionApi.remove(tr.transId);
    setTr(null);
    onSelect?.(null);
    window.dispatchEvent(new CustomEvent('fade:transition-changed'));
  }, [tr, onSelect]);

  // Group catalog by category
  const grouped = catalog.reduce<Record<string, TransitionCatalogEntry[]>>((acc, e) => {
    (acc[e.category] = acc[e.category] ?? []).push(e);
    return acc;
  }, {});

  return (
    <div className="tr-panel">
      {/* Catalog */}
      <div className="tr-panel__catalog">
        <div className="tr-panel__catalog-title">Transitions</div>
        <div className="tr-panel__hint">Drag onto clip junction • or click a junction on the timeline</div>
        {Object.entries(grouped).map(([cat, entries]) => (
          <div key={cat}>
            <div className="tr-panel__cat-label">{cat}</div>
            <div className="tr-panel__cards">
              {entries.map(e => (
                <CatalogCard key={e.typeId} entry={e} onDragStart={onDragStart} />
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Editor — shown when a transition is selected */}
      {tr && (
        <div className="tr-panel__editor">
          <div className="tr-panel__editor-header">
            <span className="tr-panel__editor-title">
              {catalog.find(c => c.typeId === tr.typeId)?.name ?? tr.typeId}
            </span>
            <button className="tr-panel__del" onClick={removeTr} title="Remove transition">✕</button>
          </div>

          {/* Type selector */}
          <div className="tr-param">
            <label className="tr-param__label">Type</label>
            <select
              className="tr-param__select"
              value={tr.typeId}
              onChange={e => patchType(e.target.value)}
            >
              {catalog.map(c => (
                <option key={c.typeId} value={c.typeId}>{c.name}</option>
              ))}
            </select>
          </div>

          {/* Duration */}
          <div className="tr-param">
            <label className="tr-param__label">Duration (frames)</label>
            <div className="tr-param__track">
              <div className="tr-param__fill" style={{ width: `${Math.min(100, (tr.duration / 90) * 100)}%` }} />
              <input
                type="range" min={1} max={90} step={1}
                defaultValue={tr.duration}
                className="tr-param__slider"
                onMouseUp={e => patchDuration(parseInt((e.target as HTMLInputElement).value))}
              />
            </div>
            <span className="tr-param__val">{tr.duration}f</span>
          </div>

          {/* SkSL params */}
          {(activeEntry?.params ?? []).map(p => {
            const val = tr.values[p.id] ?? p.default;
            const pct = ((val - p.min) / (p.max - p.min)) * 100;
            return (
              <div key={p.id} className="tr-param">
                <label className="tr-param__label">{p.displayName}</label>
                <div className="tr-param__track">
                  <div className="tr-param__fill" style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
                  <input
                    type="range" min={p.min} max={p.max} step={(p.max - p.min) / 200}
                    defaultValue={val}
                    className="tr-param__slider"
                    onMouseUp={e => patchParam(p.id, parseFloat((e.target as HTMLInputElement).value))}
                  />
                </div>
                <span className="tr-param__val">{val.toFixed(3)}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
