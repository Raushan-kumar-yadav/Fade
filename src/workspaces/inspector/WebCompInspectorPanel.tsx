 

import React, { useState, useEffect, useCallback, useRef } from 'react';
import './WebCompInspectorPanel.css';

/* Types */

interface WebCompMeta {
  assetId: string; name: string; folderPath: string;
  width: number; height: number; fps: number; durationFrames: number;
}
interface ParamDef {
  id: string; label: string;
  type: 'string' | 'number' | 'color' | 'boolean';
  default: string | number | boolean;
}
interface WebCompClipInfo {
  webcompId: string; mediaOffset: number;
  runtimeParams: Record<string, any>;
  meta: WebCompMeta | null; params: ParamDef[];
}

/* API */

function base() { return `http://127.0.0.1:${(window as any).__FADE_PORT__ ?? 8000}`; }

async function fetchInfo(clipId: string): Promise<WebCompClipInfo | null> {
  try {
    const r = await fetch(`${base()}/timeline/webcomp/clip-info?clipId=${clipId}`);
    return r.ok ? r.json() : null;
  } catch { return null; }
}

async function patchParams(clipId: string, webcompId: string, params: Record<string, any>) {
  // Signal the prefetch loop to pause and discard in-flight captures
  window.dispatchEvent(new CustomEvent('fade:webcomp-params-changed', {
    detail: { webcompId },
  }));

  await fetch(`${base()}/timeline/webcomp/runtime-params`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ clipId, params }),
  });
  // Push live to the offscreen window (after backend is updated)
  (window as any).electronAPI?.webcompUpdateParams?.(webcompId, params);
}

/* Sub-components */

function SectionHeader({ label, open, onToggle }: { label: string; open: boolean; onToggle: () => void }) {
  return (
    <button className="wci-section-hdr" onClick={onToggle}>
      <span className="wci-section-hdr__arrow">{open ? '▾' : '▸'}</span>
      <span className="wci-section-hdr__label">{label}</span>
    </button>
  );
}

function ParamEditor({ def, value, onChange }: {
  def: ParamDef; value: any; onChange: (id: string, val: any) => void;
}) {
  const [localStr, setLocalStr] = useState(String(value ?? def.default));
  useEffect(() => { setLocalStr(String(value ?? def.default)); }, [value, def.default]);
  const commit = () => {
    if (def.type === 'number') onChange(def.id, parseFloat(localStr) || 0);
    else onChange(def.id, localStr);
  };
  return (
    <div className="wci-param">
      <label className="wci-param__label">{def.label}</label>
      <div className="wci-param__ctrl">
        {def.type === 'boolean' && (
          <label className="wci-toggle">
            <input type="checkbox" checked={!!value}
              onChange={e => onChange(def.id, e.target.checked)} />
            <span className="wci-toggle__track" />
          </label>
        )}
        {def.type === 'color' && (
          <div className="wci-color-wrap">
            <input type="color" className="wci-color"
              value={typeof value === 'string' ? value : '#667eea'}
              onChange={e => onChange(def.id, e.target.value)} />
            <span className="wci-color__hex">
              {typeof value === 'string' ? value.toUpperCase() : '#667EEA'}
            </span>
          </div>
        )}
        {(def.type === 'string' || def.type === 'number') && (
          <input className="wci-param__input"
            type={def.type === 'number' ? 'number' : 'text'}
            value={localStr}
            onChange={e => setLocalStr(e.target.value)}
            onBlur={commit}
            onKeyDown={e => { if (e.key === 'Enter') commit(); }}
          />
        )}
      </div>
    </div>
  );
}

/* Main */

interface Props {
  clipId: string; clipName: string;
  trackIndex: number; startFrame: number; duration: number;
}

