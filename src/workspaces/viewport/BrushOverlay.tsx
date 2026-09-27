import React, { useRef, useState, useEffect } from 'react';
import { useTimeline } from '../timeline/TimelineContext';

interface Props {
  mode: 'brush' | 'eraser';
  width: number;
  height: number;
}

export default function BrushOverlay({ mode, width, height }: Props) {
  const { dispatch } = useTimeline();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  
  const isDrawing = useRef(false);
  const points = useRef<{ x: number, y: number }[]>([]);

  const submitStroke = async (pts: {x:number, y:number}[]) => {
    if (pts.length < 2) return; // Prevent invisible 1-point clips
    
    try {
      const endpoint = mode === 'brush' ? '/editor/brush' : '/editor/eraser';
      await fetch(`http://127.0.0.1:${(window as any).__FADE_PORT__ || 8000}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ points: pts.map(p => ({ x: p.x, y: p.y, inX:0, inY:0, outX:0, outY:0 })), size: mode === 'brush' ? 10 : 20 })
      });
      
      // Trigger a refresh of the timeline tracks so the C++ renderer updates
      window.dispatchEvent(new CustomEvent('fade:tracks-changed'));
    } catch (e) {
      console.error('Failed to submit stroke', e);
    }
  };

  const drawPoints = (ctx: CanvasRenderingContext2D, pts: {x:number, y:number}[]) => {
    ctx.clearRect(0, 0, width, height);
    if (pts.length < 2) return;
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) {
      ctx.lineTo(pts[i].x, pts[i].y);
    }
    ctx.strokeStyle = mode === 'eraser' ? 'rgba(255,100,100,0.8)' : 'white';
    ctx.lineWidth = mode === 'eraser' ? 20 : 10;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.stroke();
  };

  const startDraw = (e: React.PointerEvent) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    isDrawing.current = true;
    points.current = [{
      x: (e.clientX - rect.left) * (width / rect.width),
      y: (e.clientY - rect.top) * (height / rect.height)
    }];
    (e.target as Element).setPointerCapture(e.pointerId);
  };

  const moveDraw = (e: React.PointerEvent) => {
    if (!isDrawing.current) return;
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    points.current.push({
      x: (e.clientX - rect.left) * (width / rect.width),
      y: (e.clientY - rect.top) * (height / rect.height)
    });
    
    const ctx = canvasRef.current?.getContext('2d');
    if (ctx) drawPoints(ctx, points.current);
  };

  const endDraw = (e: React.PointerEvent) => {
    if (!isDrawing.current) return;
    isDrawing.current = false;
    (e.target as Element).releasePointerCapture(e.pointerId);
    
    submitStroke([...points.current]);
    points.current = [];
    const ctx = canvasRef.current?.getContext('2d');
    if (ctx) ctx.clearRect(0, 0, width, height);
  };

  return (
    <canvas
      ref={canvasRef}
      width={width}
      height={height}
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        cursor: mode === 'eraser' ? 'cell' : 'crosshair',
        zIndex: 40 // Above video, below transport
      }}
      onPointerDown={startDraw}
      onPointerMove={moveDraw}
      onPointerUp={endDraw}
      onPointerCancel={endDraw}
    />
  );
}
