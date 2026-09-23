import React, { useCallback } from 'react'
import * as FlexLayout from 'flexlayout-react'
import 'flexlayout-react/style/dark.css'
import './VideoWorkspace.css'
import Timeline from './timeline/Timeline'
import { TimelineProvider, useTimeline } from './timeline/TimelineContext'
import ViewportWidget from './viewport/ViewportWidget'
import LibraryPanel from './library/LibraryPanel'
import InspectorPanel from './inspector/InspectorPanel'
import EffectsPanel from './inspector/EffectsPanel'
import { addClipToTimeline, type AssetItem } from '../api/useApi'
import { useTool, isShapeTool } from '../context/toolContext'
import TextToolPanel from './tools/TextToolPanel'
import ShapeToolPanel from './tools/ShapeToolPanel'
import TransitionPanel from './inspector/TransitionPanel'
import CompositionsPanel from './compositions/CompositionsPanel'



// FlexLayout model  

const layoutJson: FlexLayout.IJsonModel = {
  global: {},
  borders: [],
  layout: {
    type: 'column',
    weight: 100,
    children: [
      {
        type: 'row',
        weight: 72,
        children: [
          {
            type: 'tabset',
            weight: 18,
            children: [{ type: 'tab', name: 'Library', component: 'library', enableClose: false }],
          },
          {
            type: 'tabset',
            weight: 52,
            children: [{ type: 'tab', name: 'Viewport', component: 'viewport', enableClose: false }],
          },
          {
            type: 'tabset',
            weight: 30,
            selected: 0,
            children: [
              { type: 'tab', name: 'Inspector', component: 'inspector', enableClose: false },
              { type: 'tab', name: 'Effects', component: 'effects', enableClose: false },
              { type: 'tab', name: 'Transitions',  component: 'transitions',  enableClose: false },
              { type: 'tab', name: 'Tools', component: 'tools', enableClose: false },
            ],
          },
        ],
      },
      {
        type: 'tabset',
        weight: 28,
        children: [{ type: 'tab', name: 'Timeline', component: 'timeline', enableClose: false }],
      },
    ],
  },
}

 
const LAYOUT_DEBOUNCE_MS = 500

function makeDefaultModel() {
  return FlexLayout.Model.fromJson(layoutJson)
}

// VideoWorkspace  
export default function VideoWorkspace() {
  return (
    <TimelineProvider>
      <div className="video-ws">
        {/* AI Director toggle button */}
        <button
          className="video-ws__ai-btn"
          onClick={() => window.dispatchEvent(new CustomEvent('fade:ai-toggle'))}
          title="Toggle AI Director"
        >
          🤖
        </button>

        <WorkspaceInner />
      </div>
    </TimelineProvider>
  )
}

// Inner component  
function WorkspaceInner() {
  const { state } = useTimeline()
  const { activeTool } = useTool()

  // Model ref  
  const modelRef = React.useRef<FlexLayout.Model>(makeDefaultModel())
  const [, forceUpdate] = React.useReducer(x => x + 1, 0)
  const saveTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null)
  const api = (window as any).electronAPI

  // Load saved layout once on mount
  React.useEffect(() => {
    api?.layoutLoad?.().then((json: string | null) => {
      if (!json) return
      try {
        modelRef.current = FlexLayout.Model.fromJson(JSON.parse(json))
        forceUpdate() 
      } catch (e) {
        console.warn('[Layout] saved layout invalid, using default', e)
      }
    }).catch(() => {})
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Save layout debounced on every model change
  const onModelChange = useCallback((model: FlexLayout.Model) => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    saveTimerRef.current = setTimeout(() => {
      const json = JSON.stringify(model.toJson())
      api?.layoutSave?.(json).catch(() => {})
    }, LAYOUT_DEBOUNCE_MS)
  }, [api])

  const handleAddToTimeline = useCallback(async (asset: AssetItem, trackIndex = 0) => {
     
    await addClipToTimeline(asset.assetId, trackIndex, 0, 300, 0, state.activeCompId)
  }, [state.activeCompId])

  // Tool panel reads currentFrame  
  const toolPanel = (() => {
    const frame = state.currentFrame ?? 0
    if (activeTool === 'text') {
      return (
        <TextToolPanel
          currentFrame={frame}
          onCreated={(clip) => console.log('[Fade] text clip created', clip.clipId)}
        />
      )
    }
    if (isShapeTool(activeTool)) {
      return (
        <ShapeToolPanel
          currentFrame={frame}
          onCreated={(clip) => console.log('[Fade] shape clip created', clip.clipId)}
        />
      )
    }
    return (
      <div className="vp vp--props" style={{ padding: 12, color: '#475569', fontSize: 11 }}>
        Select a creation tool (T / Q / P) to show options here.
      </div>
    )
  })()

  const factory = (node: FlexLayout.TabNode) => {
    switch (node.getComponent()) {
      case 'library': return <LibraryPanel onAddToTimeline={handleAddToTimeline} />
      case 'viewport': return <ViewportWidget />
      case 'timeline': return (
        <div className="vp vp--timeline"><Timeline /></div>
      )
      case 'inspector': return <InspectorPanel />
      case 'effects': return <EffectsPanel />
      case 'transitions': return <TransitionPanel />
      case 'tools': return toolPanel
      case 'compositions': return <CompositionsPanel />
      default: return <div className="vp" />
    }
  }

  return <FlexLayout.Layout model={modelRef.current} factory={factory} onModelChange={onModelChange} realtimeResize />
}
