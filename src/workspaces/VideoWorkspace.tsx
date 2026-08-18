import React from 'react'
import { Group as PanelGroup, Panel, Separator as PanelResizeHandle } from 'react-resizable-panels'
import './VideoWorkspace.css'

function ResizeHandle({ vertical = false }: { vertical?: boolean }) {
  return (
    <PanelResizeHandle
      className={`resize-handle ${vertical ? 'resize-handle--v' : 'resize-handle--h'}`}
    />
  )
}

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
      <div className="vp__header">Library</div>
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
      <div className="vp__header">Viewport</div>
      <div className="vp__screen">
        <div style={{ textAlign: 'center', color: '#55555f' }}>
          <div style={{ fontSize: 48 }}>◈</div>
          <p style={{ fontSize: 12, marginTop: 10 }}>Drop video or select from Library</p>
        </div>
      </div>
    </div>
  )
}

function TimelinePanel() {
  const tracks = [
    { label: 'Video', color: '#6c63ff', clips: [{ s: 0, w: 40 }, { s: 45, w: 30 }] },
    { label: 'Audio', color: '#00d4aa', clips: [{ s: 0, w: 75 }] },
    { label: 'FX', color: '#ff6584', clips: [{ s: 10, w: 15 }, { s: 55, w: 10 }] },
    { label: 'Text',  color: '#FFD60A', clips: [{ s: 5,  w: 20 }] },
  ]

  return (
    <div className="vp vp--timeline">
      <div className="vp__header">
        Timeline
        <div className="vp__toolbar">
          <button>✂</button><button>⊕</button><button>⟲</button>
          <span style={{ marginLeft: 'auto', color: '#55555f', fontSize: 10 }}>00:00:00</span>
        </div>
      </div>
      <div className="vp__tracks">
        {tracks.map(t => (
          <div key={t.label} className="vp__track">
            <div className="vp__track-label">{t.label}</div>
            <div className="vp__track-lane">
              {t.clips.map((c, i) => (
                <div key={i} className="vp__clip"
                  style={{ left: `${c.s}%`, width: `${c.w}%`, background: t.color + '55', borderColor: t.color }} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function EffectsPanel() {
  const [active, setActive] = React.useState<string | null>(null)
  const EFFECTS = ['Blur Out','Zoom In','Fade In','Newton Bounce','Vignette','Drop Shadow','Color Grade','Speed Ramp']

  return (
    <div className="vp">
      <div className="vp__header">Effects</div>
      <div className="vp__list">
        {EFFECTS.map(fx => (
          <div key={fx}
            className={`vp__item vp__item--effect${active === fx ? ' vp__item--active' : ''}`}
            onClick={() => setActive(fx)}>
            <span className="vp__icon" style={{ color: '#6c63ff' }}>✦</span>
            {fx}
          </div>
        ))}
      </div>
      {active && (
        <div className="vp__detail">
          <div className="vp__detail-title">{active}</div>
          {[
            { l: 'Intensity', min: 0,    max: 100, def: 50  },
            { l: 'Duration',  min: 1,    max: 60,  def: 15  },
          ].map(p => (
            <label key={p.l} className="vp__prop">
              {p.l}
              <input type="range" min={p.min} max={p.max} defaultValue={p.def} />
            </label>
          ))}
          <label className="vp__prop">
            Easing
            <select>
              <option>ease_in_out</option>
              <option>newton_bounce</option>
              <option>ease_out_cubic</option>
              <option>linear</option>
            </select>
          </label>
          <button className="vp__apply">Apply to Timeline</button>
        </div>
      )}
    </div>
  )
}

function PropertiesPanel() {
  return (
    <div className="vp">
      <div className="vp__header">Properties</div>
      <div className="vp__list" style={{ gap: 12, padding: 12 }}>
        {[
          { l: 'Opacity',  min: 0,   max: 100, def: 100 },
          { l: 'Scale X',  min: 10,  max: 300, def: 100 },
          { l: 'Scale Y',  min: 10,  max: 300, def: 100 },
          { l: 'Rotation', min:-180, max: 180, def: 0   },
        ].map(p => (
          <label key={p.l} className="vp__prop">
            {p.l}
            <input type="range" min={p.min} max={p.max} defaultValue={p.def} />
          </label>
        ))}
        <label className="vp__prop">
          Easing
          <select>
            <option>ease_in_out</option><option>newton_bounce</option>
            <option>ease_out_cubic</option><option>linear</option>
          </select>
        </label>
        <button className="vp__apply">Apply</button>
      </div>
    </div>
  )
}

export default function VideoWorkspace() {
  return (
    <div className="video-ws">
      <PanelGroup orientation="horizontal" className="panel-group">
        {/*  Library */}
        <Panel defaultSize={15} minSize={10}>
          <LibraryPanel />
        </Panel>

        <ResizeHandle />

        {/*   Viewport and Timeline */}
        <Panel defaultSize={60} minSize={30}>
          <PanelGroup orientation="vertical">
            <Panel defaultSize={70} minSize={30}>
              <ViewportPanel />
            </Panel>
            <ResizeHandle vertical />
            <Panel defaultSize={30} minSize={15}>
              <TimelinePanel />
            </Panel>
          </PanelGroup>
        </Panel>

        <ResizeHandle />

        {/*   Effects + Properties */}
        <Panel defaultSize={25} minSize={15}>
          <PanelGroup orientation="vertical">
            <Panel defaultSize={55} minSize={20}>
              <EffectsPanel />
            </Panel>
            <ResizeHandle vertical />
            <Panel defaultSize={45} minSize={20}>
              <PropertiesPanel />
            </Panel>
          </PanelGroup>
        </Panel>
      </PanelGroup>
    </div>
  )
}