export default function WebCompInspectorPanel({
  clipId, clipName, trackIndex, startFrame, duration,
}: Props) {
  const [info, setInfo]       = useState<WebCompClipInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [params, setParams]   = useState<Record<string, any>>({});
  const [saving, setSaving]   = useState(false);
  const [dirty, setDirty]     = useState(false);
  const [openPrm, setOpenPrm] = useState(true);
  const [openSrc, setOpenSrc] = useState(false);
  const [openRaw, setOpenRaw] = useState(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  /* Load */
  const load = useCallback(async () => {
    setLoading(true);
    const d = await fetchInfo(clipId);
    if (d) { setInfo(d); setParams(d.runtimeParams ?? {}); }
    setLoading(false);
  }, [clipId]);

  useEffect(() => { load(); }, [load]);

  /* Param change — debounce 500ms */
  const handleParamChange = useCallback((id: string, val: any) => {
    setParams(p => {
      const next = { ...p, [id]: val };
      setDirty(true);
      if (saveTimer.current) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(async () => {
        setSaving(true);
        await patchParams(clipId, info?.webcompId ?? '', next);
        setSaving(false);
        setDirty(false);
      }, 500);
      return next;
    });
  }, [clipId, info?.webcompId]);

  const handleReload = useCallback(() => {
    (window as any).electronAPI?.webcompReload?.(info?.webcompId ?? '');
  }, [info?.webcompId]);

  const handleOpenFolder = useCallback(() => {
    if (info?.meta?.folderPath)
      (window as any).electronAPI?.shellOpenPath?.(info.meta.folderPath);
  }, [info?.meta?.folderPath]);

  /* ── Render ── */
  if (loading) return <div className="wci-root"><div className="wci-spinner" /></div>;
  if (!info)   return <div className="wci-root"><div className="wci-empty">WebComp not found</div></div>;

  const { meta, params: paramDefs, webcompId } = info;

  return (
    <div className="wci-root">

      {/* Header */}
      <div className="wci-header">
        <div className="wci-header__badge">
          <svg width="12" height="12" viewBox="0 0 48 48" fill="none">
            <rect x="4"  y="4"  width="18" height="18" rx="3" fill="#a78bfa" opacity="0.8"/>
            <rect x="26" y="4"  width="18" height="18" rx="3" fill="#a78bfa" opacity="0.5"/>
            <rect x="4"  y="26" width="18" height="18" rx="3" fill="#a78bfa" opacity="0.5"/>
            <rect x="26" y="26" width="18" height="18" rx="3" fill="#a78bfa" opacity="0.3"/>
          </svg>
          WebComp
        </div>
        <div className="wci-header__name" title={clipName}>{clipName || meta?.name || 'Untitled'}</div>
        <div className="wci-header__meta">
          {duration} fr · start {startFrame} · track {trackIndex + 1}
        </div>
      </div>

      {/* Actions */}
      <div className="wci-actions">
        <button className="wci-action-btn" onClick={handleReload} title="Reload offscreen window">↺ Reload</button>
        <button className="wci-action-btn" onClick={handleOpenFolder} title="Open folder">📁 Folder</button>
        {saving && <span className="wci-saving">Saving…</span>}
        {!saving && dirty && <span className="wci-dirty">●</span>}
      </div>

      {/* Note: Transform (position/scale/rotation/opacity/blend) params are rendered
          by the parent InspectorPanel exactly like video/shape clips.
          This panel only shows WebComp-specific extras below. */}

      {/* Runtime params from webcomp.json schema */}
      {paramDefs.length > 0 && (
        <>
          <SectionHeader
            label={`Params (${paramDefs.length})`}
            open={openPrm}
            onToggle={() => setOpenPrm(o => !o)}
          />
          {openPrm && (
            <div className="wci-section-body">
              {paramDefs.map(def => (
                <ParamEditor key={def.id} def={def}
                  value={params[def.id] ?? def.default}
                  onChange={handleParamChange}
                />
              ))}
            </div>
          )}
        </>
      )}

      {/* Freeform JSON fallback if no schema */}
      {paramDefs.length === 0 && (
        <>
          <SectionHeader label="Runtime Params (JSON)" open={openRaw}
            onToggle={() => setOpenRaw(o => !o)} />
          {openRaw && (
            <div className="wci-section-body">
              <FreeformJsonEditor
                value={params}
                onChange={next => {
                  setParams(next); setDirty(true);
                  patchParams(clipId, webcompId, next);
                }}
              />
            </div>
          )}
        </>
      )}

      {/* Source info */}
      <SectionHeader label="Source" open={openSrc}
        onToggle={() => setOpenSrc(o => !o)} />
      {openSrc && (
        <div className="wci-section-body">
          <div className="wci-kv">
            <span className="wci-kv__key">Folder</span>
            <span className="wci-kv__val wci-kv__val--mono" title={meta?.folderPath}>
              {meta?.folderPath ? meta.folderPath.split(/[\\/]/).slice(-2).join('/') : '—'}
            </span>
          </div>
          <div className="wci-kv">
            <span className="wci-kv__key">Resolution</span>
            <span className="wci-kv__val">{meta?.width ?? 1920} × {meta?.height ?? 1080}</span>
          </div>
          <div className="wci-kv">
            <span className="wci-kv__key">FPS</span>
            <span className="wci-kv__val">{meta?.fps ?? 30}</span>
          </div>
          <div className="wci-kv">
            <span className="wci-kv__key">Native Dur.</span>
            <span className="wci-kv__val">{meta?.durationFrames ?? '—'} fr</span>
          </div>
          <div className="wci-kv">
            <span className="wci-kv__key">Offset</span>
            <span className="wci-kv__val">{info.mediaOffset} fr</span>
          </div>
        </div>
      )}
    </div>
  );
}

/* Freeform JSON editor */
function FreeformJsonEditor({ value, onChange }: {
  value: Record<string, any>; onChange: (v: Record<string, any>) => void;
}) {
  const [text, setText] = useState(JSON.stringify(value, null, 2));
  const [err, setErr]   = useState('');
  useEffect(() => { setText(JSON.stringify(value, null, 2)); }, [value]);
  const commit = () => {
    try { setErr(''); onChange(JSON.parse(text)); }
    catch (e: any) { setErr(e.message); }
  };
  return (
    <div className="wci-json">
      <textarea className={`wci-json__area${err ? ' wci-json__area--error' : ''}`}
        value={text} onChange={e => setText(e.target.value)}
        onBlur={commit} rows={8} spellCheck={false} />
      {err && <div className="wci-json__error">{err}</div>}
      <button className="wci-json__apply" onClick={commit}>Apply</button>
    </div>
  );
}
