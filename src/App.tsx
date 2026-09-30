import { useState, useEffect, useCallback, useRef } from 'react'
import TitleBar from './components/TitleBar'
import SettingsPanel from './components/SettingsPanel'
import CreateProjectModal from './components/createProjectModal.'
import HomeWorkspace from './workspaces/HomeWorkspace'
import AIWorkspace from './workspaces/AIWorkspace'
import VideoWorkspace from './workspaces/VideoWorkspace'
import AudioWorkspace from './workspaces/AudioWorkspace'
import ExportWorkspace from './workspaces/ExportWorkspace'
import ImageWorkspace from './workspaces/ImageWorkspace'
import PdfWorkspace from './workspaces/pdf/PdfWorkspace'
import DirectorPanel from './workspaces/director/DirectorPanel'
import { ToolContext, TOOL_CURSOR } from './context/toolContext'
import type { ActiveTool, PenSubMode, PenOutputMode } from './context/toolContext'
import { SelectionContext, type SelectedItem } from './context/selectionContext'
import ToolboxWidget from './workspaces/tools/ToolboxWidget'
import FloatingAIChat from './workspaces/FloatingAIChat'
import ExportProgressOverlay from './workspaces/ExportProgressOverlay'
import WindowManager from './components/WindowManager'
import DraggableAIButton from './components/DraggableAIButton'
import { useLibrarySSE }  from './api/useLibrarySSE'
import './App.css'

type TabId = 'home' | 'ai' | 'video' | 'audio' | 'export' | 'image' | 'pdf' | 'director'


// Loading overlay  

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

// Media Offline Banner  

interface MissingAsset { assetId: string; clipId: string; filename_hint: string }

