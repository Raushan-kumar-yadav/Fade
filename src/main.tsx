import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

// ── Port discovery ─────────────────────────────────────────────────────────────
// Three-layer strategy so the port is NEVER missed:
//  1. onBackendPort (push)  — main process sends it when Python prints the port
//  2. getPort() (pull)      — renderer polls main process after load (catches race)
//  3. HTTP probe fallback   — plain browser dev without Electron

;(window as any).__FADE_PORT__ = null

function broadcastPort(port: number) {
  if ((window as any).__FADE_PORT__ === port) return   // already known
  ;(window as any).__FADE_PORT__ = port
  window.dispatchEvent(new CustomEvent('fade:port', { detail: port }))
  console.log('[Fade] Backend port:', port)
}

const eAPI = (window as any).electronAPI

if (eAPI?.onBackendPort) {
  // Layer 1 — push: backend:port IPC from main process
  eAPI.onBackendPort((port: number) => broadcastPort(port))

  // Layer 2 — pull: ask main process for the stored port (handles timing race)
  let pollAttempts = 0
  const poll = async () => {
    if (pollAttempts++ > 20) return   // give up after 10 s — push path still works
    try {
      const port: number | null = await eAPI.getPort()
      if (port) {
        broadcastPort(port)
        return
      }
    } catch { /* handler not registered in old build — stop polling */ return }
    setTimeout(poll, 500)
  }
  poll()
} else {
  // Layer 3 — plain browser dev (no Electron): HTTP probe
  const tryPorts = async () => {
    for (const p of [8000, 8001, 8002]) {
      try {
        const r = await fetch(`http://127.0.0.1:${p}/health`, { signal: AbortSignal.timeout(500) })
        if (r.ok) { broadcastPort(p); return }
      } catch { /* try next */ }
    }
    setTimeout(tryPorts, 1000)
  }
  tryPorts()
}

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
