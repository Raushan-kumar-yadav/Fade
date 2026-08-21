import React, { useCallback, useState } from 'react'
import * as FlexLayout from 'flexlayout-react'
import 'flexlayout-react/style/dark.css'
import './VideoWorkspace.css'
import Timeline        from './timeline/Timeline'
import ViewportWidget  from './viewport/ViewportWidget'
import LibraryPanel    from './library/LibraryPanel'
import InspectorPanel  from './inspector/InspectorPanel'
import EffectsPanel    from './inspector/EffectsPanel'
import { addClipToTimeline, type AssetItem } from '../api/useApi'
import { useTool, isShapeTool } from '../context/toolContext'
import TextToolPanel   from './tools/TextToolPanel'
import ShapeToolPanel  from './tools/ShapeToolPanel'

// ── Tool creation panel ───────────────────────────────────────────────────────

function ToolPanel() {
  const { activeTool } = useTool()
  const [currentFrame] = useState(0)

  if (activeTool === 'text') {
    return (
      <TextToolPanel
        currentFrame={currentFrame}
        onCreated={(clip) => console.log('[Fade] text clip created', clip.clipId)}
      />
    )
  }
  if (isShapeTool(activeTool)) {
    return (
      <ShapeToolPanel
        currentFrame={currentFrame}
        onCreated={(clip) => console.log('[Fade] shape clip created', clip.clipId)}
      />
    )
  }
  return (
    <div className="vp vp--props" style={{ padding: 12, color: '#475569', fontSize: 11 }}>
      Select a creation tool (T / Q / P) to show options here.
    </div>
  )
}

// ── FlexLayout model ──────────────────────────────────────────────────────────

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
              { type: 'tab', name: 'Effects',   component: 'effects',   enableClose: false },
              { type: 'tab', name: 'Tools',     component: 'tools',     enableClose: false },
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

let _model: FlexLayout.Model | null = null
function getModel(): FlexLayout.Model {
  if (!_model) _model = FlexLayout.Model.fromJson(layoutJson)
  return _model
}

// ── VideoWorkspace ────────────────────────────────────────────────────────────

export default function VideoWorkspace() {
  const model = getModel()

  const handleAddToTimeline = useCallback(async (asset: AssetItem, trackIndex = 0) => {
    await addClipToTimeline(asset.assetId, trackIndex, 0, 300)
  }, [])

  const factory = (node: FlexLayout.TabNode) => {
    switch (node.getComponent()) {
      case 'library':   return <LibraryPanel onAddToTimeline={handleAddToTimeline} />
      case 'viewport':  return <ViewportWidget />
      case 'timeline':  return (
        <div className="vp vp--timeline"><Timeline /></div>
      )
      case 'inspector': return <InspectorPanel />
      case 'effects':   return <EffectsPanel />
      case 'tools':     return <ToolPanel />
      default:          return <div className="vp" />
    }
  }

  return (
    <div className="video-ws">
      <FlexLayout.Layout model={model} factory={factory} realtimeResize />
    </div>
  )
}
