import React, { useEffect, useRef, useState, useCallback } from 'react';
import './RemoteMCPPanel.css';

// Types

interface ProviderInfo {
  label: string;
  base_url: string;
  api_key: string;
  model: string;
  needs_key: boolean;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'tool_call' | 'tool_result' | 'thinking' | 'error';
  content: string;
  tool?: string;
  args?: Record<string, unknown>;
}

interface Status {
  connected: boolean;
  mcp_url: string;
  tool_count: number;
  llm: { provider: string; base_url: string; model: string };
}

// Helpers

function getPort(): number {
  return (window as any).__FADE_PORT__ ?? 8000;
}
function api(path: string) {
  return `http://127.0.0.1:${getPort()}${path}`;
}
function uid() {
  return Math.random().toString(36).slice(2);
}

// Thinking-capable providers / models
const THINKING_PROVIDERS = ['claude', 'openrouter', 'custom', 'llamacpp'];
const THINKING_MODEL_HINTS = ['claude-3-7', 'claude-3-5', 'qwen3', 'qwq', 'deepseek-r1', 'gemini-2.0-flash-thinking'];

function modelSupportsThinking(provider: string, model: string): boolean {
  if (THINKING_PROVIDERS.includes(provider)) return true;
  const m = model.toLowerCase();
  return THINKING_MODEL_HINTS.some(h => m.includes(h));
}

// Component

