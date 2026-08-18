import './TitleBar.css'

interface ElectronAPI {
  minimize: () => void
  maximize: () => void
  close: () => void
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI
  }
}

const TABS = [
  { id: 'home', label: 'Home' },
  { id: 'ai', label: 'AI' },
  { id: 'video', label: 'Video' },
  { id: 'audio', label: 'Audio'  },
  { id: 'export', label: 'Export' },
]

interface TitleBarProps {
  active: string
  onTab:  (id: string) => void
}

export default function TitleBar({ active, onTab }: TitleBarProps) {
  const api = window.electronAPI

  return (
    <div className="titlebar">
      {/* Logo */}
      <div className="titlebar__logo">
        <div className="titlebar__logo-dot" />
        <span>FADE</span>
      </div>

      {/* Tab pill */}
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

      {/* Window controls */}
      <div className="titlebar__controls">
        <button className="wbtn wbtn--min"  onClick={() => api?.minimize()} />
        <button className="wbtn wbtn--max"  onClick={() => api?.maximize()} />
        <button className="wbtn wbtn--close" onClick={() => api?.close()}   />
      </div>
    </div>
  )
}
