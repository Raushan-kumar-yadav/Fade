import React, { useState, useCallback, useRef, useEffect } from 'react';
import {
  useTool, type ActiveTool, type PenSubMode, isShapeTool, isPenTool,
} from '../../context/toolContext';
import './ToolboxWidget.css';

// ── Tool definitions ──────────────────────────────────────────────────────────

interface ToolDef {
  id:       ActiveTool;
  icon:     string;
  label:    string;
  shortcut: string;
  group?:   'edit' | 'create';
}

const EDIT_TOOLS: ToolDef[] = [
  { id: 'pointer',  icon: '↖',  label: 'Select',  shortcut: 'V', group: 'edit' },
  { id: 'razor',    icon: '✂',  label: 'Razor',   shortcut: 'C', group: 'edit' },
  { id: 'ripple',   icon: '⊳⊲', label: 'Ripple',  shortcut: 'R', group: 'edit' },
  { id: 'slip',     icon: '⇄',  label: 'Slip',    shortcut: 'Y', group: 'edit' },
  { id: 'hand',     icon: '✋', label: 'Pan',      shortcut: 'H', group: 'edit' },
];

const CREATE_TOOLS: ToolDef[] = [
  { id: 'text',       icon: 'T',  label: 'Text',        shortcut: 'T', group: 'create' },
  { id: 'solid',      icon: '■',  label: 'Solid Color', shortcut: 'O', group: 'create' },
  { id: 'adjustment', icon: '⚙', label: 'Adjustment',  shortcut: 'A', group: 'create' },
];

const SHAPE_SUBTOOLS: ToolDef[] = [
  { id: 'shape:rect',    icon: '▬', label: 'Rectangle', shortcut: '' },
  { id: 'shape:circle',  icon: '●', label: 'Circle',    shortcut: '' },
  { id: 'shape:ellipse', icon: '⬭', label: 'Ellipse',   shortcut: '' },
  { id: 'shape:star',    icon: '★', label: 'Star',       shortcut: '' },
  { id: 'shape:polygon', icon: '⬡', label: 'Polygon',   shortcut: '' },
  { id: 'shape:line',    icon: '╱', label: 'Line',       shortcut: '' },
  { id: 'shape:arc',     icon: '⌒', label: 'Arc',        shortcut: '' },
  { id: 'shape:path',    icon: '✏', label: 'Pen Path',   shortcut: 'P' },
];

// ── Pen sub-tool definitions ──────────────────────────────────────────────────

interface PenSubDef {
  id:      PenSubMode;
  icon:    string;
  label:   string;
  key:     string;
}

const PEN_SUBTOOLS: PenSubDef[] = [
  { id: 'pen:add',    icon: '✏',  label: 'Add Point',     key: 'a' },
  { id: 'pen:select', icon: '↖',  label: 'Select/Move',   key: 's' },
  { id: 'pen:handle', icon: '◉',  label: 'Edit Handles',  key: 'h' },
  { id: 'pen:delete', icon: '✕',  label: 'Delete Point',  key: 'd' },
  { id: 'pen:curve',  icon: '⧖',  label: 'Toggle Corner', key: 'g' },
];

// ── Shape flyout ──────────────────────────────────────────────────────────────

function ShapeFlyout({
  current, onSelect, onClose,
}: { current: ActiveTool; onSelect: (t: ActiveTool) => void; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    setTimeout(() => document.addEventListener('mousedown', handler), 10);
    return () => document.removeEventListener('mousedown', handler);
  }, [onClose]);

  return (
    <div className="tbx-flyout" ref={ref} role="menu" aria-label="Shape sub-tools">
      <div className="tbx-flyout__title">Shapes</div>
      {SHAPE_SUBTOOLS.map(s => (
        <button
          key={s.id}
          id={`tbx-${s.id}`}
          role="menuitem"
          className={`tbx-flyout__item${current === s.id ? ' tbx-flyout__item--active' : ''}`}
          onClick={() => { onSelect(s.id); onClose(); }}
          title={s.label + (s.shortcut ? ` (${s.shortcut})` : '')}
        >
          <span className="tbx-flyout__icon">{s.icon}</span>
          <span className="tbx-flyout__label">{s.label}</span>
          {s.shortcut && <span className="tbx-flyout__key">{s.shortcut}</span>}
        </button>
      ))}
    </div>
  );
}

