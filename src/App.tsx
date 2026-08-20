import { useState, useEffect } from 'react'
import TitleBar           from './components/TitleBar'
import SettingsPanel      from './components/SettingsPanel'
import HomeWorkspace      from './workspaces/HomeWorkspace'
import AIWorkspace        from './workspaces/AIWorkspace'
import VideoWorkspace     from './workspaces/VideoWorkspace'
import AudioWorkspace     from './workspaces/AudioWorkspace'
import ExportWorkspace    from './workspaces/ExportWorkspace'
import { ToolContext, TOOL_CURSOR } from './context/toolContext'
import type { ActiveTool } from './context/toolContext'
import ToolboxWidget      from './workspaces/tools/ToolboxWidget'
import './App.css'

type TabId = 'home' | 'ai' | 'video' | 'audio' | 'export'

export default function App() {
  const [activeTab,      setActiveTab]      = useState<TabId>('home')
  const [showSettings,   setShowSettings]   = useState(false)
  const [activeTool,     setActiveTool]     = useState<ActiveTool>('pointer')
  const [lastShapeTool,  setLastShapeTool]  = useState<ActiveTool>('shape:rect')
  const [showToolbox,    setShowToolbox]    = useState(true)

  // Apply cursor to whole app when tool changes
  useEffect(() => {
    document.body.style.cursor = TOOL_CURSOR[activeTool] ?? 'default'
    return () => { document.body.style.cursor = '' }
  }, [activeTool])

  const workspaces: Record<TabId, React.FC> = {
    home:   HomeWorkspace,
    ai:     AIWorkspace,
    video:  VideoWorkspace,
    audio:  AudioWorkspace,
    export: ExportWorkspace,
  }
  const Workspace = workspaces[activeTab]

  return (
    <ToolContext.Provider value={{
      activeTool,
      setTool:      setActiveTool,
      lastShapeTool,
      setLastShape: setLastShapeTool,
    }}>
      <div className="app-shell">
        <TitleBar
          active={activeTab}
          onTab={(t) => setActiveTab(t as TabId)}
          onSettings={() => setShowSettings(true)}
          activeTool={activeTool}
          onTool={setActiveTool}
          onToggleToolbox={() => setShowToolbox(v => !v)}
          toolboxOpen={showToolbox}
        />
        <main className="app-workspace">
          <Workspace />
        </main>

        {/* Floating toolbox — visible on Video tab */}
        {activeTab === 'video' && showToolbox && (
          <ToolboxWidget onClose={() => setShowToolbox(false)} />
        )}

        {showSettings && (
          <SettingsPanel onClose={() => setShowSettings(false)} />
        )}
      </div>
    </ToolContext.Provider>
  )
}
