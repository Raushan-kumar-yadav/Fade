import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useSelection } from '../../context/selectionContext';
import { inspectorApi, type ParamRow, type ClipParams } from '../../api/inspectorApi';
import './InspectorPanel.css';

// ── Keyframe diamond button (mirrors Qteee keyframeButton.qml) ────────────────

interface KeyframeBtnProps {
  paramId:     string;
  clipId:      string;
  frame:       number;
  isAnimated:  boolean;
  hasKf:       boolean;
  value:       number;
  onToggle:    () => void;
  onPrev:      () => void;
  onNext:      () => void;
}

function KeyframeBtn({ isAnimated, hasKf, onToggle, onPrev, onNext }: KeyframeBtnProps) {
  return (
    <div className="insp-kf-group">
      <button
        className="insp-kf-nav"
        disabled={!isAnimated}
        onClick={onPrev}
        title="Previous keyframe"
      >‹</button>

      <button
        className={`insp-kf-diamond${hasKf ? ' insp-kf-diamond--active' : ''}${isAnimated ? ' insp-kf-diamond--animated' : ''}`}
        onClick={onToggle}
        title={hasKf ? 'Remove keyframe' : 'Add keyframe'}
        aria-label={hasKf ? 'Remove keyframe' : 'Add keyframe'}
      >
        <svg width="10" height="10" viewBox="0 0 10 10">
          <polygon
            points="5,0 10,5 5,10 0,5"
            fill={hasKf ? '#6366f1' : (isAnimated ? '#374151' : 'none')}
            stroke={isAnimated ? '#6366f1' : '#374151'}
            strokeWidth="1.5"
          />
        </svg>
      </button>

      <button
        className="insp-kf-nav"
        disabled={!isAnimated}
        onClick={onNext}
        title="Next keyframe"
      >›</button>
    </div>
  );
}

// ── Single param row ────────────────────────────────────────────────────────

interface ParamRowProps {
  param:       ParamRow;
  clipId:      string;
  currentFrame: number;
  onChange:    (id: string, value: number) => void;
  onRefresh:   () => void;
}

function ParamRowWidget({ param, clipId, currentFrame, onChange, onRefresh }: ParamRowProps) {
  const [localVal, setLocalVal] = useState(param.value);
  const [editing,  setEditing]  = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Sync value from server
  useEffect(() => { setLocalVal(param.value); }, [param.value]);

  const handleSlider = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const v = parseFloat(e.target.value);
    setLocalVal(v);
  }, []);

  const handleSliderCommit = useCallback(async () => {
    await inspectorApi.setParam(clipId, param.id, localVal, -1);
    onChange(param.id, localVal);
  }, [clipId, param.id, localVal, onChange]);

  const handleNumberCommit = useCallback(async (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      const v = parseFloat((e.target as HTMLInputElement).value);
      if (!isNaN(v)) {
        const clamped = Math.max(param.min, Math.min(param.max, v));
        setLocalVal(clamped);
        await inspectorApi.setParam(clipId, param.id, clamped, -1);
        onChange(param.id, clamped);
        setEditing(false);
      }
    }
    if (e.key === 'Escape') setEditing(false);
  }, [clipId, param.id, param.min, param.max, onChange]);

  const handleKfToggle = useCallback(async () => {
    if (param.hasKeyframe) {
      await inspectorApi.removeKeyframe(clipId, param.id, currentFrame);
    } else {
      await inspectorApi.addKeyframe(clipId, param.id, {
        frame: currentFrame, value: localVal,
        interp: 'ease_both',
        handle_in_f: -5, handle_in_v: 0,
        handle_out_f: 5, handle_out_v: 0,
      });
    }
    onRefresh();
  }, [clipId, param.id, param.hasKeyframe, currentFrame, localVal, onRefresh]);

  const handleKfNav = useCallback(async (dir: 'prev' | 'next') => {
    // Jump to nearest keyframe in that direction
    const frames = param.keyframes;
    if (!frames.length) return;
    if (dir === 'prev') {
      const prev = [...frames].filter(f => f < currentFrame).pop();
      if (prev != null) window.dispatchEvent(new CustomEvent('fade:seek', { detail: prev }));
    } else {
      const next = frames.find(f => f > currentFrame);
      if (next != null) window.dispatchEvent(new CustomEvent('fade:seek', { detail: next }));
    }
  }, [param.keyframes, currentFrame]);

  const pct = ((localVal - param.min) / (param.max - param.min)) * 100;

  return (
    <div className={`insp-row${param.isAnimated ? ' insp-row--animated' : ''}`}>
      {/* Keyframe controls */}
      <KeyframeBtn
        paramId={param.id}
        clipId={clipId}
        frame={currentFrame}
        isAnimated={param.isAnimated}
        hasKf={param.hasKeyframe}
        value={localVal}
        onToggle={handleKfToggle}
        onPrev={() => handleKfNav('prev')}
        onNext={() => handleKfNav('next')}
      />

      {/* Label */}
      <span className="insp-row__label" title={param.id}>{param.label}</span>

      {/* Slider */}
      <div className="insp-row__slider-wrap">
        <div className="insp-row__slider-track">
          <div className="insp-row__slider-fill" style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
        </div>
        <input
          type="range"
          className="insp-row__slider"
          min={param.min}
          max={param.max}
          step={(param.max - param.min) / 1000}
          value={localVal}
          onChange={handleSlider}
          onMouseUp={handleSliderCommit}
          onTouchEnd={handleSliderCommit}
          aria-label={param.label}
        />

        {/* Keyframe markers on slider */}
        {param.isAnimated && param.keyframes.map(kf => (
          <div
            key={kf}
            className={`insp-row__kf-marker${kf === currentFrame ? ' insp-row__kf-marker--current' : ''}`}
            style={{ left: `${((kf - 0) / (param.max - param.min)) * 100}%` }}
            title={`Keyframe @ frame ${kf}`}
          />
        ))}
      </div>

      {/* Numeric input */}
      {editing ? (
        <input
          ref={inputRef}
          type="number"
          className="insp-row__num-input"
          defaultValue={localVal.toFixed(2)}
          onKeyDown={handleNumberCommit}
          onBlur={() => setEditing(false)}
          autoFocus
          step="any"
        />
      ) : (
        <button
          className="insp-row__val"
          onClick={() => setEditing(true)}
          title="Click to enter value"
          tabIndex={0}
        >
          {localVal.toFixed(localVal % 1 === 0 ? 0 : 2)}
        </button>
      )}
    </div>
  );
}

