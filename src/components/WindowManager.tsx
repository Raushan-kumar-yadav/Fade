 
import { useEffect, useCallback } from 'react'
import FloatingWindow from './FloatingWindow'
import HomeWorkspace from '../workspaces/HomeWorkspace'
import AIWorkspace from '../workspaces/AIWorkspace'
import VideoWorkspace from '../workspaces/VideoWorkspace'
import AudioWorkspace from '../workspaces/AudioWorkspace'
import ExportWorkspace from '../workspaces/ExportWorkspace'
import ImageWorkspace from '../workspaces/ImageWorkspace'
import PdfWorkspace from '../workspaces/pdf/PdfWorkspace'
import DirectorPanel from '../workspaces/director/DirectorPanel'

export type DetachableTabId =
  | 'home' | 'ai' | 'video' | 'audio' | 'export' | 'director'
  | 'image' | 'pdf'

interface TabMeta {
  label: string
  icon: string
  accent: string
  w: number
  h: number
}

export const TAB_META: Record<DetachableTabId, TabMeta> = {
  home: { label: 'Home', icon: '🏠', accent: '#4a9eff', w: 900,  h: 600 },
  ai: { label: 'AI Chat', icon: '🤖', accent: '#a855f7', w: 480,  h: 700 },
  video: { label: 'Video Editor', icon: '🎬', accent: '#7c6fff', w: 1100, h: 720 },
  audio: { label: 'Audio', icon: '🎵', accent: '#22d3ee', w: 700,  h: 420 },
  export: { label: 'Export', icon: '📤', accent: '#f59e0b', w: 800,  h: 560 },
  director: { label: 'Director', icon: '🎭', accent: '#ec4899', w: 900,  h: 640 },
  image: { label: 'Image Editor', icon: '🖼️', accent: '#10b981', w: 1100, h: 720 },
  pdf: { label: 'PDF Editor',   icon: '📄', accent: '#f97316', w: 900,  h: 720 },
}

interface WindowManagerProps {
  detachedTabs: Set<DetachableTabId>
  onClose: (tabId: DetachableTabId) => void
  
  imageCompId?: string | null
  imageCompName?: string
  pdfDocId?: string | null
  pdfDocName?: string
  onImageBack?: () => void
}

export default function WindowManager({
  detachedTabs,
  onClose,
  imageCompId,
  imageCompName = 'Image Editor',
  pdfDocId,
  pdfDocName = 'Untitled Document',
  onImageBack,
}: WindowManagerProps) {

 
  const tabs = Array.from(detachedTabs)

  return (
    <>
      {tabs.map((tabId, idx) => {
        const meta = TAB_META[tabId]
        const offset = idx * 32

        const content = renderWorkspace(tabId, {
          imageCompId, imageCompName, pdfDocId, pdfDocName,
          onImageBack: onImageBack ?? (() => onClose('image')),
        })

        if (!content) return null

        return (
          <FloatingWindow
            key={tabId}
            id={`fw-${tabId}`}
            title={meta.label}
            icon={meta.icon}
            accent={meta.accent}
            defaultWidth={meta.w}
            defaultHeight={meta.h}
            defaultX={80 + offset}
            defaultY={50 + offset}
            onClose={() => onClose(tabId)}
          >
            {content}
          </FloatingWindow>
        )
      })}
    </>
  )
}

//   Render the right workspace per tabId  

interface ExtraProps {
  imageCompId?: string | null
  imageCompName?: string
  pdfDocId?: string | null
  pdfDocName?: string
  onImageBack: () => void
}

function renderWorkspace(tabId: DetachableTabId, p: ExtraProps) {
  switch (tabId) {
    case 'home': return <HomeWorkspace />
    case 'ai': return <AIWorkspace />
    case 'video': return <VideoWorkspace floatingMode />
    case 'audio': return <AudioWorkspace />
    case 'export': return <ExportWorkspace />
    case 'director': return <DirectorPanel />
    case 'image':
      return (
        <ImageWorkspace
          floatingMode
          compId={p.imageCompId ?? null}
          compName={p.imageCompName ?? 'Image Editor'}
          onBack={p.onImageBack}
        />
      )
    case 'pdf':
      return <PdfWorkspace docId={p.pdfDocId ?? null} docName={p.pdfDocName ?? 'Untitled Document'} />
    default:
      return null
  }
}
