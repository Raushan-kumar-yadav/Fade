import { useState, useRef, useCallback, useEffect, type ReactNode } from 'react'
import './FloatingWindow.css'
import FloatingAIChat from '../workspaces/FloatingAIChat'

export interface FloatingWindowProps {
  id: string
  title: string
  icon?: string
  defaultWidth?: number
  defaultHeight?: number
  defaultX?: number
  defaultY?: number
  minWidth?: number
  minHeight?: number
  children: ReactNode
  onClose?: () => void
  /** If true, window starts minimised to taskbar */
  defaultMinimized?: boolean
  /** Accent color for the header gradient */
  accent?: string
}

interface WinState {
  x: number
  y: number
  w: number
  h: number
  minimized: boolean
  maximized: boolean
  /** pre-maximize snapshot */
  snap: { x: number; y: number; w: number; h: number } | null
}

export default function FloatingWindow({
  id,
  title,
  icon = '⊞',
  defaultWidth = 720,
  defaultHeight = 480,
  defaultX,
  defaultY,
  minWidth = 320,
  minHeight = 240,
  children,
  onClose,
  defaultMinimized = false,
  accent = '#7c6fff',
}: FloatingWindowProps) {
  const initX = defaultX ?? Math.max(60, (window.innerWidth  - defaultWidth)  / 2)
  const initY = defaultY ?? Math.max(40, (window.innerHeight - defaultHeight) / 2)

  const [win, setWin] = useState<WinState>({
    x: initX, y: initY,
    w: defaultWidth, h: defaultHeight,
    minimized: defaultMinimized,
    maximized: false,
    snap: null,
  })
  const [zIndex, setZIndex] = useState(1000)
  const [aiOpen, setAiOpen] = useState(false)
  const ref    = useRef<HTMLDivElement>(null)
  const drag   = useRef<{ ox: number; oy: number; wx: number; wy: number } | null>(null)
  const resize = useRef<{ ox: number; oy: number; ow: number; oh: number; dir: string } | null>(null)

  // Bring to front on click
  const bringToFront = useCallback(() => {
    setZIndex(z => z < 9000 ? 9000 : z + 1)
  }, [])

  // ── Drag ──────────────────────────────────────────────────────────────────
  const onHeaderMouseDown = useCallback((e: React.MouseEvent) => {
    if (win.maximized) return
    e.preventDefault()
    bringToFront()
    drag.current = { ox: e.clientX, oy: e.clientY, wx: win.x, wy: win.y }

    const onMove = (ev: MouseEvent) => {
      if (!drag.current) return
      const nx = Math.max(0, Math.min(window.innerWidth  - 120, drag.current.wx + ev.clientX - drag.current.ox))
      const ny = Math.max(0, Math.min(window.innerHeight - 36,  drag.current.wy + ev.clientY - drag.current.oy))
      setWin(s => ({ ...s, x: nx, y: ny }))
    }
    const onUp = () => {
      drag.current = null
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }, [win.x, win.y, win.maximized, bringToFront])

  // ── Resize ────────────────────────────────────────────────────────────────
  const onResizeMouseDown = useCallback((e: React.MouseEvent, dir: string) => {
    e.preventDefault()
    e.stopPropagation()
    bringToFront()
    resize.current = { ox: e.clientX, oy: e.clientY, ow: win.w, oh: win.h, dir }

    const onMove = (ev: MouseEvent) => {
      if (!resize.current) return
      const dx = ev.clientX - resize.current.ox
      const dy = ev.clientY - resize.current.oy
      const { dir: d, ow, oh } = resize.current
      setWin(s => {
        let { x, y, w, h } = s
        if (d.includes('e')) w = Math.max(minWidth,  ow + dx)
        if (d.includes('s')) h = Math.max(minHeight, oh + dy)
        if (d.includes('w')) { w = Math.max(minWidth, ow - dx); x = s.x + (ow - w) }
        if (d.includes('n')) { h = Math.max(minHeight, oh - dy); y = s.y + (oh - h) }
        return { ...s, x, y, w, h }
      })
    }
    const onUp = () => {
      resize.current = null
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }, [win.w, win.h, minWidth, minHeight, bringToFront])

  // ── Maximize toggle ───────────────────────────────────────────────────────
  const toggleMaximize = useCallback(() => {
    setWin(s => {
      if (s.maximized) {
        const snap = s.snap ?? { x: initX, y: initY, w: defaultWidth, h: defaultHeight }
        return { ...s, maximized: false, snap: null, x: snap.x, y: snap.y, w: snap.w, h: snap.h }
      }
      return {
        ...s, maximized: true,
        snap: { x: s.x, y: s.y, w: s.w, h: s.h },
        x: 0, y: 0,
        w: window.innerWidth, h: window.innerHeight,
      }
    })
  }, [initX, initY, defaultWidth, defaultHeight])

  const toggleMinimize = useCallback(() => {
    setWin(s => ({ ...s, minimized: !s.minimized }))
  }, [])

  // Double-click header = maximize
  const onHeaderDblClick = useCallback(() => {
    toggleMaximize()
  }, [toggleMaximize])

  const style: React.CSSProperties = win.maximized
    ? { left: 0, top: 0, width: '100vw', height: '100vh', zIndex, borderRadius: 0 }
    : {
        left: win.x, top: win.y,
        width: win.w, height: win.minimized ? 'auto' : win.h,
        zIndex,
      }

  return (
    <div
      ref={ref}
      className={`fw-window${win.minimized ? ' fw-window--minimized' : ''}${win.maximized ? ' fw-window--maximized' : ''}`}
      style={style}
      onMouseDown={bringToFront}
    >
      {/* Header */}
      <div
        className="fw-header"
        style={{ '--fw-accent': accent } as any}
        onMouseDown={onHeaderMouseDown}
        onDoubleClick={onHeaderDblClick}
      >
        <span className="fw-icon">{icon}</span>
        <span className="fw-title">{title}</span>
        <div className="fw-controls">
          {/* Per-window AI chat toggle */}
          <button
            className="fw-btn fw-btn--ai"
            title="Toggle AI Assistant"
            onMouseDown={e => e.stopPropagation()}
            onClick={() => setAiOpen(v => !v)}
          >
            {aiOpen ? '✕' : '🤖'}
          </button>
          <button
            className="fw-btn fw-btn--min"
            title="Minimize"
            onMouseDown={e => e.stopPropagation()}
            onClick={toggleMinimize}
          >─</button>
          <button
            className="fw-btn fw-btn--max"
            title={win.maximized ? 'Restore' : 'Maximize'}
            onMouseDown={e => e.stopPropagation()}
            onClick={toggleMaximize}
          >{win.maximized ? '❐' : '□'}</button>
          {onClose && (
            <button
              className="fw-btn fw-btn--close"
              title="Close"
              onMouseDown={e => e.stopPropagation()}
              onClick={onClose}
            >✕</button>
          )}
        </div>
      </div>

      {/* Content */}
      {!win.minimized && (
        <div className="fw-body">
          {children}
          {/* Contained AI chat — stays inside this window */}
          {aiOpen && (
            <FloatingAIChat
              contained
              onClose={() => setAiOpen(false)}
            />
          )}
        </div>
      )}

      {/* Resize handles — 8 directions */}
      {!win.minimized && !win.maximized && (
        <>
          <div className="fw-resize fw-resize--n"  onMouseDown={e => onResizeMouseDown(e, 'n')} />
          <div className="fw-resize fw-resize--s"  onMouseDown={e => onResizeMouseDown(e, 's')} />
          <div className="fw-resize fw-resize--e"  onMouseDown={e => onResizeMouseDown(e, 'e')} />
          <div className="fw-resize fw-resize--w"  onMouseDown={e => onResizeMouseDown(e, 'w')} />
          <div className="fw-resize fw-resize--ne" onMouseDown={e => onResizeMouseDown(e, 'ne')} />
          <div className="fw-resize fw-resize--nw" onMouseDown={e => onResizeMouseDown(e, 'nw')} />
          <div className="fw-resize fw-resize--se" onMouseDown={e => onResizeMouseDown(e, 'se')} />
          <div className="fw-resize fw-resize--sw" onMouseDown={e => onResizeMouseDown(e, 'sw')} />
        </>
      )}
    </div>
  )
}