// ── Pen Sub-tool Panel ────────────────────────────────────────────────────────

function PenSubPanel() {
  const { penSubMode, setPenSubMode, penOutputMode, setPenOutputMode } = useTool();

  return (
    <div className="tbx-pen-panel">
      <div className="tbx-group__label">Pen Mode</div>

      {/* Sub-tool buttons */}
      <div className="tbx-pen-subtools">
        {PEN_SUBTOOLS.map(sub => (
          <button
            key={sub.id}
            id={`tbx-pen-${sub.id.replace('pen:', '')}`}
            className={`tbx-pen-btn${penSubMode === sub.id ? ' tbx-pen-btn--active' : ''}`}
            title={`${sub.label} (${sub.key.toUpperCase()})`}
            onClick={() => setPenSubMode(sub.id)}
            aria-pressed={penSubMode === sub.id}
          >
            <span className="tbx-pen-btn__icon">{sub.icon}</span>
            <span className="tbx-pen-btn__label">{sub.label}</span>
            <span className="tbx-pen-btn__key">{sub.key.toUpperCase()}</span>
          </button>
        ))}
      </div>

      <div className="tbx-pen-divider" />

      {/* Output mode toggle */}
      <div className="tbx-group__label">Output</div>
      <div className="tbx-pen-output">
        <button
          id="tbx-pen-output-clip"
          className={`tbx-pen-output-btn${penOutputMode === 'clip' ? ' active' : ''}`}
          onClick={() => setPenOutputMode('clip')}
          title="Create a new Pen Clip on the timeline"
        >
          ✏ Add Clip
        </button>
        <button
          id="tbx-pen-output-mask"
          className={`tbx-pen-output-btn${penOutputMode === 'mask' ? ' active' : ''}`}
          onClick={() => setPenOutputMode('mask')}
          title="Add as Mask on the selected clip"
        >
          ⊖ Add Mask
        </button>
      </div>
    </div>
  );
}

// ── Single tool button ────────────────────────────────────────────────────────

function ToolBtn({
  tool, active, onClick, children,
}: { tool: ToolDef; active: boolean; onClick: () => void; children?: React.ReactNode }) {
  return (
    <button
      id={`tbx-tool-${tool.id.replace(':', '-')}`}
      className={`tbx-btn${active ? ' tbx-btn--active' : ''}`}
      title={`${tool.label}${tool.shortcut ? ` (${tool.shortcut})` : ''}`}
      onClick={onClick}
      aria-pressed={active}
    >
      <span className="tbx-btn__icon">{tool.icon}</span>
      {tool.shortcut && <span className="tbx-btn__key">{tool.shortcut}</span>}
      {children}
    </button>
  );
}

// ── ToolboxWidget (dockable) ──────────────────────────────────────────────────

interface Props {
  docked?:  boolean;
  onClose?: () => void;
}

