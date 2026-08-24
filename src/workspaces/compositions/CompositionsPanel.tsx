import React, { useState, useEffect, useCallback } from "react";
import { useTimeline } from "../timeline/TimelineContext";

 // Types
 
interface CompMeta {
  compId: string;
  name: string;
  trackCount: number;
  clipCount: number;
}
 
const BASE = "http://localhost:8000";

async function fetchComps(): Promise<CompMeta[]> {
  const res = await fetch(`${BASE}/comps`);
  const data = await res.json();
  return data.comps ?? [];
}

async function createComp(name: string): Promise<CompMeta> {
  const res = await fetch(`${BASE}/comps`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  return res.json();
}

async function deleteComp(compId: string): Promise<void> {
  await fetch(`${BASE}/comps/${compId}`, { method: "DELETE" });
}

async function addCompClip(compId: string, startFrame: number, duration: number) {
  const res = await fetch(`${BASE}/clips/comp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ compId, startFrame, duration }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(err.detail ?? "Failed to add comp clip");
  }
  return res.json();
}

 // Component
 export default function CompositionsPanel() {
  const { state, dispatch } = useTimeline();
  const [comps, setComps] = useState<CompMeta[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchComps();
      setComps(data);
    } catch {
      setError("Failed to load compositions");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const comp = await createComp(newName.trim());
      setComps((prev) => [...prev, { compId: comp.compId, name: comp.name, trackCount: 0, clipCount: 0 }]);
      setNewName("");
    } catch {
      setError("Failed to create composition");
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (compId: string) => {
    if (!window.confirm("Delete this composition?")) return;
    try {
      await deleteComp(compId);
      setComps((prev) => prev.filter((c) => c.compId !== compId));
      
      if (state.activeCompId === compId) {
        dispatch({ type: "EXIT_COMP" });
      }
    } catch {
      setError("Failed to delete composition");
    }
  };

  const handleAddToTimeline = async (comp: CompMeta) => {
    try {
      await addCompClip(comp.compId, state.currentFrame, 90);
    } catch (err: any) {
      setError(err.message ?? "Cycle detected or failed to add");
    }
  };

  const handleEnter = (comp: CompMeta) => {
    dispatch({ type: "ENTER_COMP", compId: comp.compId, compName: comp.name });
  };

  // Breadcrumb 
  const insideComp = state.activeCompId !== null;

  return (
    <div style={styles.panel}>
      {/* Header */}
      <div style={styles.header}>
        <span style={styles.headerTitle}>Compositions</span>
        <button style={styles.refreshBtn} onClick={load} title="Refresh">↺</button>
      </div>

      {/* Breadcrumb */}
      {insideComp && (
        <div style={styles.breadcrumb}>
          <button style={styles.breadcrumbBack} onClick={() => dispatch({ type: "EXIT_COMP" })}>
            ← Root
          </button>
          <span style={styles.breadcrumbName}>/{state.activeCompName}</span>
        </div>
      )}

      {/* New composition form */}
      <form onSubmit={handleCreate} style={styles.form}>
        <input
          style={styles.input}
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="Composition name…"
          disabled={creating}
        />
        <button style={styles.createBtn} type="submit" disabled={creating || !newName.trim()}>
          {creating ? "…" : "+"}
        </button>
      </form>

      {error && (
        <div style={styles.error} onClick={() => setError(null)}>
          ⚠ {error}
        </div>
      )}

      {/* List */}
      <div style={styles.list}>
        {loading && <div style={styles.loading}>Loading…</div>}
        {!loading && comps.length === 0 && (
          <div style={styles.empty}>No compositions yet.<br />Create one above.</div>
        )}
        {comps.map((comp) => (
          <div
            key={comp.compId}
            style={{
              ...styles.item,
              ...(state.activeCompId === comp.compId ? styles.itemActive : {}),
            }}
          >
            <div style={styles.itemInfo}>
              <span style={styles.itemIcon}>⊞</span>
              <div>
                <div style={styles.itemName}>{comp.name}</div>
                <div style={styles.itemMeta}>
                  {comp.trackCount} tracks · {comp.clipCount} clips
                </div>
              </div>
            </div>
            <div style={styles.itemActions}>
              <button
                style={styles.actionBtn}
                title="Add to timeline at playhead"
                onClick={() => handleAddToTimeline(comp)}
              >
                ↓
              </button>
              <button
                style={styles.actionBtn}
                title="Open composition"
                onClick={() => handleEnter(comp)}
              >
                ✎
              </button>
              <button
                style={{ ...styles.actionBtn, ...styles.deleteBtn }}
                title="Delete"
                onClick={() => handleDelete(comp.compId)}
              >
                ✕
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

 // Styles  
 const styles: Record<string, React.CSSProperties> = {
  panel: {
    display: "flex",
    flexDirection: "column",
    background: "#1a1a2e",
    color: "#e8e8f0",
    fontFamily: "'Inter', sans-serif",
    fontSize: 13,
    height: "100%",
    overflow: "hidden",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "10px 12px 8px",
    borderBottom: "1px solid #2a2a4a",
    background: "#16213e",
  },
  headerTitle: {
    fontWeight: 600,
    fontSize: 13,
    letterSpacing: "0.04em",
    color: "#a0a8d0",
    textTransform: "uppercase",
  },
  refreshBtn: {
    background: "none",
    border: "none",
    color: "#6060a0",
    cursor: "pointer",
    fontSize: 16,
    padding: "2px 4px",
  },
  breadcrumb: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "6px 12px",
    background: "#00897b22",
    borderBottom: "1px solid #00897b44",
    fontSize: 12,
  },
  breadcrumbBack: {
    background: "none",
    border: "none",
    color: "#00e5cc",
    cursor: "pointer",
    fontSize: 12,
    padding: 0,
  },
  breadcrumbName: {
    color: "#80cbc4",
  },
  form: {
    display: "flex",
    gap: 6,
    padding: "10px 12px",
    borderBottom: "1px solid #2a2a4a",
  },
  input: {
    flex: 1,
    background: "#0f1030",
    border: "1px solid #3a3a6a",
    borderRadius: 6,
    color: "#e0e0f0",
    fontSize: 12,
    padding: "5px 8px",
    outline: "none",
  },
  createBtn: {
    background: "#00897b",
    border: "none",
    borderRadius: 6,
    color: "#fff",
    cursor: "pointer",
    fontSize: 16,
    padding: "4px 12px",
    fontWeight: 700,
    transition: "background 0.15s",
  },
  error: {
    margin: "8px 12px",
    padding: "6px 10px",
    background: "#c0303040",
    border: "1px solid #c0303080",
    borderRadius: 6,
    color: "#ff8a80",
    fontSize: 11,
    cursor: "pointer",
  },
  list: {
    flex: 1,
    overflowY: "auto",
    padding: "6px 0",
  },
  loading: {
    padding: "20px",
    textAlign: "center",
    color: "#5050a0",
  },
  empty: {
    padding: "24px 16px",
    textAlign: "center",
    color: "#4040a0",
    lineHeight: 1.6,
  },
  item: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "8px 12px",
    borderBottom: "1px solid #1e1e3a",
    transition: "background 0.1s",
    cursor: "default",
  },
  itemActive: {
    background: "#00897b18",
    borderLeft: "2px solid #00897b",
  },
  itemInfo: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    overflow: "hidden",
  },
  itemIcon: {
    fontSize: 18,
    color: "#00897b",
    flexShrink: 0,
  },
  itemName: {
    fontWeight: 500,
    color: "#d0d8f0",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
    maxWidth: 130,
  },
  itemMeta: {
    fontSize: 11,
    color: "#505070",
    marginTop: 2,
  },
  itemActions: {
    display: "flex",
    gap: 4,
    flexShrink: 0,
  },
  actionBtn: {
    background: "#252550",
    border: "none",
    borderRadius: 4,
    color: "#8090c0",
    cursor: "pointer",
    fontSize: 13,
    padding: "3px 7px",
    transition: "background 0.1s, color 0.1s",
  },
  deleteBtn: {
    color: "#e05060",
  },
};
