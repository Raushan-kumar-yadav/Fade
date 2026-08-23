import { useState, useRef, useEffect, useCallback } from 'react';
import type { ActiveTool } from '../context/toolContext';
import WorkerProgress from '../workspaces/worker/WorkerProgress';
import { saveProject, saveProjectTo, loadProject, newProject } from '../api/projectApi';
import './TitleBar.css';
import '../workspaces/tools/ToolPanels.css';

interface ElectronAPI {
  minimize: () => void;
  maximize: () => void;
  close:    () => void;
}

declare global {
  interface Window { electronAPI?: ElectronAPI }
}

const TABS = [
  { id: 'home',   label: 'Home'   },
  { id: 'ai',     label: 'AI'     },
  { id: 'video',  label: 'Video'  },
  { id: 'audio',  label: 'Audio'  },
  { id: 'export', label: 'Export' },
];

// ── Minimal dropdown ────────────────────────────────────────────────────────

interface MenuItem {
  label?:    string;
  shortcut?: string;
  sep?:      boolean;
  action?:   () => void;
}

function MenuButton({ label, items }: { label: string; items: MenuItem[] }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  return (
    <div className="tb-menu" ref={ref}>
      <button
        className={`tb-menu__btn${open ? ' tb-menu__btn--open' : ''}`}
        onClick={() => setOpen(o => !o)}
      >
        {label}
      </button>
      {open && (
        <div className="tb-menu__dropdown">
          {items.map((item, i) =>
            item.sep ? (
              <div key={i} className="tb-menu__sep" />
            ) : (
              <button
                key={i}
                className="tb-menu__item"
                onClick={() => { item.action?.(); setOpen(false); }}
              >
                <span>{item.label}</span>
                {item.shortcut && <span className="tb-menu__shortcut">{item.shortcut}</span>}
              </button>
            )
          )}
        </div>
      )}
    </div>
  );
}

// ── TitleBar ────────────────────────────────────────────────────────────────

// ActiveTool re-exported for backwards-compat with App.tsx
export type { ActiveTool } from '../context/toolContext';

interface TitleBarProps {
  active:             string;
  onTab:              (id: string) => void;
  onSettings:         () => void;
  activeTool?:        ActiveTool;
  onTool?:            (t: ActiveTool) => void;
  onToggleToolbox?:   () => void;
  toolboxOpen?:       boolean;
  /** Called after a project is loaded so the app can refresh the timeline */
  onProjectLoaded?:   (result: { project: any; timeline: any }) => void;
}

