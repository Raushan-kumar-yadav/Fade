// DirectorPanel.tsx — Multi-Agent Parallel Composition Director

import React, { useState, useCallback } from "react";
import "./DirectorPanel.css";
import { useDirectorSession, AgentState } from "./useDirectorSession";

// ── Constants ─────────────────────────────────────────────────────────────────

const COMP_TYPES = [
  { id: "image", label: "Image",   icon: "🖼️",  hint: "Social poster" },
  { id: "video", label: "Video",   icon: "🎬",  hint: "Edited reel" },
  { id: "pdf",   label: "PDF",     icon: "📄",  hint: "Carousel doc" },
];

const STATUS_ICONS: Record<string, string> = {
  pending:   "○",
  running:   "◎",
  done:      "✓",
  error:     "✕",
  cancelled: "⊘",
};

// ── Agent Card ────────────────────────────────────────────────────────────────

interface AgentCardProps {
  info:       { id: string; label: string; icon: string };
  state:      AgentState | undefined;
  onViewComp: (compId: string) => void;
}

const AgentCard: React.FC<AgentCardProps> = ({ info, state, onViewComp }) => {
  const status   = state?.status ?? "pending";
  const label    = state?.label  ?? "Waiting…";
  const progress = state?.progress ?? 0;

  return (
    <div className={`agent-card ${status}`}>
      {/* Header */}
      <div className="agent-card-header">
        <span className="agent-card-icon">{info.icon}</span>
        <span className="agent-card-type">{info.label}</span>
        <span className={`agent-status-dot ${status}`} title={STATUS_ICONS[status]} />
      </div>

      {/* Progress bar */}
      <div className="agent-progress-bar">
        <div
          className="agent-progress-fill"
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Label */}
      <div className="agent-label" title={label}>{label}</div>

      {/* Thinking stream */}
      {state?.thinking && (
        <div className="agent-thinking">{state.thinking}</div>
      )}

      {/* Error */}
      {state?.error && (
        <div className="agent-label" style={{ color: "#f87171" }}>{state.error}</div>
      )}

      {/* View comp button */}
      {state?.comp_id && (
        <button
          className="agent-view-btn"
          onClick={() => onViewComp(state.comp_id)}
          title={`Open ${info.label} composition`}
        >
          View Comp →
        </button>
      )}
    </div>
  );
};

// ── Director Panel ────────────────────────────────────────────────────────────

interface DirectorPanelProps {
  /** Called when the user clicks "View Comp" — switch the editor to that comp */
  onActivateComp?: (compId: string) => void;
  /** assetIds pre-seeded from library "Send to Director" */
  initialAssets?: string[];
}