// ── Group header ────────────────────────────────────────────────────────────

function GroupHeader({ label, open, onToggle }: { label: string; open: boolean; onToggle: () => void }) {
  return (
    <button className="insp-group-header" onClick={onToggle}>
      <span className={`insp-group-header__arrow${open ? ' open' : ''}`}>▶</span>
      {label}
    </button>
  );
}

// ── Main Inspector Panel ────────────────────────────────────────────────────

export default function InspectorPanel() {
  const { selected }         = useSelection();
  const [data, setData]      = useState<ClipParams | null>(null);
  const [currentFrame, setCF] = useState(0);
  const [loading, setLoading] = useState(false);
  const [groups, setGroups]   = useState<Record<string, boolean>>({});

  // Follow the global playhead
  useEffect(() => {
    const handler = (e: Event) => {
      setCF((e as CustomEvent<number>).detail);
    };
    window.addEventListener('fade:frame', handler);
    window.addEventListener('fade:seek',  handler);
    return () => {
      window.removeEventListener('fade:frame', handler);
      window.removeEventListener('fade:seek',  handler);
    };
  }, []);

  const refresh = useCallback(async () => {
    if (!selected) { setData(null); return; }
    setLoading(true);
    try {
      const d = await inspectorApi.getParams(selected.clipId, currentFrame);
      setData(d);
      // Auto-open all groups on first load
      setGroups(prev => {
        const next = { ...prev };
        const groupNames = [...new Set(d.params.map(p => p.group))];
        groupNames.forEach(g => { if (!(g in next)) next[g] = true; });
        return next;
      });
    } catch (err) {
      console.error('[Inspector] fetch error', err);
    } finally {
      setLoading(false);
    }
  }, [selected, currentFrame]);

  // Refresh when selection or frame changes
  useEffect(() => { refresh(); }, [selected?.clipId, currentFrame]);

  const handleParamChange = useCallback((_id: string, _val: number) => {
    // Optimistic: update local data
    setData(prev => {
      if (!prev) return prev;
      return {
        ...prev,
        params: prev.params.map(p => p.id === _id ? { ...p, value: _val } : p),
      };
    });
  }, []);

  // Group params
  const grouped = useMemo(() => {
    if (!data) return {};
    const map: Record<string, ParamRow[]> = {};
    data.params.forEach(p => {
      if (!map[p.group]) map[p.group] = [];
      map[p.group].push(p);
    });
    return map;
  }, [data]);

  // ── Empty state ───────────────────────────────────────────────────────────

  if (!selected) {
    return (
      <div className="insp-empty">
        <div className="insp-empty__icon">⬚</div>
        <div className="insp-empty__text">Select a clip to inspect</div>
      </div>
    );
  }

  // ── Loading ───────────────────────────────────────────────────────────────

  if (loading && !data) {
    return (
      <div className="insp-empty">
        <div className="insp-empty__spinner" />
        <div className="insp-empty__text">Loading…</div>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="insp-root">
      {/* Clip header */}
      <div className="insp-clip-header">
        <div className="insp-clip-header__badge">{data.clipType.replace('Clip', '')}</div>
        <div className="insp-clip-header__name">{selected.clipName}</div>
        <div className="insp-clip-header__meta">
          {data.duration} fr @ track {selected.trackIndex + 1}
        </div>
      </div>

      {/* Param groups */}
      <div className="insp-groups">
        {Object.entries(grouped).map(([group, params]) => (
          <div key={group} className="insp-group">
            <GroupHeader
              label={group}
              open={groups[group] ?? true}
              onToggle={() => setGroups(prev => ({ ...prev, [group]: !prev[group] }))}
            />
            {(groups[group] ?? true) && (
              <div className="insp-group__body">
                {params.map(p => (
                  <ParamRowWidget
                    key={p.id}
                    param={p}
                    clipId={data.clipId}
                    currentFrame={currentFrame}
                    onChange={handleParamChange}
                    onRefresh={refresh}
                  />
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
