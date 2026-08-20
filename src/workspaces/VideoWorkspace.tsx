import React, { useCallback } from 'react'
import * as FlexLayout from 'flexlayout-react'
import 'flexlayout-react/style/dark.css'
import './VideoWorkspace.css'
import Timeline from './timeline/Timeline'
import ViewportWidget from './viewport/ViewportWidget'
import LibraryPanel from './library/LibraryPanel'
import { addClipToTimeline, type AssetItem } from '../api/useApi'

// Panel wrappers  

function EffectsPanel() {
  const [active, setActive] = React.useState<string | null>(null)
  const EFFECTS = [
    { name: 'Blur Out', icon: '⬚' },
    { name: 'Zoom In', icon: '⊕' },
    { name: 'Fade In', icon: '◐' },
    { name: 'Newton Bounce', icon: '↗' },
    { name: 'Vignette', icon: '◉' },
    { name: 'Drop Shadow', icon: '▣' },
    { name: 'Color Grade', icon: '◈' },
    { name: 'Speed Ramp', icon: '⚡' },
  ]

  return (
    <div className="vp">
      <div className="vp__list">
        {EFFECTS.map(fx => (
          <div key={fx.name}
            className={`vp__item vp__item--effect${active === fx.name ? ' vp__item--active' : ''}`}
            onClick={() => setActive(fx.name)}>
            <span className="vp__icon">{fx.icon}</span>
            {fx.name}
          </div>
        ))}
      </div>
    </div>
  )
}

function PropertiesPanel() {
  const PROPS = [
    { l: 'Opacity',  min: 0, max: 100, def: 100 },
    { l: 'Scale X',  min: 10, max: 300, def: 100 },
    { l: 'Scale Y',  min: 10, max: 300, def: 100 },
    { l: 'Rotation', min: -180, max: 180, def: 0 },
    { l: 'X Offset', min: -500, max: 500, def: 0 },
    { l: 'Y Offset', min: -500, max: 500, def: 0 },
  ]

  return (
    <div className="vp vp--props">
      {PROPS.map(p => (
        <label key={p.l} className="vp__prop">
          <span>{p.l}</span>
          <div className="vp__prop-row">
            <input type="range" min={p.min} max={p.max} defaultValue={p.def} />
            <span className="vp__prop-val">{p.def}</span>
          </div>
        </label>
      ))}
      <label className="vp__prop">
        <span>Easing</span>
        <select>
          <option>ease_in_out</option>
          <option>newton_bounce</option>
          <option>ease_out_cubic</option>
          <option>linear</option>
        </select>
      </label>
      <button className="vp__apply">Apply to Selection</button>
    </div>
  )
}

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
            children: [
              { type: 'tab', name: 'Effects',    component: 'effects',    enableClose: false },
              { type: 'tab', name: 'Properties', component: 'properties', enableClose: false },
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

// Workspace  

export default function VideoWorkspace() {
  const model = getModel()

   const handleAddToTimeline = useCallback(async (asset: AssetItem, trackIndex = 0) => {
    await addClipToTimeline(asset.assetId, trackIndex, 0, 300)
   }, [])

  const factory = (node: FlexLayout.TabNode) => {
    switch (node.getComponent()) {
      case 'library':
        return <LibraryPanel onAddToTimeline={handleAddToTimeline} />
      case 'viewport':
        return <ViewportWidget />
      case 'timeline':
        return (
          <div className="vp vp--timeline">
            <Timeline />
          </div>
        )
      case 'effects':    return <EffectsPanel />
      case 'properties': return <PropertiesPanel />
      default: return <div className="vp" />
    }
  }

  return (
    <div className="video-ws">
      <FlexLayout.Layout model={model} factory={factory} realtimeResize />
    </div>
  )
}