export default function RemoteMCPPanel() {
  // connection / provider state
  const [providers, setProviders] = useState<Record<string, ProviderInfo>>({});
  const [provider,  setProvider]  = useState('llamacpp');
  const [baseUrl,   setBaseUrl]   = useState('http://100.88.241.12:808/v1');
  const [apiKey,    setApiKey]    = useState('none');
  const [model,     setModel]     = useState('local-model');
  const [modelList, setModelList] = useState<string[]>([]);   // detected from /v1/models
  const [detecting, setDetecting] = useState(false);
  const [mcpUrl,    setMcpUrl]    = useState('http://127.0.0.1:7654/sse');
  const [status,    setStatus]    = useState<Status | null>(null);

  // advanced options
  const [temperature,   setTemperature]   = useState(0);
  const [maxTokens,     setMaxTokens]     = useState(8192);
  const [maxSteps,      setMaxSteps]      = useState(15);
  const [thinking,      setThinking]      = useState(false);
  const [thinkBudget,   setThinkBudget]   = useState(5000);
  const [systemPrompt,  setSystemPrompt]  = useState('');
  const [showAdvanced,  setShowAdvanced]  = useState(false);

  // chat state
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input,    setInput]    = useState('');
  const [busy,     setBusy]     = useState(false);
  const [showCfg,  setShowCfg]  = useState(true);
  const [saving,   setSaving]   = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef  = useRef<AbortController | null>(null);

  // fetch providers on mount
  useEffect(() => {
    fetch(api('/mcp-remote/providers'))
      .then(r => r.json())
      .then(data => {
        setProviders(data.providers ?? {});
        const cur = data.current;
        if (cur) {
          setProvider(cur.provider);
          setBaseUrl(cur.base_url);
          setApiKey(cur.api_key);
          setModel(cur.model);
          if (cur.temperature !== undefined) setTemperature(cur.temperature);
          if (cur.max_tokens   !== undefined) setMaxTokens(cur.max_tokens);
          if (cur.max_steps    !== undefined) setMaxSteps(cur.max_steps);
          if (cur.thinking     !== undefined) setThinking(cur.thinking);
          if (cur.think_budget !== undefined) setThinkBudget(cur.think_budget);
          if (cur.system_prompt !== undefined) setSystemPrompt(cur.system_prompt);
        }
      })
      .catch(() => {});

    fetch(api('/mcp-remote/status'))
      .then(r => r.json())
      .then(setStatus)
      .catch(() => {});
  }, []);

  // auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // fill defaults when provider changes
  const handleProviderChange = (p: string) => {
    setProvider(p);
    const def = providers[p];
    if (def) {
      setBaseUrl(def.base_url);
      setApiKey(def.api_key ?? 'none');
      setModel(def.model);
    }
  };

  // auto-detect models from /v1/models
  const detectModels = async () => {
    setDetecting(true);
    try {
      // Strip trailing /v1 so we can re-append it cleanly
      const base = baseUrl.replace(/\/v1\/?$/, '').replace(/\/$/, '');
      const url  = `${base}/v1/models`;
      const r = await fetch(url, {
        headers: apiKey && apiKey !== 'none' ? { Authorization: `Bearer ${apiKey}` } : {},
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      const ids: string[] = (data.data ?? data.models ?? []).map((m: any) => m.id ?? m.name ?? String(m));
      if (ids.length > 0) {
        setModelList(ids);
        setModel(ids[0]);   // auto-select first
      }
    } catch (e) {
      setModelList([]);
      addMsg('error', `Could not fetch models: ${e}`);
    } finally {
      setDetecting(false);
    }
  };

  // save config
  const saveConfig = async () => {
    setSaving(true);
    try {
      await fetch(api('/mcp-remote/config'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider, base_url: baseUrl, api_key: apiKey, model,
          mcp_sse_url: mcpUrl,
          temperature, max_tokens: maxTokens, max_steps: maxSteps,
          thinking, think_budget: thinkBudget,
          system_prompt: systemPrompt,
        }),
      });
      setShowCfg(false);
    } finally {
      setSaving(false);
    }
  };

  // connect / disconnect
  const connect = async () => {
    setBusy(true);
    try {
      const r = await fetch(api('/mcp-remote/connect'), { method: 'POST' });
      const data = await r.json();
      if (data.ok) {
        const s = await fetch(api('/mcp-remote/status')).then(x => x.json());
        setStatus(s);
      } else {
        addMsg('error', `Connection failed: ${data.error}`);
      }
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    await fetch(api('/mcp-remote/disconnect'), { method: 'POST' });
    const s = await fetch(api('/mcp-remote/status')).then(r => r.json());
    setStatus(s);
  };

  // message helpers
  const addMsg = (role: ChatMessage['role'], content: string, tool?: string, args?: Record<string, unknown>) => {
    const m: ChatMessage = { id: uid(), role, content, tool, args };
    setMessages(prev => [...prev, m]);
    return m.id;
  };

  const updateLastAssistant = (text: string) => {
    setMessages(prev => {
      const copy = [...prev];
      for (let i = copy.length - 1; i >= 0; i--) {
        if (copy[i].role === 'assistant') {
          copy[i] = { ...copy[i], content: text };
          return copy;
        }
      }
      return [...copy, { id: uid(), role: 'assistant' as const, content: text }];
    });
  };

  // send
  const send = useCallback(async () => {
    if (!input.trim() || busy) return;
    const text = input.trim();
    setInput('');
    setBusy(true);

    addMsg('user', text);
    setMessages(prev => [...prev, { id: uid(), role: 'assistant', content: '' }]);

    abortRef.current = new AbortController();
    let assistantText = '';

    try {
      const history = messages
        .filter(m => m.role === 'user' || m.role === 'assistant')
        .map(m => ({ role: m.role as 'user' | 'assistant', content: m.content }));

      const resp = await fetch(api('/mcp-remote/chat'), {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ message: text, history }),
        signal:  abortRef.current.signal,
      });

      const reader  = resp.body!.getReader();
      const decoder = new TextDecoder();
      let buf = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() ?? '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;
          try {
            const ev = JSON.parse(raw);
            switch (ev.type) {
              case 'thinking':
                addMsg('thinking', ev.text);
                break;
              case 'token':
                assistantText += ev.text;
                updateLastAssistant(assistantText);
                break;
              case 'tool_call':
                addMsg('tool_call', JSON.stringify(ev.args, null, 2), ev.name, ev.args);
                break;
              case 'tool_result':
                addMsg('tool_result', ev.result, ev.name);
                break;
              case 'done':
                if (ev.text && ev.text !== assistantText) {
                  assistantText = ev.text;
                  updateLastAssistant(assistantText);
                }
                break;
              case 'error':
                addMsg('error', ev.message);
                break;
            }
          } catch { /* ignore parse errors */ }
        }
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') addMsg('error', String(err));
    } finally {
      setBusy(false);
      abortRef.current = null;
      const s = await fetch(api('/mcp-remote/status')).then(r => r.json()).catch(() => null);
      if (s) setStatus(s);
    }
  }, [input, busy, messages]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  };

  const stopGeneration = () => {
    abortRef.current?.abort();
    setBusy(false);
  };

  const clearChat = () => setMessages([]);

  // derived
  const connected = status?.connected ?? false;
  const needsKey  = providers[provider]?.needs_key ?? false;
  const canThink  = modelSupportsThinking(provider, model);

  return (
    <div className="rmc-panel">

      {/* Header */}
      <div className="rmc-header">
        <div className="rmc-header-left">
          <span className="rmc-title">Remote AI Control</span>
          <span className={`rmc-badge ${connected ? 'connected' : 'disconnected'}`}>
            {connected ? `● ${status?.tool_count} tools` : '○ disconnected'}
          </span>
          {connected && thinking && (
            <span className="rmc-badge rmc-badge-think">🧠 thinking</span>
          )}
        </div>
        <div className="rmc-header-actions">
          <button className="rmc-btn rmc-btn-ghost" onClick={clearChat} title="Clear chat">🗑</button>
          <button className="rmc-btn rmc-btn-ghost" onClick={() => setShowCfg(v => !v)} title="Toggle config">⚙</button>
          {connected
            ? <button className="rmc-btn rmc-btn-danger"  onClick={disconnect} disabled={busy}>Disconnect</button>
            : <button className="rmc-btn rmc-btn-primary" onClick={connect}    disabled={busy}>Connect</button>
          }
        </div>
      </div>

      {/* Config panel */}
      {showCfg && (
        <div className="rmc-config">
          {/* Provider */}
          <div className="rmc-config-row">
            <label>Provider</label>
            <select value={provider} onChange={e => handleProviderChange(e.target.value)}>
              {Object.entries(providers).map(([k, v]) => (
                <option key={k} value={k}>{v.label}</option>
              ))}
            </select>
          </div>

          <div className="rmc-config-row">
            <label>Base URL</label>
            <input value={baseUrl} onChange={e => setBaseUrl(e.target.value)}
              placeholder="http://100.88.241.12:808/v1" />
          </div>

          {needsKey && (
            <div className="rmc-config-row">
              <label>API Key</label>
              <input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)}
                placeholder="sk-..." />
            </div>
          )}

          <div className="rmc-config-row rmc-model-row">
            <label>Model</label>
            <div className="rmc-model-input-group">
              {modelList.length > 0 ? (
                <select className="rmc-model-select"
                  value={model} onChange={e => setModel(e.target.value)}>
                  {modelList.map(m => (
                    <option key={m} value={m} title={m}>
                      {m.length > 40 ? '…' + m.slice(-38) : m}
                    </option>
                  ))}
                </select>
              ) : (
                <input value={model} onChange={e => setModel(e.target.value)}
                  placeholder="e.g. Qwen3.8 or local-model" />
              )}
              <button
                className={`rmc-detect-btn ${detecting ? 'rmc-detect-btn--spin' : ''}`}
                onClick={detectModels}
                disabled={detecting}
                title="Auto-detect models from server"
              >
                {detecting ? '⟳' : '🔍'}
              </button>
            </div>
          </div>

          <div className="rmc-config-row">
            <label>MCP Server</label>
            <input value={mcpUrl} onChange={e => setMcpUrl(e.target.value)}
              placeholder="http://127.0.0.1:7654/sse" />
          </div>

          {/* Thinking — always visible */}
          <div className="rmc-config-row rmc-thinking-row">
            <label>🧠 Thinking</label>
            <div className="rmc-toggle-row">
              <label className={`rmc-toggle ${!canThink ? 'rmc-toggle--disabled' : ''}`}
                title={!canThink ? 'Enable thinking only works with Claude 3.7+, Qwen3, QwQ, DeepSeek-R1' : 'Enable extended thinking / reasoning'}>
                <input type="checkbox" checked={thinking && canThink}
                  disabled={!canThink}
                  onChange={e => setThinking(e.target.checked)} />
                <span className="rmc-toggle-slider" />
              </label>
              {thinking && canThink ? (
                <div className="rmc-config-row rmc-config-row--inline">
                  <label>Budget</label>
                  <input type="number" className="rmc-num-input" min={1000} max={100000} step={1000}
                    value={thinkBudget} onChange={e => setThinkBudget(Number(e.target.value))} />
                  <span className="rmc-hint-small">tokens</span>
                </div>
              ) : (
                <span className="rmc-hint-small">
                  {canThink ? 'Off' : 'Need: Claude 3.7+ / Qwen3 / QwQ / DeepSeek-R1'}
                </span>
              )}
            </div>
          </div>

          {/* Advanced toggle */}
          <button className="rmc-advanced-toggle" onClick={() => setShowAdvanced(v => !v)}>
            {showAdvanced ? '▲' : '▼'} Advanced options
          </button>

          {showAdvanced && (
            <div className="rmc-advanced">

              {/* Temperature */}
              <div className="rmc-config-row">
                <label>Temperature</label>
                <div className="rmc-slider-row">
                  <input type="range" min={0} max={2} step={0.1}
                    value={temperature} onChange={e => setTemperature(Number(e.target.value))} />
                  <span className="rmc-slider-val">{temperature.toFixed(1)}</span>
                </div>
              </div>

              {/* Max tokens */}
              <div className="rmc-config-row">
                <label>Max tokens</label>
                <select className="rmc-select-sm"
                  value={maxTokens} onChange={e => setMaxTokens(Number(e.target.value))}>
                  {[1024, 2048, 4096, 8192, 16384, 32768, 65536].map(v => (
                    <option key={v} value={v}>{v.toLocaleString()}</option>
                  ))}
                </select>
              </div>

              {/* Max tool steps */}
              <div className="rmc-config-row">
                <label>Max steps</label>
                <div className="rmc-slider-row">
                  <input type="range" min={1} max={30} step={1}
                    value={maxSteps} onChange={e => setMaxSteps(Number(e.target.value))} />
                  <span className="rmc-slider-val">{maxSteps}</span>
                </div>
              </div>

              {/* System prompt */}
              <div className="rmc-config-row rmc-config-row--tall">
                <label>System prompt</label>
                <textarea className="rmc-sys-prompt" rows={3}
                  placeholder="Leave empty to use Fade's default system prompt…"
                  value={systemPrompt} onChange={e => setSystemPrompt(e.target.value)} />
              </div>
            </div>
          )}

          <div className="rmc-config-footer">
            <span className="rmc-hint">
              Start MCP server:&nbsp;
              <code>python -m backend.ai.mcp_server --transport sse --port 7654</code>
            </span>
            <button className="rmc-btn rmc-btn-primary" onClick={saveConfig} disabled={saving}>
              {saving ? 'Saving…' : 'Save & Apply'}
            </button>
          </div>
        </div>
      )}

      {/* Chat area */}
      <div className="rmc-messages">
        {messages.length === 0 && (
          <div className="rmc-empty">
            <div className="rmc-empty-icon">🤖</div>
            <p>Connect to an LLM and start editing your timeline with natural language.</p>
            <p className="rmc-empty-sub">Try: <em>"Split the first clip at the halfway point"</em></p>
          </div>
        )}

        {messages.map(msg => (
          <div key={msg.id} className={`rmc-msg rmc-msg-${msg.role}`}>

            {msg.role === 'thinking' && (
              <details className="rmc-thinking">
                <summary>🧠 Thinking…</summary>
                <pre>{msg.content}</pre>
              </details>
            )}

            {msg.role === 'tool_call' && (
              <div className="rmc-tool-header">
                <span className="rmc-tool-icon">⚡</span>
                <span className="rmc-tool-name">{msg.tool}</span>
              </div>
            )}
            {msg.role === 'tool_result' && (
              <div className="rmc-tool-header">
                <span className="rmc-tool-icon">✓</span>
                <span className="rmc-tool-name">{msg.tool}</span>
              </div>
            )}
            {msg.role === 'error' && (
              <div className="rmc-tool-header">
                <span className="rmc-tool-icon">✗</span>
                <span className="rmc-tool-name">Error</span>
              </div>
            )}

            {msg.role !== 'thinking' && (
              <div className="rmc-msg-content">
                {msg.role === 'tool_call' || msg.role === 'tool_result'
                  ? <pre>{msg.content}</pre>
                  : <span>{msg.content || (busy && msg.role === 'assistant'
                      ? <span className="rmc-cursor">▌</span> : '')}</span>
                }
              </div>
            )}
          </div>
        ))}

        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="rmc-input-bar">
        <textarea className="rmc-input" value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={connected ? 'Tell the AI what to do… (Enter to send, Shift+Enter = newline)' : 'Connect first'}
          disabled={!connected || busy}
          rows={1}
        />
        {busy
          ? <button className="rmc-btn rmc-btn-stop" onClick={stopGeneration}>■ Stop</button>
          : <button className="rmc-btn rmc-btn-send" onClick={send} disabled={!connected || !input.trim()}>Send</button>
        }
      </div>
    </div>
  );
}
