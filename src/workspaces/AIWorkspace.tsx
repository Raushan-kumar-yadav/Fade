import ViewportWidget from './viewport/ViewportWidget'
import './AIWorkspace.css'

 
export default function AIWorkspace() {
  return (
    <div className="ai-ws">
      <div className="ai-viewport-pane">
        <ViewportWidget />
      </div>
    </div>
  )
}
