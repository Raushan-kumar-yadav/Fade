import React, { useRef, useEffect, useState } from 'react';
import { PIIDetection } from './PIITypes';

interface PIIOverlayProps {
  detections: PIIDetection[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onUpdateDetection: (id: string, updates: Partial<PIIDetection>) => void;
  // Canvas coordinate system helpers
  width: number;
  height: number;
}

export default function PIIOverlay({ 
  detections, 
  selectedId, 
  onSelect, 
  onUpdateDetection,
  width,
  height
}: PIIOverlayProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState<{ id: string; startX: number; startY: number; initBbox: any } | null>(null);
  const [resizing, setResizing] = useState<{ id: string; handle: string; startX: number; startY: number; initBbox: any } | null>(null);

  const handlePointerDown = (e: React.PointerEvent, det: PIIDetection, handle?: string) => {
    e.stopPropagation();
    onSelect(det.id);
    if (!det.bbox) return;

    if (handle) {
      setResizing({ id: det.id, handle, startX: e.clientX, startY: e.clientY, initBbox: { ...det.bbox } });
    } else {
      setDragging({ id: det.id, startX: e.clientX, startY: e.clientY, initBbox: { ...det.bbox } });
    }
    
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (dragging) {
      // Calculate delta in screen space, scale to canvas space.
      // Assuming container is 100% of the canvas and scales with it.
      // If the CSS transforms the container, we need to account for it, 
      // but in ViewportWidget the overlay is typically position: absolute 100% w/h over canvas.
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect) return;
      
      const scaleX = width / rect.width;
      const scaleY = height / rect.height;

      const dx = (e.clientX - dragging.startX) * scaleX;
      const dy = (e.clientY - dragging.startY) * scaleY;

      onUpdateDetection(dragging.id, {
        bbox: {
          ...dragging.initBbox,
          x: dragging.initBbox.x + dx,
          y: dragging.initBbox.y + dy,
        }
      });
    } else if (resizing) {
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect) return;
      
      const scaleX = width / rect.width;
      const scaleY = height / rect.height;

      const dx = (e.clientX - resizing.startX) * scaleX;
      const dy = (e.clientY - resizing.startY) * scaleY;

      const { handle, initBbox } = resizing;
      let newBbox = { ...initBbox };

      if (handle.includes('e')) newBbox.width += dx;
      if (handle.includes('s')) newBbox.height += dy;
      if (handle.includes('w')) {
        newBbox.x += dx;
        newBbox.width -= dx;
      }
      if (handle.includes('n')) {
        newBbox.y += dy;
        newBbox.height -= dy;
      }

      onUpdateDetection(resizing.id, { bbox: newBbox });
    }
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    setDragging(null);
    setResizing(null);
    (e.target as HTMLElement).releasePointerCapture(e.pointerId);
  };

  return (
    <div 
      ref={containerRef}
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        overflow: 'hidden'
      }}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
      onPointerDown={(e) => {
        if (e.target === containerRef.current) {
          onSelect(null);
        }
      }}
    >
      {detections.map(det => {
        if (!det.bbox || !det.enabled) return null;
        const isSelected = selectedId === det.id;
        
        // Convert canvas coordinates to percentages for CSS rendering
        // Use sourceWidth and sourceHeight from detection to map correctly onto the stretched canvas
        const srcW = det.sourceWidth || width;
        const srcH = det.sourceHeight || height;

        const leftPct = (det.bbox.x / srcW) * 100;
        const topPct = (det.bbox.y / srcH) * 100;
        const widthPct = (det.bbox.width / srcW) * 100;
        const heightPct = (det.bbox.height / srcH) * 100;

        return (
          <div
            key={det.id}
            onPointerDown={(e) => handlePointerDown(e, det)}
            style={{
              position: 'absolute',
              left: `${leftPct}%`,
              top: `${topPct}%`,
              width: `${widthPct}%`,
              height: `${heightPct}%`,
              border: `2px solid ${isSelected ? '#007acc' : '#ff5555'}`,
              backgroundColor: isSelected ? 'rgba(0, 122, 204, 0.2)' : 'rgba(255, 85, 85, 0.2)',
              pointerEvents: 'auto',
              cursor: isSelected ? 'move' : 'pointer',
              boxSizing: 'border-box'
            }}
          >
            {/* Label */}
            <div style={{
              position: 'absolute',
              top: -24,
              left: -2,
              backgroundColor: isSelected ? '#007acc' : '#ff5555',
              color: '#fff',
              fontSize: '12px',
              padding: '2px 6px',
              whiteSpace: 'nowrap',
              borderRadius: '2px 2px 0 0',
              pointerEvents: 'none'
            }}>
              {det.type}
            </div>

            {/* Resize Handles */}
            {isSelected && (
              <>
                <div onPointerDown={(e) => handlePointerDown(e, det, 'se')} style={{ position: 'absolute', right: -5, bottom: -5, width: 10, height: 10, background: '#fff', border: '1px solid #007acc', cursor: 'se-resize' }} />
                <div onPointerDown={(e) => handlePointerDown(e, det, 'sw')} style={{ position: 'absolute', left: -5, bottom: -5, width: 10, height: 10, background: '#fff', border: '1px solid #007acc', cursor: 'sw-resize' }} />
                <div onPointerDown={(e) => handlePointerDown(e, det, 'ne')} style={{ position: 'absolute', right: -5, top: -5, width: 10, height: 10, background: '#fff', border: '1px solid #007acc', cursor: 'ne-resize' }} />
                <div onPointerDown={(e) => handlePointerDown(e, det, 'nw')} style={{ position: 'absolute', left: -5, top: -5, width: 10, height: 10, background: '#fff', border: '1px solid #007acc', cursor: 'nw-resize' }} />
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}
