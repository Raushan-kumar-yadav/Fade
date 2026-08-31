import { useCallback } from 'react'
import { Allotment } from 'allotment'
import 'allotment/dist/style.css'
import ViewportWidget from './viewport/ViewportWidget'
import LibraryPanel from './library/LibraryPanel'
import { TimelineProvider } from './timeline/TimelineContext'
import { addClipToTimeline, type AssetItem } from '../api/useApi'
import './AIWorkspace.css'

// AI Workspace — Library panel (left) + live viewport (right).
// TimelineProvider is required here because LibraryPanel calls useTimeline() internally.
// (VideoWorkspace has its own provider — the two share a backend but maintain separate UI state.)

export default function AIWorkspace() {

  const handleAddToTimeline = useCallback(async (asset: AssetItem, trackIndex = 0) => {
    await addClipToTimeline(asset.assetId, trackIndex, 0, 300)
    window.dispatchEvent(new CustomEvent('fade:tracks-changed'))
  }, [])

  return (
    <TimelineProvider>
      <div className="ai-ws">
        <Allotment>
          {/* Library panel — collapsible, default 280px */}
          <Allotment.Pane minSize={200} maxSize={400} preferredSize={280} snap>
            <div className="ai-library-pane">
              <LibraryPanel onAddToTimeline={handleAddToTimeline} />
            </div>
          </Allotment.Pane>

          {/* Main viewport */}
          <Allotment.Pane minSize={320}>
            <div className="ai-viewport-pane">
              <ViewportWidget />
            </div>
          </Allotment.Pane>
        </Allotment>
      </div>
    </TimelineProvider>
  )
}
