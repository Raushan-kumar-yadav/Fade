import { useState, useRef, useEffect, useCallback } from 'react'

const STORAGE_KEY = 'fade:ai-btn-pos'

function loadPos(): { x: number; y: number } {
  try {
    const s = localStorage.getItem(STORAGE_KEY)
    if (s) {
      const p = JSON.parse(s)
      // Clamp to current screen so a saved off-screen position never hides the button
      return {
        x: Math.max(0, Math.min(window.innerWidth  - 44, p.x)),
        y: Math.max(0, Math.min(window.innerHeight - 44, p.y)),
      }
    }
  } catch {}
  return { x: window.innerWidth - 56, y: 42 }
}

export default function DraggableAIButton({ onClick }: { onClick: () => void }) {
  const [pos, setPos] = useState(loadPos)
  const [dragging, setDragging] = useState(false)
  const dragRef = useRef<{ ox: number; oy: number; bx: number; by: number } | null>(null)
  const moved = useRef(false)
  const btnRef = useRef<HTMLButtonElement>(null)

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    moved.current = false
    dragRef.current = { ox: e.clientX, oy: e.clientY, bx: pos.x, by: pos.y }
    setDragging(true)

    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return
      const dx = ev.clientX - dragRef.current.ox
      const dy = ev.clientY - dragRef.current.oy
      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) moved.current = true
      const nx = Math.max(0, Math.min(window.innerWidth  - 44, dragRef.current.bx + dx))
      const ny = Math.max(0, Math.min(window.innerHeight - 44, dragRef.current.by + dy))
      setPos({ x: nx, y: ny })
    }

    const onUp = () => {
      dragRef.current = null
      setDragging(false)
      setPos(p => {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(p))
        return p
      })
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }

    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }, [pos])

  const handleClick = useCallback(() => {
    if (!moved.current) onClick()
  }, [onClick])

  return (
    <button
      ref={btnRef}
      id="global-ai-toggle-btn"
      title="AI Assistant — drag to move"
      onMouseDown={onMouseDown}
      onClick={handleClick}
      style={{
        position: 'fixed',
        left: pos.x,
        top: pos.y,
        zIndex: 8000,
        width: 44,
        height: 44,
        borderRadius: '50%',
        border: '1.5px solid rgba(124,111,255,0.55)',
        background: 'linear-gradient(135deg,#6c5fff,#a040f0)',
        backdropFilter: 'blur(8px)',
        color: '#fff',
        fontSize: 20,
        cursor: dragging ? 'grabbing' : 'grab',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        boxShadow: dragging
          ? '0 8px 32px rgba(100,80,255,0.7)'
          : '0 4px 20px rgba(100,80,255,0.45)',
        transform: dragging ? 'scale(1.12)' : 'scale(1)',
        transition: dragging ? 'box-shadow 0.1s, transform 0.1s' : 'box-shadow 0.15s, transform 0.15s',
        userSelect: 'none',
      }}
    >
      🤖
    </button>
  )
}
