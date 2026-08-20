import { useState } from 'react'
import TitleBar      from './components/TitleBar'
import SettingsPanel from './components/SettingsPanel'
import HomeWorkspace   from './workspaces/HomeWorkspace'
import AIWorkspace     from './workspaces/AIWorkspace'
import VideoWorkspace  from './workspaces/VideoWorkspace'
import AudioWorkspace  from './workspaces/AudioWorkspace'
import ExportWorkspace from './workspaces/ExportWorkspace'
import './App.css'

type TabId = 'home' | 'ai' | 'video' | 'audio' | 'export'

const WORKSPACES: Record<TabId, React.FC> = {
  home:   HomeWorkspace,
  ai:     AIWorkspace,
  video:  VideoWorkspace,
  audio:  AudioWorkspace,
  export: ExportWorkspace,
}

export default function App() {
  const [activeTab,     setActiveTab]     = useState<TabId>('home')
  const [showSettings,  setShowSettings]  = useState(false)
  const Workspace = WORKSPACES[activeTab]

  return (
    <div className="app-shell">
      <TitleBar
        active={activeTab}
        onTab={(t) => setActiveTab(t as TabId)}
        onSettings={() => setShowSettings(true)}
      />
      <main className="app-workspace">
        <Workspace />
      </main>

      {showSettings && (
        <SettingsPanel onClose={() => setShowSettings(false)} />
      )}
    </div>
  )
}