const DirectorPanel: React.FC<DirectorPanelProps> = ({
  onActivateComp,
  initialAssets = [],
}) => {
  const [intent,    setIntent]    = useState("");
  const [assets,    setAssets]    = useState<string[]>(initialAssets);
  const [assetInput, setAssetInput] = useState("");
  const [compTypes, setCompTypes] = useState<string[]>(["image", "video", "pdf"]);

  const { session, launch, cancel, reset } = useDirectorSession();

  const isRunning = session.phase === "running";
  const isDone    = session.phase === "done";

  // ── Asset management ──────────────────────────────────────────────────────
  const addAsset = useCallback(() => {
    const id = assetInput.trim();
    if (id && !assets.includes(id)) setAssets(prev => [...prev, id]);
    setAssetInput("");
  }, [assetInput, assets]);

  const removeAsset = useCallback((id: string) => {
    setAssets(prev => prev.filter(a => a !== id));
  }, []);

  // ── Comp type toggle ──────────────────────────────────────────────────────
  const toggleType = useCallback((id: string) => {
    setCompTypes(prev =>
      prev.includes(id) ? prev.filter(t => t !== id) : [...prev, id]
    );
  }, []);

  // ── Launch ────────────────────────────────────────────────────────────────
  const handleLaunch = useCallback(() => {
    if (!intent.trim() || compTypes.length === 0) return;
    launch(assets, intent.trim(), compTypes);
  }, [intent, assets, compTypes, launch]);

  // ── View comp ─────────────────────────────────────────────────────────────
  const handleViewComp = useCallback((compId: string) => {
    // Call the global activate_comp API directly
    fetch("http://localhost:8000/comps/activate", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ comp_id: compId }),
    }).catch(console.error);
    onActivateComp?.(compId);
  }, [onActivateComp]);

  // ── Render ────────────────────────────────────────────────────────────────
  const activeAgents = COMP_TYPES.filter(c => compTypes.includes(c.id));
  const allDone = isDone || (
    activeAgents.length > 0 &&
    activeAgents.every(c => {
      const s = session.agents[c.id]?.status;
      return s === "done" || s === "error" || s === "cancelled";
    })
  );

  return (
    <div className="director-panel">
      {/* ── Header ── */}
      <div className="director-header">
        <span className="director-header-icon">🎯</span>
        <div>
          <h2>Director</h2>
          <p>Parallel AI composition — image · video · PDF</p>
        </div>
      </div>

      <div className="director-body">
        {/* ── Asset zone ── */}
        <div className="director-assets">
          <div className="director-assets-label">Assets</div>
          <div className="director-asset-tags">
            {assets.length === 0 && (
              <span className="director-asset-empty">No assets added yet</span>
            )}
            {assets.map(id => (
              <span className="director-asset-tag" key={id}>
                {id.slice(0, 8)}…
                <button
                  className="director-asset-tag-remove"
                  onClick={() => removeAsset(id)}
                  title="Remove"
                >×</button>
              </span>
            ))}
          </div>
          <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
            <input
              style={{
                flex: 1, background: "rgba(255,255,255,0.05)",
                border: "1px solid rgba(255,255,255,0.1)", borderRadius: 6,
                color: "#e8eaf0", fontSize: 12, padding: "5px 8px", outline: "none",
                fontFamily: "inherit",
              }}
              placeholder="Paste asset ID…"
              value={assetInput}
              onChange={e => setAssetInput(e.target.value)}
              onKeyDown={e => e.key === "Enter" && addAsset()}
            />
            <button
              onClick={addAsset}
              style={{
                padding: "5px 12px", borderRadius: 6, border: "1px solid rgba(167,139,250,0.3)",
                background: "rgba(167,139,250,0.1)", color: "#c4b5fd",
                fontSize: 12, cursor: "pointer", fontFamily: "inherit",
              }}
            >Add</button>
          </div>
        </div>

        {/* ── Intent ── */}
        <div className="director-intent">
          <span className="director-label">Intent / Goal</span>
          <textarea
            rows={3}
            placeholder="e.g. Create content for our product launch targeting Gen-Z on social media…"
            value={intent}
            onChange={e => setIntent(e.target.value)}
            disabled={isRunning}
          />
        </div>

        {/* ── Comp type toggles ── */}
        <div>
          <span className="director-label" style={{ display: "block", marginBottom: 8 }}>
            Output types
          </span>
          <div className="director-types">
            {COMP_TYPES.map(ct => (
              <button
                key={ct.id}
                className={`director-type-btn ${compTypes.includes(ct.id) ? "active" : ""}`}
                onClick={() => toggleType(ct.id)}
                disabled={isRunning}
              >
                <span className="type-icon">{ct.icon}</span>
                <span>{ct.label}</span>
                <span style={{ fontSize: 9, opacity: 0.6 }}>{ct.hint}</span>
              </button>
            ))}
          </div>
        </div>

        {/* ── Launch / Reset button ── */}
        {!isRunning && !allDone ? (
          <button
            className="director-launch-btn"
            onClick={handleLaunch}
            disabled={!intent.trim() || compTypes.length === 0}
          >
            ▶ Launch Director
          </button>
        ) : allDone ? (
          <button
            className="director-launch-btn"
            onClick={reset}
            style={{ background: "linear-gradient(135deg, #374151, #4b5563)" }}
          >
            ↺ New Session
          </button>
        ) : null}

        {/* ── Agent cards ── */}
        {(isRunning || allDone) && (
          <>
            <div className="director-agents">
              {activeAgents.map(ct => (
                <AgentCard
                  key={ct.id}
                  info={ct}
                  state={session.agents[ct.id]}
                  onViewComp={handleViewComp}
                />
              ))}
            </div>

            {/* Overall progress */}
            <div className="director-overall">
              <div className="director-overall-bar">
                <div
                  className="director-overall-fill"
                  style={{ width: `${session.overallPct}%` }}
                />
              </div>
              <div className="director-overall-label">
                {allDone
                  ? `All agents finished (${Object.values(session.agents).filter(a => a.status === "done").length}/${activeAgents.length} done)`
                  : `Overall: ${session.overallPct}%`
                }
              </div>
            </div>
          </>
        )}

        {/* ── Idle hint ── */}
        {session.phase === "idle" && (
          <div className="director-idle-hint">
            <span className="hint-icon">🎬</span>
            Add assets from the library, describe your goal,
            choose output types, and hit&nbsp;<strong>Launch Director</strong>.
            <br /><br />
            Three AI agents will run&nbsp;<em>simultaneously</em> to build
            your image, video, and PDF compositions.
          </div>
        )}
      </div>

      {/* ── Footer ── */}
      {(isRunning || allDone) && (
        <div className="director-footer">
          {isRunning && (
            <button className="director-cancel-btn" onClick={cancel}>
              ⏹ Cancel All
            </button>
          )}
          <button
            className="director-publish-btn"
            disabled={!allDone}
            onClick={() => alert("Publish flow — connect your social accounts in Settings.")}
            style={isRunning ? { flex: 1 } : {}}
          >
            🚀 Publish
          </button>
        </div>
      )}
    </div>
  );
};

export default DirectorPanel;
