import './TopTabBar.css'

interface Tab {
  id: string
  label: string
}

interface TopTabBarProps {
  active: string
  onTab:  (id: string) => void
}

const TABS: Tab[] = [
  { id: 'home', label: 'Home' },
  { id: 'ai', label: 'AI' },
  { id: 'video', label: 'Video' },
  { id: 'audio', label: 'Audio' },
  { id: 'export', label: 'Export' },
]

export default function TopTabBar({ active, onTab }: TopTabBarProps) {
  return (
    <div className="toptabbar">
      <div className="toptabbar__segments">
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            className={`toptabbar__tab${active === id ? ' toptabbar__tab--active' : ''}`}
            onClick={() => onTab(id)}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  )
}
