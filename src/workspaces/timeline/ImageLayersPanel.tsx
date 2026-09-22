import React, { useState, useEffect, useCallback, useRef } from "react";
import type { ImageLayer } from "./types";

// ─── API helpers ────────────────────────────────────────────────────────────

const BASE = "http://localhost:8002";

async function fetchLayers(compId: string): Promise<ImageLayer[]> {
  const res = await fetch(`${BASE}/comps/${compId}/layers`);
  if (!res.ok) return [];
  const data = await res.json();
  return (data.layers ?? []).sort(
    (a: ImageLayer, b: ImageLayer) => b.z_index - a.z_index
  );
}

async function addLayer(compId: string, name: string, element?: ImageLayer["element"]) {
  await fetch(`${BASE}/comps/${compId}/layers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, element: element ?? null }),
  });
}

async function patchLayer(compId: string, layerId: string, patch: Partial<ImageLayer>) {
  await fetch(`${BASE}/comps/${compId}/layers/${layerId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
}

async function deleteLayer(compId: string, layerId: string) {
  await fetch(`${BASE}/comps/${compId}/layers/${layerId}`, { method: "DELETE" });
}

async function reorderLayers(compId: string, layerIds: string[]) {
  await fetch(`${BASE}/comps/${compId}/layers/reorder`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ layerIds }),
  });
}

// ─── Component ───────────────────────────────────────────────────────────────

interface Props {
  compId: string;
}

const BLEND_MODES = [
  "normal", "multiply", "screen", "overlay",
  "darken", "lighten", "color-dodge", "color-burn",
  "hard-light", "soft-light", "difference", "exclusion",
];

