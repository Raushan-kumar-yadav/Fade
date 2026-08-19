import React from 'react'
import * as FlexLayout from 'flexlayout-react'
import 'flexlayout-react/style/dark.css'
import './VideoWorkspace.css'
import Timeline from './timeline/Timeline'

// Panel content components  

function LibraryPanel() {
  const items = [
    { name: 'Clip_001.mp4', type: 'video' as const },
    { name: 'Clip_002.mp4', type: 'video' as const },
    { name: 'BRoll_sunset.mp4', type: 'video' as const },
    { name: 'Intro_v3.mp4', type: 'video' as const },
    { name: 'Title_card.png', type: 'image' as const },
    { name: 'Music_bg.mp3', type: 'audio' as const },
  ]
  const ICON: Record<string, string> = { video: '▶', audio: '♪', image: '🖼' }

  return (
    <div className="vp">
      <div className="vp__search">
        <input placeholder="Search assets…" />
      </div>
      <div className="vp__list">
        {items.map(i => (
          <div key={i.name} className="vp__item">
            <span className="vp__icon">{ICON[i.type]}</span>
            {i.name}
          </div>
        ))}
      </div>
    </div>
  )
}

function ViewportPanel() {
  return (
    <div className="vp vp--viewport">
      <div className="vp__screen">
        <div className="vp__screen-empty">
          <div className="vp__screen-icon">◈</div>
          <p>Drop video or select from Library</p>
          <div className="vp__screen-controls">
            <button>⏮</button>
            <button className="vp__screen-play">▶</button>
            <button>⏭</button>
          </div>
        </div>
      </div>
    </div>
  )
}

function TimelinePanel() {
  return (
    <div className="vp vp--timeline">
      <Timeline />
    </div>
  )
}

function EffectsPanel() {
  const [active, setActive] = React.useState<string | null>(null)
  const EFFECTS = [
    { name: 'Blur Out', icon: '⬚' },
    { name: 'Zoom In', icon: '⊕' },
    { name: 'Fade In', icon: '◐' },
    { name: 'Newton Bounce',  icon: '↗' },
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
    { l: 'Opacity', min: 0,   max: 100, def: 100 },
    { l: 'Scale X', min: 10,  max: 300, def: 100 },
    { l: 'Scale Y',  min: 10,  max: 300, def: 100 },
    { l: 'Rotation', min:-180, max: 180, def: 0   },
    { l: 'X Offset', min:-500, max: 500, def: 0   },
    { l: 'Y Offset', min:-500, max: 500, def: 0   },
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

 

const layoutJson: FlexLayout.IJsonModel = {
  global: {
    tabSetTabStripHeight: 30,
    tabSetHeaderHeight: 30,
    borderBarSize: 0,
    splitterSize: 2,    
    splitterExtra: 2,
  },
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

export default function VideoWorkspace() {
  const model = getModel()

  const factory = (node: FlexLayout.TabNode) => {
    switch (node.getComponent()) {
      case 'library': return <LibraryPanel />
      case 'viewport': return <ViewportPanel />
      case 'timeline': return <TimelinePanel />
      case 'effects': return <EffectsPanel />
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
