import os

code = '''import React, { useRef, useState, useEffect } from 'react';
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
      await fetch(http://localhost:8000, {
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
    ctx.strokeStyle = mode === 'brush' ? '#ffffff' : 'rgba(255, 0, 0, 0.5)';
    ctx.lineWidth = mode === 'brush' ? 10 : 20;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.stroke();
  };

  const getPt = (e: React.MouseEvent) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    const x = (e.clientX - rect.left) * (1920 / rect.width);
    const y = (e.clientY - rect.top) * (1080 / rect.height);
    return { x, y };
  };

  const onDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    isDrawing.current = true;
    points.current = [getPt(e)];
    
    // Draw locally
    const ctx = canvasRef.current?.getContext('2d');
    if (ctx) drawPoints(ctx, points.current);
  };

  const onMove = (e: React.MouseEvent) => {
    if (!isDrawing.current) return;
    points.current.push(getPt(e));
    
    // Draw locally
    const ctx = canvasRef.current?.getContext('2d');
    if (ctx) drawPoints(ctx, points.current);
  };

  const onUp = (e: React.MouseEvent) => {
    if (!isDrawing.current) return;
    isDrawing.current = false;
    
    // Submit the complete stroke to the backend
    submitStroke(points.current);
    
    // Clear local canvas immediately so it transitions to backend render
    const ctx = canvasRef.current?.getContext('2d');
    if (ctx) ctx.clearRect(0, 0, width, height);
    
    points.current = [];
  };

  return (
    <canvas
      ref={canvasRef}
      width={1920}
      height={1080}
      onMouseDown={onDown}
      onMouseMove={onMove}
      onMouseUp={onUp}
      onMouseLeave={onUp}
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        cursor: 'crosshair',
        zIndex: 50,
      }}
    />
  );
}
'''

with open('src/workspaces/viewport/BrushOverlay.tsx', 'w', encoding='utf-8') as f:
    f.write(code)