function MediaOfflineBanner({
  assets,
  onRelinked,
}: {
  assets: MissingAsset[];
  onRelinked: (assetId: string) => void;
}) {
  const port = (window as any).__FADE_PORT__ ?? 8000;
  const relink = async (a: MissingAsset) => {
    const el = (window as any).electronAPI;
    const fp: string | undefined = await el?.showOpenDialog({
      title: `Relink "${a.filename_hint}"`,
      filters: [
        { name: 'Media', extensions: ['mp4','mov','avi','mkv','webm','png','jpg','jpeg','bmp','webp','svg','mp3','wav','aac','flac','ogg'] },
        { name: 'All Files', extensions: ['*'] },
      ],
    });
    if (!fp) return;
    const r = await fetch(`http://127.0.0.1:${port}/library/relink/${a.assetId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filepath: fp }),
    });
    if (r.ok) {
      onRelinked(a.assetId);
      window.dispatchEvent(new CustomEvent('fade:tracks-changed'));
    }
  };
  return (
    <div style={{
      position: 'fixed', bottom: 60, left: '50%', transform: 'translateX(-50%)',
      zIndex: 5000,
      background: 'rgba(28,18,8,0.96)',
      border: '1px solid rgba(255,160,40,0.45)',
      borderRadius: 10, padding: '12px 18px',
      display: 'flex', flexDirection: 'column', gap: 8,
      fontFamily: 'Inter,sans-serif', fontSize: 13, color: '#ffd580',
      boxShadow: '0 8px 32px rgba(0,0,0,0.65)',
      maxWidth: 480, minWidth: 300,
    }}>
      <div style={{ fontWeight: 600, marginBottom: 2 }}>
        {'\u26a0\ufe0f'} {assets.length} media file{assets.length > 1 ? 's' : ''} offline
      </div>
      {assets.map(a => (
        <div key={a.assetId} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ flex: 1, opacity: 0.75, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {a.filename_hint || a.assetId.slice(0, 12) + '…'}
          </span>
          <button
            onClick={() => relink(a)}
            style={{
              background: 'rgba(255,160,40,0.15)', border: '1px solid rgba(255,160,40,0.4)',
              color: '#ffd580', borderRadius: 6, padding: '3px 12px',
              cursor: 'pointer', fontSize: 12, whiteSpace: 'nowrap',
            }}
          >
            Relink…
          </button>
        </div>
      ))}
    </div>
  );
}

// App  

export default function App() {
  // Live push notifications from backend 
  useLibrarySSE()

  const [activeTab, setActiveTab] = useState<TabId>('home')
  const [showSettings, setShowSettings] = useState(false)
  const [showNewProject, setShowNewProject] = useState(false)
  const [activeTool, setActiveTool] = useState<ActiveTool>('pointer')
  const [lastShapeTool,  setLastShapeTool] = useState<ActiveTool>('shape:rect')
  const [showToolbox, setShowToolbox] = useState(true)
  const [selected, setSelectedRaw]    = useState<SelectedItem | null>(null)
  const [penSubMode, setPenSubMode] = useState<PenSubMode>('pen:add')
  const [penOutputMode,  setPenOutputMode]  = useState<PenOutputMode>('clip')
  const [brushColor, setBrushColor] = useState<[number, number, number, number]>([1, 1, 1, 1])
  const [brushSize, setBrushSize] = useState<number>(10)

  // Global AI chat widget  
  const [aiOpen, setAiOpen] = useState(false)

  // Any workspace can dispatch ' 
  useEffect(() => {
    const h = () => setAiOpen(v => !v)
    window.addEventListener('fade:ai-toggle', h)
    return () => window.removeEventListener('fade:ai-toggle', h)
  }, [])

  // Auto-show on AI tab 
  useEffect(() => {
    if (activeTab === 'ai') setAiOpen(true)
  }, [activeTab])

  // When a clip is selected, push to backend so AI tools can read it
  const setSelected = useCallback((item: SelectedItem | null) => {
    setSelectedRaw(item)
    const port = (window as any).__FADE_PORT__ ?? 8000
    const clipId = item?.type === 'clip' ? item.clipId : null
    fetch(`http://127.0.0.1:${port}/clips/select`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ clipId }),
    }).catch(() => {})
    window.dispatchEvent(new CustomEvent('fade:clip-selected', {
      detail: item?.type === 'clip' ? {
        clipId: item.clipId,
        trackIndex: item.trackIndex,
        clipType: item.clipType,
      } : null,
    }))
  }, [])

  // Loading overlay state
  const [loadingMsg, setLoadingMsg] = useState<string | null>(null)
  // Offline assets after project load
  const [offlineAssets, setOfflineAssets] = useState<MissingAsset[]>([])

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
  const handleProjectLoaded = useCallback((result: { project: any; timeline: any; missing_assets?: MissingAsset[] }) => {
    setLoadingMsg(null)
    setOfflineAssets(result.missing_assets ?? [])
    setActiveTab('video')
    window.dispatchEvent(new CustomEvent('fade:tracks-changed'))
    window.dispatchEvent(new CustomEvent('fade:library-changed'))   // refresh library panel
    window.dispatchEvent(new CustomEvent('fade:project-loaded', { detail: result }))
  }, [])

  // Expose a way for TitleBar  
  const handleProjectLoadStart = useCallback((msg: string) => {
    setLoadingMsg(msg)
  }, [])

  const handleProjectLoadEnd = useCallback(() => {
    setLoadingMsg(null)

  }, [])

  // Listen for imageComp double-click → switch to image tab
  const [imageCompId, setImageCompId] = useState<string | null>(null);
  const [imageCompName, setImageCompName] = useState<string>('Image Editor');
  useEffect(() => {
    const h = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.compId) {
        setImageCompId(detail.compId);
        setImageCompName(detail.name || 'Image Editor');
      }
      setActiveTab('image');
    };
    window.addEventListener('fade:enter-image-comp', h);
    return () => window.removeEventListener('fade:enter-image-comp', h);
  }, []);

  // Listen for PDF doc open → switch to pdf tab
  const [pdfDocId, setPdfDocId] = useState<string | null>(null);
  const [pdfDocName, setPdfDocName] = useState<string>('Untitled Document');
  useEffect(() => {
    const h = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.docId) {
        setPdfDocId(detail.docId);
        setPdfDocName(detail.name || 'Untitled Document');
      }
      setActiveTab('pdf');
    };
    window.addEventListener('fade:enter-pdf-doc', h);
    return () => window.removeEventListener('fade:enter-pdf-doc', h);
  }, []);

  const workspaces: Record<Exclude<TabId, 'image' | 'pdf'>, React.FC> = {
    home: HomeWorkspace,
    ai: AIWorkspace,
    video: VideoWorkspace,
    audio: AudioWorkspace,
    export: ExportWorkspace,
    director: DirectorPanel,
  }

  const isImageTab = activeTab === 'image';
  const isPdfTab   = activeTab === 'pdf';
  const Workspace  = (isImageTab || isPdfTab) ? null : workspaces[activeTab as Exclude<TabId, 'image' | 'pdf'>]

  return (
    <SelectionContext.Provider value={{ selected, setSelected }}>
      <ToolContext.Provider value={{
        activeTool,
        setTool: setActiveTool,
        lastShapeTool,
        setLastShape: setLastShapeTool,
        penSubMode,
        setPenSubMode,
        penOutputMode,
        setPenOutputMode,
          brushColor,
          setBrushColor,
          brushSize,
          setBrushSize,
      }}>
        <div className="app-shell">
          <TitleBar
            active={activeTab}
            onTab={(t) => setActiveTab(t as TabId)}
            onSettings={() => setShowSettings(true)}
            onNewProject={() => setShowNewProject(true)}
            activeTool={activeTool}
            onTool={setActiveTool}
            onToggleToolbox={() => setShowToolbox(v => !v)}
            toolboxOpen={showToolbox}
            onProjectLoaded={handleProjectLoaded}
            onLoadStart={handleProjectLoadStart}
            onLoadEnd={handleProjectLoadEnd}
          />
          <main className="app-workspace">
           
            <div style={{
              display: isImageTab ? 'flex' : 'none',
              width: '100%', height: '100%',
            }}>
              <ImageWorkspace
                compId={imageCompId}
                compName={imageCompName}
                onBack={() => setActiveTab('video')}
              />
            </div>

            {/* PdfWorkspace  */}
            <div style={{
              display: isPdfTab ? 'flex' : 'none',
              width: '100%', height: '100%',
            }}>
              <PdfWorkspace docId={pdfDocId} docName={pdfDocName} />
            </div>

            {!isImageTab && !isPdfTab && Workspace && <Workspace />}
          </main>


           
          {(activeTab === 'video' || activeTab === 'image') && showToolbox && (
            <ToolboxWidget onClose={() => setShowToolbox(false)} />
          )}

          {/* AI chat — visible on ALL tabs */}
          <div style={{ display: aiOpen ? 'contents' : 'none' }}>
            <FloatingAIChat onClose={() => setAiOpen(false)} />
          </div>

          {/* Draggable AI button — visible on all tabs, position persists in localStorage */}
          {!aiOpen && <DraggableAIButton onClick={() => setAiOpen(true)} />}

          {/* Floating detached workspace windows */}
          <WindowManager />

          {showSettings && (
            <SettingsPanel onClose={() => setShowSettings(false)} />
          )}

          {showNewProject && (
            <CreateProjectModal
              onClose={() => setShowNewProject(false)}
              onProjectCreated={() => {
                setShowNewProject(false)
                setActiveTab('video')
                window.dispatchEvent(new CustomEvent('fade:tracks-changed'))
              }}
            />
          )}

           
          {/* AI-triggered export progress */}
          <ExportProgressOverlay />

           
          {loadingMsg && <LoadingOverlay message={loadingMsg} />}

           
          {offlineAssets.length > 0 && (
            <MediaOfflineBanner
              assets={offlineAssets}
              onRelinked={(id) => setOfflineAssets(prev => prev.filter(a => a.assetId !== id))}
            />
          )}
        </div>
      </ToolContext.Provider>
    </SelectionContext.Provider>
  )
}