export default function TitleBar({
  active, onTab, onSettings,
  activeTool = 'pointer', onTool,
  onToggleToolbox, toolboxOpen,
  onProjectLoaded,
}: TitleBarProps) {
  const api = window.electronAPI;

  // Track the currently saved path so Ctrl+S can overwrite without re-asking
  const savedPathRef = useRef<string | null>(null);
  const [projectName, setProjectName] = useState('Untitled Project');

  // ── Actions ─────────────────────────────────────────────────────────────────

  const handleNew = useCallback(async () => {
    const proj = await newProject({ name: 'Untitled Project' });
    if (proj) {
      savedPathRef.current = null;
      setProjectName(proj.name);
    }
  }, []);

  const handleSave = useCallback(async () => {
    if (savedPathRef.current) {
      await saveProjectTo(savedPathRef.current);
    } else {
      const fp = await saveProject(projectName);
      if (fp) {
        savedPathRef.current = fp;
        const name = fp.split(/[\\/]/).pop()?.replace(/\.fade$/, '') ?? projectName;
        setProjectName(name);
      }
    }
  }, [projectName]);

  const handleSaveAs = useCallback(async () => {
    const fp = await saveProject(projectName);
    if (fp) {
      savedPathRef.current = fp;
      const name = fp.split(/[\\/]/).pop()?.replace(/\.fade$/, '') ?? projectName;
      setProjectName(name);
    }
  }, [projectName]);

  const handleOpen = useCallback(async () => {
    const result = await loadProject();
    if (result) {
      savedPathRef.current = result.project.filePath ?? null;
      setProjectName(result.project.name);
      onProjectLoaded?.(result);
    }
  }, [onProjectLoaded]);

  // ── Keyboard shortcuts ───────────────────────────────────────────────────────

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!e.ctrlKey && !e.metaKey) return;
      switch (e.key.toLowerCase()) {
        case 'n': e.preventDefault(); handleNew();   break;
        case 'o': e.preventDefault(); handleOpen();  break;
        case 's': e.preventDefault(); handleSave();  break;
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [handleNew, handleOpen, handleSave]);

  // ── Menu items ───────────────────────────────────────────────────────────────

  const fileItems: MenuItem[] = [
    { label: 'New Project',   shortcut: 'Ctrl+N',       action: handleNew },
    { label: 'Open Project…', shortcut: 'Ctrl+O',       action: handleOpen },
    { label: 'Save Project',  shortcut: 'Ctrl+S',       action: handleSave },
    { label: 'Save As…',      shortcut: 'Ctrl+Shift+S', action: handleSaveAs },
    { sep: true },
    { label: 'Import Media',  shortcut: 'Ctrl+I',       action: () => {} },
    { sep: true },
    { label: 'Quit',          shortcut: 'Alt+F4',       action: () => api?.close() },
  ];

  const editItems: MenuItem[] = [
    { label: 'Undo',        shortcut: 'Ctrl+Z', action: () => {} },
    { label: 'Redo',        shortcut: 'Ctrl+Y', action: () => {} },
    { sep: true },
    { label: 'Cut',         shortcut: 'Ctrl+X', action: () => {} },
    { label: 'Copy',        shortcut: 'Ctrl+C', action: () => {} },
    { label: 'Paste',       shortcut: 'Ctrl+V', action: () => {} },
    { sep: true },
    { label: 'Split Clip',  shortcut: 'S',      action: () => {} },
    { label: 'Delete Clip', shortcut: 'Del',    action: () => {} },
  ];

  return (
    <div className="titlebar">
      {/* Left: Logo + menus + tool buttons */}
      <div className="titlebar__left">
        <div className="titlebar__logo">
          <div className="titlebar__logo-dot" />
          <span>FADE</span>
        </div>
        <div className="titlebar__menus">
          <MenuButton label="File"  items={fileItems} />
          <MenuButton label="Edit"  items={editItems} />
          <button className="tb-menu__btn" onClick={onSettings}>Settings</button>
        </div>

        {/* Toolbox toggle + Tasks indicator — only on Video tab */}
        {active === 'video' && (
          <div className="tb-tool-group">
            <button
              id="tb-toolbox-toggle"
              className={`tb-tool-btn${toolboxOpen ? ' tb-tool-btn--active' : ''}`}
              title="Toggle Toolbox (§)"
              onClick={onToggleToolbox}
            >
              <span style={{ fontSize: 13 }}>⊞</span>
              <span className="tb-tool-btn__tip">Toolbox</span>
            </button>
            <WorkerProgress />
          </div>
        )}
      </div>

      {/* Centre: project name + workspace tabs */}
      <div className="titlebar__tabs">
        {/* Unsaved indicator dot */}
        <span
          className="titlebar__project-name"
          title={savedPathRef.current ?? 'Unsaved — press Ctrl+S to save'}
        >
          {projectName}{!savedPathRef.current ? ' •' : ''}
        </span>
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            className={`titlebar__tab${active === id ? ' titlebar__tab--active' : ''}`}
            onClick={() => onTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Right: window controls */}
      <div className="titlebar__controls">
        <button className="wbtn wbtn--min"   onClick={() => api?.minimize()} />
        <button className="wbtn wbtn--max"   onClick={() => api?.maximize()} />
        <button className="wbtn wbtn--close" onClick={() => api?.close()}    />
      </div>
    </div>
  );
}