export default function ToolboxWidget({ docked = false, onClose }: Props) {
  const {
    activeTool, setTool, lastShapeTool, setLastShape,
    penSubMode, setPenSubMode,
  } = useTool();
  const [showShapeFlyout, setShowShapeFlyout] = useState(false);

  const [pos, setPos]   = useState({ x: 8, y: 96 });
  const dragRef         = useRef<{ startX: number; startY: number; ox: number; oy: number } | null>(null);
  const boxRef          = useRef<HTMLDivElement>(null);

  const onHeaderMouseDown = useCallback((e: React.MouseEvent) => {
    if (docked) return;
    dragRef.current = { startX: e.clientX, startY: e.clientY, ox: pos.x, oy: pos.y };
    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return;
      setPos({
        x: Math.max(0, dragRef.current.ox + ev.clientX - dragRef.current.startX),
        y: Math.max(0, dragRef.current.oy + ev.clientY - dragRef.current.startY),
      });
    };
    const onUp = () => {
      dragRef.current = null;
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }, [docked, pos]);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).matches('input,textarea,select')) return;
      // Main tool shortcuts
      const toolMap: Record<string, ActiveTool> = {
        v: 'pointer', c: 'razor', r: 'ripple', y: 'slip', h: 'hand',
        t: 'text',    o: 'solid', a: 'adjustment',
        q: lastShapeTool, p: 'shape:path',
      };
      const tool = toolMap[e.key.toLowerCase()];
      if (tool) { e.preventDefault(); setTool(tool); }

      // Pen sub-mode shortcuts (only when pen is active)
      if (isPenTool(activeTool)) {
        const penMap: Record<string, PenSubMode> = {
          a: 'pen:add', s: 'pen:select', h: 'pen:handle', d: 'pen:delete', g: 'pen:curve',
        };
        const sub = penMap[e.key.toLowerCase()];
        if (sub) { e.preventDefault(); setPenSubMode(sub); }
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [setTool, lastShapeTool, activeTool, setPenSubMode]);

  const handleShapeClick = useCallback(() => {
    if (isShapeTool(activeTool)) {
      setShowShapeFlyout(f => !f);
    } else {
      setTool(lastShapeTool);
    }
  }, [activeTool, lastShapeTool, setTool]);

  const handleShapeSelect = useCallback((t: ActiveTool) => {
    setTool(t);
    setLastShape(t);
  }, [setTool, setLastShape]);

  const currentShapeDef = SHAPE_SUBTOOLS.find(s => s.id === lastShapeTool) ?? SHAPE_SUBTOOLS[0];

  const content = (
    <>
      {/* Drag handle / header */}
      <div className="tbx-header" onMouseDown={onHeaderMouseDown}>
        <span className="tbx-header__label">Tools</span>
        {!docked && onClose && (
          <button className="tbx-header__close" onClick={onClose} title="Close">×</button>
        )}
      </div>

      {/* Edit tools group */}
      <div className="tbx-group">
        <div className="tbx-group__label">Edit</div>
        {EDIT_TOOLS.map(t => (
          <ToolBtn key={t.id} tool={t} active={activeTool === t.id} onClick={() => setTool(t.id)} />
        ))}
      </div>

      <div className="tbx-divider" />

      {/* Create tools group */}
      <div className="tbx-group">
        <div className="tbx-group__label">Create</div>
        {CREATE_TOOLS.map(t => (
          <ToolBtn key={t.id} tool={t} active={activeTool === t.id} onClick={() => setTool(t.id)} />
        ))}

        {/* Shape flyout button — mirrors Qteee QToolButton::MenuButtonPopup */}
        <div className="tbx-shape-wrap" style={{ position: 'relative' }}>
          <div className={`tbx-btn tbx-btn--shape${isShapeTool(activeTool) ? ' tbx-btn--active' : ''}`}>
            <button
              id="tbx-shape-main"
              className="tbx-shape-main"
              title={`Shape: ${currentShapeDef.label} (Q)`}
              onClick={handleShapeClick}
              aria-pressed={isShapeTool(activeTool)}
            >
              <span className="tbx-btn__icon">{currentShapeDef.icon}</span>
              <span className="tbx-btn__key">Q</span>
            </button>
            <button
              id="tbx-shape-arrow"
              className="tbx-shape-arrow"
              title="Choose shape type"
              onClick={() => setShowShapeFlyout(f => !f)}
              aria-haspopup="true"
              aria-expanded={showShapeFlyout}
            >
              ▾
            </button>
          </div>

          {showShapeFlyout && (
            <ShapeFlyout
              current={lastShapeTool}
              onSelect={handleShapeSelect}
              onClose={() => setShowShapeFlyout(false)}
            />
          )}
        </div>
      </div>

      {/* Pen sub-tool panel — only when pen tool is active */}
      {isPenTool(activeTool) && (
        <>
          <div className="tbx-divider" />
          <PenSubPanel />
        </>
      )}
    </>
  );

  if (docked) {
    return <div ref={boxRef} className="tbx-docked">{content}</div>;
  }

  return (
    <div
      ref={boxRef}
      className="tbx-floating"
      style={{ left: pos.x, top: pos.y }}
      role="toolbar"
      aria-label="Tools"
    >
      {content}
    </div>
  );
}
