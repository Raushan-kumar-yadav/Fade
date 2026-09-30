/**
 * WindowManager — manages a set of floating detached workspace windows.
 * 
 * Usage in App.tsx:
 *   <WindowManager activeTab={activeTab} />
 * 
 * Any workspace can dispatch:
 *   window.dispatchEvent(new CustomEvent('fade:detach-tab', { detail: { tabId: 'audio' } }))
 * 
 * TitleBar tabs get a detach icon on right-click → "Open in floating window".
 */

import { useState, useCallback, useEffect } from 'react'
import FloatingWindow from './FloatingWindow'
import HomeWorkspace from '../workspaces/HomeWorkspace'
import AIWorkspace from '../workspaces/AIWorkspace'
import VideoWorkspace from '../workspaces/VideoWorkspace'
import AudioWorkspace from '../workspaces/AudioWorkspace'
import ExportWorkspace from '../workspaces/ExportWorkspace'
import DirectorPanel from '../workspaces/director/DirectorPanel'

type TabId = 'home' | 'ai' | 'video' | 'audio' | 'export' | 'director'

const TAB_META: Record<TabId, { label: string; icon: string; accent: string; w: number; h: number }> = {
  home:     { label: 'Home',     icon: '🏠', accent: '#4a9eff', w: 900, h: 600 },
  ai:       { label: 'AI Chat',  icon: '🤖', accent: '#a855f7', w: 480, h: 700 },
  video:    { label: 'Video',    icon: '🎬', accent: '#7c6fff', w: 1100, h: 720 },
  audio:    { label: 'Audio',    icon: '🎵', accent: '#22d3ee', w: 700, h: 420 },
  export:   { label: 'Export',   icon: '📤', accent: '#f59e0b', w: 800, h: 560 },
  director: { label: 'Director', icon: '🎭', accent: '#ec4899', w: 900, h: 640 },
}

const WORKSPACE_MAP: Record<TabId, React.FC> = {
  home:     HomeWorkspace,
  ai:       AIWorkspace,
  video:    VideoWorkspace,
  audio:    AudioWorkspace,
  export:   ExportWorkspace,
  director: DirectorPanel,
}

interface DetachedWindow {
  id: string
  tabId: TabId
  /** stagger position so windows don't all stack at same spot */
  offsetIdx: number
}

export default function WindowManager() {
  const [windows, setWindows] = useState<DetachedWindow[]>([])

  const detach = useCallback((tabId: TabId) => {
    // Don't duplicate
    setWindows(prev => {
      if (prev.some(w => w.tabId === tabId)) return prev
      const offsetIdx = prev.length
      return [...prev, { id: `fw-${tabId}-${Date.now()}`, tabId, offsetIdx }]
    })
  }, [])

  const close = useCallback((id: string) => {
    setWindows(prev => prev.filter(w => w.id !== id))
  }, [])

  // Listen for detach events from anywhere in the app
  useEffect(() => {
    const h = (e: Event) => {
      const tabId = (e as CustomEvent).detail?.tabId as TabId | undefined
      if (tabId && TAB_META[tabId]) detach(tabId)
    }
    window.addEventListener('fade:detach-tab', h)
    return () => window.removeEventListener('fade:detach-tab', h)
  }, [detach])

  return (
    <>
      {windows.map(win => {
        const meta = TAB_META[win.tabId]
        const Workspace = WORKSPACE_MAP[win.tabId]
        const offset = win.offsetIdx * 32
        return (
          <FloatingWindow
            key={win.id}
            id={win.id}
            title={meta.label}
            icon={meta.icon}
            accent={meta.accent}
            defaultWidth={meta.w}
            defaultHeight={meta.h}
            defaultX={60 + offset}
            defaultY={60 + offset}
            onClose={() => close(win.id)}
          >
            <Workspace />
          </FloatingWindow>
        )
      })}
    </>
  )
}
