import { useState, useRef, useEffect } from 'react';
import './TitleBar.css';

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

interface TitleBarProps {
  active:        string;
  onTab:         (id: string) => void;
  onSettings:    () => void;
}

export default function TitleBar({ active, onTab, onSettings }: TitleBarProps) {
  const api = window.electronAPI;

  const fileItems: MenuItem[] = [
    { label: 'New Project',   shortcut: 'Ctrl+N', action: () => {} },
    { label: 'Open Project',  shortcut: 'Ctrl+O', action: () => {} },
    { label: 'Save Project',  shortcut: 'Ctrl+S', action: () => {} },
    { sep: true },
    { label: 'Import Media',  shortcut: 'Ctrl+I', action: () => {} },
    { sep: true },
    { label: 'Quit',          shortcut: 'Alt+F4', action: () => api?.close() },
  ];

  const editItems: MenuItem[] = [
    { label: 'Undo',          shortcut: 'Ctrl+Z', action: () => {} },
    { label: 'Redo',          shortcut: 'Ctrl+Y', action: () => {} },
    { sep: true },
    { label: 'Cut',           shortcut: 'Ctrl+X', action: () => {} },
    { label: 'Copy',          shortcut: 'Ctrl+C', action: () => {} },
    { label: 'Paste',         shortcut: 'Ctrl+V', action: () => {} },
    { sep: true },
    { label: 'Split Clip',    shortcut: 'S',      action: () => {} },
    { label: 'Delete Clip',   shortcut: 'Del',    action: () => {} },
  ];

  return (
    <div className="titlebar">
      {/* Left: Logo + menus */}
      <div className="titlebar__left">
        <div className="titlebar__logo">
          <div className="titlebar__logo-dot" />
          <span>FADE</span>
        </div>
        <div className="titlebar__menus">
          <MenuButton label="File"     items={fileItems} />
          <MenuButton label="Edit"     items={editItems} />
          <button className="tb-menu__btn" onClick={onSettings}>Settings</button>
        </div>
      </div>

      {/* Centre: workspace tabs */}
      <div className="titlebar__tabs">
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