export default function ImageLayersPanel({ compId }: Props) {
  const [layers, setLayers] = useState<ImageLayer[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [dragOverId, setDragOverId] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [renameVal, setRenameVal] = useState("");
  const renameRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    const data = await fetchLayers(compId);
    setLayers(data);
  }, [compId]);

  useEffect(() => {
    load();
  }, [load]);

  // ── Focus rename input when opened
  useEffect(() => {
    if (renaming && renameRef.current) renameRef.current.focus();
  }, [renaming]);

  // ── Actions ──────────────────────────────────────────────────────────────

  const handleAddLayer = async (
    type: "solid" | "text" | "image" | "shape" = "solid"
  ) => {
    const name =
      type === "solid" ? "Solid Layer"
      : type === "text" ? "Text Layer"
      : type === "image" ? "Image Layer"
      : "Shape Layer";

    const element: ImageLayer["element"] =
      type === "solid"
        ? { type: "solid", x: 0, y: 0, width: 1920, height: 1080, rotation: 0, color: "#3a3a6a" }
        : type === "text"
        ? { type: "text", x: 100, y: 100, width: 600, height: 80, rotation: 0, text: "New Text", color: "#ffffff" }
        : null;

    await addLayer(compId, name, element);
    load();
  };

  const handleToggleVisible = async (lyr: ImageLayer) => {
    await patchLayer(compId, lyr.trackId, { visible: !lyr.visible });
    load();
  };

  const handleToggleLock = async (lyr: ImageLayer) => {
    await patchLayer(compId, lyr.trackId, { locked: !lyr.locked });
    load();
  };

  const handleOpacity = async (lyr: ImageLayer, val: number) => {
    // Optimistic UI update
    setLayers((prev) =>
      prev.map((l) => (l.trackId === lyr.trackId ? { ...l, opacity: val } : l))
    );
    await patchLayer(compId, lyr.trackId, { opacity: val });
  };

  const handleBlendMode = async (lyr: ImageLayer, blendMode: string) => {
    await patchLayer(compId, lyr.trackId, { blendMode });
    load();
  };

  const handleDelete = async (layerId: string) => {
    await deleteLayer(compId, layerId);
    if (selectedId === layerId) setSelectedId(null);
    load();
  };

  const handleRenameStart = (lyr: ImageLayer) => {
    setRenaming(lyr.trackId);
    setRenameVal(lyr.name);
  };

  const handleRenameCommit = async () => {
    if (!renaming) return;
    if (renameVal.trim()) {
      await patchLayer(compId, renaming, { name: renameVal.trim() });
    }
    setRenaming(null);
    load();
  };

  // ── Drag-to-reorder ──────────────────────────────────────────────────────

  const handleDragStart = (id: string) => setDraggingId(id);
  const handleDragOver = (e: React.DragEvent, id: string) => {
    e.preventDefault();
    setDragOverId(id);
  };
  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    if (!draggingId || !dragOverId || draggingId === dragOverId) {
      setDraggingId(null);
      setDragOverId(null);
      return;
    }
    const ids = layers.map((l) => l.trackId);
    const fromIdx = ids.indexOf(draggingId);
    const toIdx = ids.indexOf(dragOverId);
    const newIds = [...ids];
    newIds.splice(fromIdx, 1);
    newIds.splice(toIdx, 0, draggingId);
    setDraggingId(null);
    setDragOverId(null);
    await reorderLayers(compId, newIds);
    load();
  };

  // ── Thumbnail icon ───────────────────────────────────────────────────────

  const layerIcon = (lyr: ImageLayer) => {
    if (!lyr.element) return "◇";
    switch (lyr.element.type) {
      case "image":  return "🖼";
      case "text":   return "T";
      case "solid":  return "■";
      case "shape":  return "◆";
      default:       return "◇";
    }
  };

  const selectedLayer = layers.find((l) => l.trackId === selectedId) ?? null;

  // ─── Render ───────────────────────────────────────────────────────────────
  return (
    <div style={s.panel}>
      {/* Header */}
      <div style={s.header}>
        <span style={s.headerTitle}>🖼 Image Layers</span>
        <div style={s.headerActions}>
          <button style={s.addBtn} onClick={() => handleAddLayer("solid")} title="Add Solid">■</button>
          <button style={s.addBtn} onClick={() => handleAddLayer("text")}  title="Add Text">T</button>
          <button style={s.addBtn} onClick={() => handleAddLayer("image")} title="Add Image">🖼</button>
          <button style={s.addBtn} onClick={() => handleAddLayer("shape")} title="Add Shape">◆</button>
        </div>
      </div>

      {/* Layer list */}
      <div style={s.list} onDrop={handleDrop} onDragOver={(e) => e.preventDefault()}>
        {layers.length === 0 && (
          <div style={s.empty}>
            No layers yet.<br />
            Click ■ T 🖼 ◆ above to add one.
          </div>
        )}
        {layers.map((lyr) => (
          <div
            key={lyr.trackId}
            draggable
            onDragStart={() => handleDragStart(lyr.trackId)}
            onDragOver={(e) => handleDragOver(e, lyr.trackId)}
            onDrop={handleDrop}
            onClick={() => setSelectedId(lyr.trackId)}
            style={{
              ...s.row,
              ...(selectedId === lyr.trackId ? s.rowSelected : {}),
              ...(dragOverId === lyr.trackId ? s.rowDragOver : {}),
              opacity: lyr.visible ? 1 : 0.38,
            }}
          >
            {/* Drag handle */}
            <span style={s.dragHandle} title="Drag to reorder">⠿</span>

            {/* Visibility */}
            <button
              style={s.iconBtn}
              onClick={(e) => { e.stopPropagation(); handleToggleVisible(lyr); }}
              title={lyr.visible ? "Hide layer" : "Show layer"}
            >
              {lyr.visible ? "👁" : "🚫"}
            </button>

            {/* Lock */}
            <button
              style={s.iconBtn}
              onClick={(e) => { e.stopPropagation(); handleToggleLock(lyr); }}
              title={lyr.locked ? "Unlock layer" : "Lock layer"}
            >
              {lyr.locked ? "🔒" : "🔓"}
            </button>

            {/* Thumbnail */}
            <div style={s.thumb}>{layerIcon(lyr)}</div>

            {/* Name — double-click to rename */}
            {renaming === lyr.trackId ? (
              <input
                ref={renameRef}
                style={s.renameInput}
                value={renameVal}
                onChange={(e) => setRenameVal(e.target.value)}
                onBlur={handleRenameCommit}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleRenameCommit();
                  if (e.key === "Escape") setRenaming(null);
                }}
                onClick={(e) => e.stopPropagation()}
              />
            ) : (
              <span
                style={s.name}
                onDoubleClick={(e) => { e.stopPropagation(); handleRenameStart(lyr); }}
                title="Double-click to rename"
              >
                {lyr.name}
              </span>
            )}

            {/* Opacity % */}
            <span style={s.opacityPct}>{Math.round(lyr.opacity * 100)}%</span>

            {/* Delete */}
            <button
              style={{ ...s.iconBtn, color: "#e05060" }}
              onClick={(e) => { e.stopPropagation(); handleDelete(lyr.trackId); }}
              title="Delete layer"
            >
              ✕
            </button>
          </div>
        ))}
      </div>

      {/* Footer: properties for selected layer */}
      {selectedLayer && (
        <div style={s.footer}>
          {/* Blend mode */}
          <div style={s.footerRow}>
            <label style={s.footerLabel}>Blend</label>
            <select
              style={s.select}
              value={selectedLayer.blendMode}
              onChange={(e) => handleBlendMode(selectedLayer, e.target.value)}
            >
              {BLEND_MODES.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>

          {/* Opacity slider */}
          <div style={s.footerRow}>
            <label style={s.footerLabel}>Opacity</label>
            <input
              type="range"
              min={0} max={1} step={0.01}
              value={selectedLayer.opacity}
              style={s.slider}
              onChange={(e) => handleOpacity(selectedLayer, parseFloat(e.target.value))}
            />
            <span style={s.opacityLabel}>{Math.round(selectedLayer.opacity * 100)}%</span>
          </div>

          {/* Element info */}
          {selectedLayer.element && (
            <div style={s.footerRow}>
              <label style={s.footerLabel}>Type</label>
              <span style={s.footerValue}>{selectedLayer.element.type}</span>
              <label style={s.footerLabel}>Size</label>
              <span style={s.footerValue}>
                {selectedLayer.element.width}×{selectedLayer.element.height}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Styles ──────────────────────────────────────────────────────────────────

const s: Record<string, React.CSSProperties> = {
  panel: {
    display: "flex",
    flexDirection: "column",
    background: "#1a1a2e",
    height: "100%",
    fontFamily: "'Inter', sans-serif",
    fontSize: 12,
    color: "#d0d8f0",
    overflow: "hidden",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "8px 12px",
    borderBottom: "1px solid #2a2a4a",
    background: "#16213e",
    flexShrink: 0,
  },
  headerTitle: {
    fontWeight: 600,
    fontSize: 12,
    letterSpacing: "0.04em",
    color: "#c084fc",
    textTransform: "uppercase",
  },
  headerActions: {
    display: "flex",
    gap: 4,
  },
  addBtn: {
    background: "#252550",
    border: "1px solid #3a3a6a",
    borderRadius: 5,
    color: "#a0a8d0",
    cursor: "pointer",
    fontSize: 13,
    padding: "3px 8px",
    transition: "background 0.15s",
  },
  list: {
    flex: 1,
    overflowY: "auto",
  },
  empty: {
    padding: "28px 16px",
    textAlign: "center",
    color: "#4040a0",
    lineHeight: 1.7,
  },
  row: {
    display: "flex",
    alignItems: "center",
    gap: 5,
    padding: "5px 8px",
    borderBottom: "1px solid #1e1e3a",
    cursor: "pointer",
    transition: "background 0.1s",
    userSelect: "none",
  },
  rowSelected: {
    background: "#7c3aed18",
    borderLeft: "2px solid #7c3aed",
  },
  rowDragOver: {
    background: "#7c3aed30",
    borderTop: "2px solid #c084fc",
  },
  dragHandle: {
    color: "#3a3a6a",
    cursor: "grab",
    fontSize: 14,
    flexShrink: 0,
  },
  iconBtn: {
    background: "none",
    border: "none",
    cursor: "pointer",
    fontSize: 12,
    padding: "0 2px",
    color: "#6070a0",
    flexShrink: 0,
  },
  thumb: {
    width: 26,
    height: 26,
    background: "#252550",
    borderRadius: 4,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 13,
    flexShrink: 0,
  },
  name: {
    flex: 1,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    color: "#c8d0f0",
  },
  renameInput: {
    flex: 1,
    background: "#0f1030",
    border: "1px solid #7c3aed",
    borderRadius: 4,
    color: "#e0e0f0",
    fontSize: 12,
    padding: "2px 5px",
    outline: "none",
  },
  opacityPct: {
    color: "#505070",
    fontSize: 10,
    minWidth: 28,
    textAlign: "right",
    flexShrink: 0,
  },
  footer: {
    flexShrink: 0,
    borderTop: "1px solid #2a2a4a",
    background: "#14142a",
    padding: "8px 12px",
    display: "flex",
    flexDirection: "column",
    gap: 6,
  },
  footerRow: {
    display: "flex",
    alignItems: "center",
    gap: 6,
  },
  footerLabel: {
    color: "#505078",
    fontSize: 10,
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    minWidth: 36,
  },
  footerValue: {
    color: "#a0a8c0",
    fontSize: 11,
    marginRight: 8,
  },
  select: {
    flex: 1,
    background: "#0f1030",
    border: "1px solid #3a3a6a",
    borderRadius: 4,
    color: "#d0d8f0",
    fontSize: 11,
    padding: "3px 6px",
  },
  slider: {
    flex: 1,
    accentColor: "#7c3aed",
  },
  opacityLabel: {
    color: "#80909c",
    fontSize: 10,
    minWidth: 28,
    textAlign: "right",
  },
};
