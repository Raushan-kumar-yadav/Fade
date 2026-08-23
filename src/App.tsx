import { useState, useEffect, useCallback } from 'react'
import TitleBar           from './components/TitleBar'
import SettingsPanel      from './components/SettingsPanel'
import HomeWorkspace      from './workspaces/HomeWorkspace'
import AIWorkspace        from './workspaces/AIWorkspace'
import VideoWorkspace     from './workspaces/VideoWorkspace'
import AudioWorkspace     from './workspaces/AudioWorkspace'
import ExportWorkspace    from './workspaces/ExportWorkspace'
import { ToolContext, TOOL_CURSOR } from './context/toolContext'
import type { ActiveTool, PenSubMode, PenOutputMode } from './context/toolContext'
import { SelectionContext, type SelectedItem } from './context/selectionContext'
import ToolboxWidget      from './workspaces/tools/ToolboxWidget'
import './App.css'

type TabId = 'home' | 'ai' | 'video' | 'audio' | 'export'

// ── Loading overlay ──────────────────────────────────────────────────────────

function LoadingOverlay({ message }: { message: string }) {
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: 'rgba(10,10,14,0.82)',
      backdropFilter: 'blur(6px)',
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      gap: 20, color: '#fff', fontFamily: 'Inter,sans-serif',
    }}>
      {/* Spinner */}
      <div style={{
        width: 48, height: 48,
        border: '3px solid rgba(255,255,255,0.15)',
        borderTopColor: '#7c6fff',
        borderRadius: '50%',
        animation: 'fade-spin 0.8s linear infinite',
      }} />
      <div style={{ fontSize: 15, opacity: 0.85 }}>{message}</div>
      <style>{`@keyframes fade-spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}

// ── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  const [activeTab,     setActiveTab]     = useState<TabId>('home')
  const [showSettings,  setShowSettings]  = useState(false)
  const [activeTool,    setActiveTool]    = useState<ActiveTool>('pointer')
  const [lastShapeTool, setLastShapeTool] = useState<ActiveTool>('shape:rect')
  const [showToolbox,   setShowToolbox]   = useState(true)
  const [selected,      setSelected]      = useState<SelectedItem | null>(null)
  const [penSubMode,    setPenSubMode]    = useState<PenSubMode>('pen:add')
  const [penOutputMode, setPenOutputMode] = useState<PenOutputMode>('clip')

  // Loading overlay state
  const [loadingMsg, setLoadingMsg] = useState<string | null>(null)

  // Apply cursor to whole app when tool changes
  useEffect(() => {
    document.body.style.cursor = TOOL_CURSOR[activeTool] ?? 'default'
    return () => { document.body.style.cursor = '' }
  }, [activeTool])

  useEffect(() => {
    const port = (window as any).__FADE_PORT__ ?? 8000
    const base  = `http://127.0.0.1:${port}`
    const onKey = async (e: KeyboardEvent) => {
      if (!e.ctrlKey && !e.metaKey) return
      if (e.key === 'z' && !e.shiftKey) {
        e.preventDefault()
        await fetch(`${base}/history/undo`, { method: 'POST' })
        window.dispatchEvent(new CustomEvent('fade:tracks-changed'))
      } else if (e.key === 'y' || (e.key === 'z' && e.shiftKey)) {
        e.preventDefault()
        await fetch(`${base}/history/redo`, { method: 'POST' })
        window.dispatchEvent(new CustomEvent('fade:tracks-changed'))
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Called by TitleBar after a project is loaded
  const handleProjectLoaded = useCallback((result: { project: any; timeline: any }) => {
    setLoadingMsg(null)
    // Switch to video workspace so the user sees their timeline immediately
    setActiveTab('video')
    // Notify timeline components to refresh
    window.dispatchEvent(new CustomEvent('fade:tracks-changed'))
    window.dispatchEvent(new CustomEvent('fade:project-loaded', { detail: result }))
  }, [])

  // Expose a way for TitleBar to show the loading overlay before the fetch
  // We pass a wrapper that sets the message, delegates to projectApi, then clears
  const handleProjectLoadStart = useCallback((msg: string) => {
    setLoadingMsg(msg)
  }, [])

  const handleProjectLoadEnd = useCallback(() => {
    setLoadingMsg(null)
  }, [])

  const workspaces: Record<TabId, React.FC> = {
    home:   HomeWorkspace,
    ai:     AIWorkspace,
    video:  VideoWorkspace,
    audio:  AudioWorkspace,
    export: ExportWorkspace,
  }
  const Workspace = workspaces[activeTab]

  return (
    <SelectionContext.Provider value={{ selected, setSelected }}>
      <ToolContext.Provider value={{
        activeTool,
        setTool:          setActiveTool,
        lastShapeTool,
        setLastShape:     setLastShapeTool,
        penSubMode,
        setPenSubMode,
        penOutputMode,
        setPenOutputMode,
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
            onProjectLoaded={handleProjectLoaded}
            onLoadStart={handleProjectLoadStart}
            onLoadEnd={handleProjectLoadEnd}
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

          {/* Full-screen loading overlay */}
          {loadingMsg && <LoadingOverlay message={loadingMsg} />}
        </div>
      </ToolContext.Provider>
    </SelectionContext.Provider>
  )
}
