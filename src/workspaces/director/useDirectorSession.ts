 
import { useState, useRef, useCallback } from "react";

export type AgentStatus = "pending" | "running" | "done" | "error" | "cancelled";

export interface AgentState {
  job_id:    string;
  comp_type: "image" | "video" | "pdf";
  comp_id:   string;
  status: AgentStatus;
  label: string;
  progress:  number;
  thinking: string;   // last N chars of token stream
  error: string;
}

export interface DirectorSessionState {
  session_id:  string | null;
  phase: "idle" | "running" | "done" | "error";
  agents: Record<string, AgentState>;   // keyed by comp_type
  overallPct:  number;
}

const PORT = 8000;

function _empty(): DirectorSessionState {
  return { session_id: null, phase: "idle", agents: {}, overallPct: 0 };
}

export function useDirectorSession() {
  const [session, setSession] = useState<DirectorSessionState>(_empty());
  const esRef = useRef<EventSource | null>(null);

  // SSE progress handler
  const _handleProgress = useCallback((raw: string) => {
    try {
      const data = JSON.parse(raw);

      // Session created  
      if (data.type === "session_created") {
        setSession(prev => {
          const agents: Record<string, AgentState> = { ...prev.agents };
          for (const j of (data.jobs ?? [])) {
            agents[j.comp_type] = {
              job_id: j.job_id,
              comp_type: j.comp_type,
              comp_id: j.comp_id,
              status: "pending",
              label: "Waiting to start…",
              progress: 0,
              thinking: "",
              error: "",
            };
          }
          return { ...prev, session_id: data.session_id, phase: "running", agents };
        });
        return;
      }

      // All done
      if (data.type === "all_done") {
        setSession(prev => ({ ...prev, phase: "done", overallPct: 100 }));
        return;
      }

      // Per-agent progress event
      if (data.comp_type) {
        setSession(prev => {
          const ctype = data.comp_type as string;
          const existing = prev.agents[ctype] ?? {
            job_id: data.job_id ?? "",
            comp_type: ctype,
            comp_id: data.comp_id ?? "",
            status: "pending" as AgentStatus,
            label: "",
            progress: 0,
            thinking: "",
            error: "",
          };

          const next: AgentState = {
            ...existing,
            status: _phaseToStatus(data.phase ?? "", existing.status),
            label:  data.label ?? existing.label,
            progress: data.progress ?? existing.progress,
            thinking: data.token
              ? (existing.thinking + data.token).slice(-300)
              : existing.thinking,
            error: data.phase === "error" ? (data.label ?? "") : existing.error,
          };

          const agents = { ...prev.agents, [ctype]: next };

          // Overall %
          const vals = Object.values(agents).map(a => a.progress);
          const overallPct = vals.length ? Math.round(vals.reduce((a, b) => a + b, 0) / vals.length) : 0;

          return { ...prev, agents, overallPct };
        });
      }
    } catch { /* ignore malformed */ }
  }, []);

  const launch = useCallback(async (
    assets: string[],
    intent: string,
    compTypes: string[],
  ) => {
    // Close any existing stream
    esRef.current?.close();

    // POST to start the director run (returns SSE stream)
    const resp = await fetch(`http://localhost:${PORT}/ai/director/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ assets, intent, comp_types: compTypes, port: PORT }),
    });

    if (!resp.ok || !resp.body) {
      setSession(s => ({ ...s, phase: "error" }));
      return;
    }

    setSession(prev => ({ ...prev, phase: "running", overallPct: 0 }));

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    const pump = async () => {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            _handleProgress(line.slice(6).trim());
          }
        }
      }
    };

    pump().catch(console.error);
  }, [_handleProgress]);

  const cancel = useCallback(async () => {
    if (!session.session_id) return;
    esRef.current?.close();
    await fetch(`http://localhost:${PORT}/ai/director/cancel/${session.session_id}`, {
      method: "POST",
    }).catch(() => {});
    setSession(prev => ({ ...prev, phase: "idle" }));
  }, [session.session_id]);

  const reset = useCallback(() => {
    esRef.current?.close();
    setSession(_empty());
  }, []);

  return { session, launch, cancel, reset };
}

function _phaseToStatus(phase: string, current: AgentStatus): AgentStatus {
  switch (phase) {
    case "start": return "running";
    case "thinking":  return "running";
    case "tool": return "running";
    case "done": return "done";
    case "error": return "error";
    case "cancelled": return "cancelled";
    default: return current;
  }
}
