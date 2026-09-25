import React, { useRef, useState, useEffect } from 'react';
import { useTimeline } from '../timeline/TimelineContext';
import { useTool } from '../../context/toolContext';

import { viewportToComposition } from './viewportUtils';

interface Props {
  mode: 'brush' | 'eraser';
  width: number;
  height: number;
}

export default function BrushOverlay({ mode, width, height }: Props) {
  const { state, dispatch } = useTimeline();
  const { brushColor, brushSize } = useTool();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  
  const isDrawing = useRef(false);
  const points = useRef<{ x: number, y: number }[]>([]);

  const submitStroke = async (pts: {x:number, y:number}[]) => {
    const compW = state.width || 1920;
    const compH = state.height || 1080;
    const validPoints = [];
    for (const p of pts) {
      const mapped = viewportToComposition(p.x, p.y, compW, compH, true);
      if (mapped) validPoints.push(mapped);
    }

    if (validPoints.length < 2) {
      const ctx = canvasRef.current?.getContext('2d');
      if (ctx) ctx.clearRect(0, 0, width, height);
      return;
    }
    
    try {
      const port = (window as any).__FADE_PORT__ || 8000;
      const endpoint = mode === 'brush' ? '/editor/brush' : '/editor/eraser';
      await fetch(`http://127.0.0.1:${port}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ points: validPoints.map(p => ({ x: p.x, y: p.y, inX:0, inY:0, outX:0, outY:0 })), size: mode === 'brush' ? brushSize : 20, color: brushColor })
      });
      
      // 1. Trigger a refresh of the timeline tracks
      window.dispatchEvent(new CustomEvent('fade:tracks-changed'));
      
      // 2. Force the C++ native renderer to fetch and render the new frame
      window.dispatchEvent(new CustomEvent('fade:render-now'));
    } catch (e) {
      console.error('Failed to submit stroke', e);
    } finally {
      // 3. Only then clear the temporary local canvas
      const ctx = canvasRef.current?.getContext('2d');
      if (ctx) ctx.clearRect(0, 0, width, height);
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
    const [r, g, b, a] = brushColor;
    ctx.strokeStyle = mode === 'brush' ? 'rgba(' + Math.round(r*255) + ',' + Math.round(g*255) + ',' + Math.round(b*255) + ',' + a + ')' : 'rgba(255, 0, 0, 0.5)';
    ctx.lineWidth = mode === 'brush' ? brushSize : 20;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.stroke();
  };

  const getPt = (e: React.MouseEvent) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    const x = (e.clientX - rect.left) * (width / rect.width);
    const y = (e.clientY - rect.top) * (height / rect.height);
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
    
    // Submit the complete stroke to the backend (handles clearing)
    submitStroke([...points.current]);
    
    points.current = [];
  };

  return (
    <>
      <canvas
        ref={canvasRef}
        width={width}
        height={height}
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
    </>
  );
}



