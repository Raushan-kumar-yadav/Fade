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
  const lastSubmitTime = useRef<number>(0);

  const submitStroke = async (pts: {x:number, y:number}[], inProgress: boolean = false) => {
    const compW = state.width || 1920;
    const compH = state.height || 1080;
    const validPoints = [];
    for (const p of pts) {
      const mapped = viewportToComposition(p.x, p.y, compW, compH, true);
      if (mapped) validPoints.push(mapped);
    }

    if (validPoints.length < 1) {
      if (!inProgress) {
        const ctx = canvasRef.current?.getContext('2d');
        if (ctx) ctx.clearRect(0, 0, width, height);
      }
      return;
    }
    
    try {
      const port = (window as any).__FADE_PORT__ || 8000;
      const endpoint = mode === 'brush' ? '/editor/brush' : '/editor/eraser';
      
      const payload: any = { 
        points: validPoints.map(p => ({ x: p.x, y: p.y, inX:0, inY:0, outX:0, outY:0 })), 
        size: brushSize, 
        color: brushColor 
      };
      
      if (mode === 'eraser') {
        payload.in_progress = inProgress;
      }
      
      await fetch(`http://127.0.0.1:${port}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      window.dispatchEvent(new CustomEvent('fade:tracks-changed'));
      window.dispatchEvent(new CustomEvent('fade:render-now'));
    } catch (e) {
      console.error('Failed to submit stroke', e);
    } finally {
      if (!inProgress) {
        const ctx = canvasRef.current?.getContext('2d');
        if (ctx) ctx.clearRect(0, 0, width, height);
      }
    }
  };

  const drawPoints = (ctx: CanvasRenderingContext2D, pts: {x:number, y:number}[]) => {
    ctx.clearRect(0, 0, width, height);
    if (pts.length < 1) return;
    
    if (pts.length >= 2) {
      ctx.beginPath();
      ctx.moveTo(pts[0].x, pts[0].y);
      for (let i = 1; i < pts.length; i++) {
        ctx.lineTo(pts[i].x, pts[i].y);
      }
      const [r, g, b, a] = brushColor;
      ctx.strokeStyle = mode === 'brush' ? 'rgba(' + Math.round(r*255) + ',' + Math.round(g*255) + ',' + Math.round(b*255) + ',' + a + ')' : 'rgba(255, 50, 50, 0.4)';
      ctx.lineWidth = brushSize;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.stroke();
    }
    
    // For eraser, draw a circle indicator at the current pointer
    if (mode === 'eraser' && pts.length > 0) {
      const lastPt = pts[pts.length - 1];
      ctx.beginPath();
      ctx.arc(lastPt.x, lastPt.y, brushSize, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.9)';
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(lastPt.x, lastPt.y, brushSize, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(0, 0, 0, 0.5)';
      ctx.lineWidth = 1;
      ctx.stroke();
    }
  };

  const getPt = (e: React.MouseEvent | MouseEvent) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    const x = (e.clientX - rect.left) * (width / rect.width);
    const y = (e.clientY - rect.top) * (height / rect.height);
    return { x, y };
  };

  const onDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    isDrawing.current = true;
    points.current = [getPt(e)];
    
    const ctx = canvasRef.current?.getContext('2d');
    if (ctx) drawPoints(ctx, points.current);
    
    if (mode === 'eraser') {
      submitStroke([...points.current], true);
      lastSubmitTime.current = Date.now();
    }
  };

  const onMove = (e: React.MouseEvent) => {
    if (!isDrawing.current && mode === 'eraser') {
      // Hover preview for eraser
      const ctx = canvasRef.current?.getContext('2d');
      if (ctx) {
        ctx.clearRect(0, 0, width, height);
        const pt = getPt(e);
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, brushSize, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.9)';
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, brushSize, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(0, 0, 0, 0.5)';
        ctx.lineWidth = 1;
        ctx.stroke();
      }
      return;
    }
    
    if (!isDrawing.current) return;
    points.current.push(getPt(e));
    
    const ctx = canvasRef.current?.getContext('2d');
    if (ctx) drawPoints(ctx, points.current);
    
    if (mode === 'eraser') {
      const now = Date.now();
      if (now - lastSubmitTime.current > 50) { // 20fps preview
        submitStroke([...points.current], true);
        lastSubmitTime.current = now;
      }
    }
  };

  const onUp = (e: React.MouseEvent) => {
    if (!isDrawing.current) return;
    isDrawing.current = false;
    
    submitStroke([...points.current], false);
    points.current = [];
  };
  
  const onLeave = (e: React.MouseEvent) => {
    if (mode === 'eraser' && !isDrawing.current) {
      const ctx = canvasRef.current?.getContext('2d');
      if (ctx) ctx.clearRect(0, 0, width, height);
    }
    onUp(e);
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
        onMouseLeave={onLeave}
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          cursor: mode === 'eraser' ? 'none' : 'crosshair',
          zIndex: 50,
        }}
      />
    </>
  );
}
