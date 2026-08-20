/**
 * OverlayCanvas.tsx
 *
 * Transparent SVG canvas overlaid on the viewport — After Effects style.
 *
 * Modes:
 *   'pen'   — Bezier path editor: click to add points, drag handles for tangents,
 *             Enter to commit, Escape to cancel, Double-click to close path.
 *   'shape' — Click + drag to draw bounding rectangle; on mouseup sends to backend.
 *   'mask'  — Same as pen but for clip masks.
 *   'none'  — Hidden.
 */
import React, { useState, useCallback, useRef, useEffect } from 'react';
import './OverlayCanvas.css';
import { penApi, shapeApi, maskApi, type BezierPoint } from '../../api/toolsApi';
import { useTool, shapeTypeOf } from '../../context/toolContext';

export type OverlayMode = 'pen' | 'mask' | 'shape' | 'none';

interface Props {
  mode:        OverlayMode;
  clipId?:     string;
  maskId?:     string;
  width:       number;
  height:      number;
  viewScale?:  number;
  startFrame?: number;
  duration?:   number;
  onDone?:     (clipId: string) => void;
}

interface PtState extends BezierPoint { id: string; }

type DragTarget =
  | { kind: 'anchor';    idx: number }
  | { kind: 'inHandle';  idx: number }
  | { kind: 'outHandle'; idx: number }
  | null;

// ── Coordinate helpers ─────────────────────────────────────────────────────────

function svgCoord(e: React.MouseEvent, el: SVGSVGElement, scale: number) {
  const rect = el.getBoundingClientRect();
  return {
    x: (e.clientX - rect.left) / scale,
    y: (e.clientY - rect.top)  / scale,
  };
}

// ──────────────────────────────────────────────────────────────────────────────

export default function OverlayCanvas({
  mode, clipId, maskId, width, height,
  viewScale = 1, startFrame = 0, duration = 150, onDone,
}: Props) {
  const { activeTool } = useTool();

  // ── Pen / Mask state ──────────────────────────────────────────────────────
  const [points,   setPoints]   = useState<PtState[]>([]);
  const [closed,   setClosed]   = useState(false);
  const [dragging, setDragging] = useState<DragTarget>(null);
  const penClipId = useRef<string | null>(clipId ?? null);

  // ── Shape-draw state ──────────────────────────────────────────────────────
  const [shapeStart, setShapeStart] = useState<{ x: number; y: number } | null>(null);
  const [shapeCur,   setShapeCur]   = useState<{ x: number; y: number } | null>(null);
  const shapeDrawing = useRef(false);

  // ── Cursor position for crosshair ─────────────────────────────────────────
  const [cursor, setCursor] = useState<{ x: number; y: number } | null>(null);

  const svgRef = useRef<SVGSVGElement>(null);
  const pt = useCallback((e: React.MouseEvent) =>
    svgRef.current ? svgCoord(e, svgRef.current, viewScale) : { x: 0, y: 0 },
    [viewScale]);

  // ── Keyboard shortcuts ────────────────────────────────────────────────────
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (mode === 'none') return;
      if (e.key === 'Enter') {
        if ((mode === 'pen' || mode === 'mask') && points.length >= 2) {
          setClosed(true);
          commitPoints(points, true);
        }
      }
      if (e.key === 'Escape') {
        setPoints([]); setClosed(false);
        setShapeStart(null); setShapeCur(null);
      }
      if (e.key === 'Backspace' || e.key === 'Delete') {
        setPoints(prev => prev.slice(0, -1));
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [mode, points]);

  // ── Shape-draw ────────────────────────────────────────────────────────────

  const onShapeDown = useCallback((e: React.MouseEvent) => {
    if (mode !== 'shape') return;
    const p = pt(e);
    setShapeStart(p); setShapeCur(p);
    shapeDrawing.current = true;
    e.preventDefault();
  }, [mode, pt]);

  const onShapeMove = useCallback((e: React.MouseEvent) => {
    const p = pt(e);
    setCursor(p);
    if (mode === 'shape' && shapeDrawing.current) setShapeCur(p);
  }, [mode, pt]);

  const onShapeUp = useCallback(async (e: React.MouseEvent) => {
    if (mode !== 'shape' || !shapeDrawing.current || !shapeStart) return;
    shapeDrawing.current = false;
    const end = pt(e);
    const w = Math.abs(end.x - shapeStart.x);
    const h = Math.abs(end.y - shapeStart.y);
    setShapeStart(null); setShapeCur(null);
    if (w < 4 || h < 4) return;

    const sType = shapeTypeOf(activeTool) ?? 'rect';
    try {
      const result: any = await shapeApi.add(startFrame, duration, {
        shapeType:     sType as any,
        width: w, height: h,
        radiusX:       w / 2, radiusY: h / 2,
        outerRadius:   Math.min(w, h) / 2,
        innerRadius:   Math.min(w, h) / 4,
        numPoints: 5,  numSides: 6,
        polygonRadius: Math.min(w, h) / 2,
        arcRadius:     Math.min(w, h) / 2,
        fillColor:     [0.4, 0.4, 1.0, 1.0],
      });
      onDone?.(result.clipId);
    } catch (err) {
      console.error('[OverlayCanvas] shape create error', err);
    }
  }, [mode, shapeStart, pt, activeTool, startFrame, duration, onDone]);

  // ── Pen / Mask ────────────────────────────────────────────────────────────

  const commitPoints = useCallback(async (pts: PtState[], isClosed: boolean) => {
    const bpts = pts.map(({ x, y, inX, inY, outX, outY }) =>
      ({ x, y, inX, inY, outX, outY }));
    if (mode === 'pen') {
      if (!penClipId.current && pts.length >= 1) {
        const clip: any = await penApi.add(startFrame, duration, bpts, isClosed);
        penClipId.current = clip.clipId;
        onDone?.(clip.clipId);
      } else if (penClipId.current) {
        await penApi.updatePoints(penClipId.current, bpts, isClosed);
      }
    } else if (mode === 'mask' && clipId && maskId) {
      await maskApi.update(clipId, maskId, { points: bpts });
    }
  }, [mode, clipId, maskId, startFrame, duration, onDone]);

  const onPenClick = useCallback((e: React.MouseEvent) => {
    if (mode !== 'pen' && mode !== 'mask') return;
    if ((e.target as Element).closest('circle, rect[data-anchor]')) return;
    if (closed) return;
    const { x, y } = pt(e);
    const id = crypto.randomUUID();
    setPoints(prev => [...prev, { id, x, y, inX: 0, inY: 0, outX: 0, outY: 0 }]);
  }, [mode, closed, pt]);

  const onDblClick = useCallback(() => {
    if ((mode === 'pen' || mode === 'mask') && points.length >= 2) setClosed(true);
  }, [mode, points.length]);

  const onDragStart = useCallback((target: DragTarget, e: React.MouseEvent) => {
    e.stopPropagation();
    setDragging(target);
  }, []);

  const onPenMove = useCallback((e: React.MouseEvent) => {
    const p = pt(e);
    setCursor(p);
    if (!dragging) return;
    const { x, y } = p;
    setPoints(prev => {
      const pts = [...prev];
      const pp  = { ...pts[dragging!.idx] };
      if (dragging.kind === 'anchor') {
        pp.x = x; pp.y = y;
      } else if (dragging.kind === 'outHandle') {
        pp.outX = x - pp.x; pp.outY = y - pp.y;
        pp.inX  = -pp.outX; pp.inY  = -pp.outY;
      } else {
        pp.inX  = x - pp.x; pp.inY  = y - pp.y;
        pp.outX = -pp.inX;  pp.outY = -pp.inY;
      }
      pts[dragging.idx] = pp;
      return pts;
    });
  }, [dragging, pt]);

  const onPenUp = useCallback(async () => {
    setDragging(null);
    await commitPoints(points, closed);
  }, [points, closed, commitPoints]);

  useEffect(() => {
    if (closed && points.length >= 2) commitPoints(points, true);
  }, [closed]);

  // ── Unified handlers ──────────────────────────────────────────────────────

  const handleMouseDown = mode === 'shape' ? onShapeDown : undefined;
  const handleMouseMove = (e: React.MouseEvent) =>
    mode === 'shape' ? onShapeMove(e) : onPenMove(e);
  const handleMouseUp   = (e: React.MouseEvent) =>
    mode === 'shape' ? onShapeUp(e)   : onPenUp();

  // ── Shape preview ─────────────────────────────────────────────────────────
  const shapePreview = shapeStart && shapeCur ? {
    x: Math.min(shapeStart.x, shapeCur.x),
    y: Math.min(shapeStart.y, shapeCur.y),
    w: Math.abs(shapeCur.x - shapeStart.x),
    h: Math.abs(shapeCur.y - shapeStart.y),
  } : null;

  const pathD = buildPath(points, closed);

  return (
    <svg
      ref={svgRef}
      className={`overlay-canvas overlay-canvas--${mode}`}
      width={width} height={height}
      viewBox={`0 0 ${width} ${height}`}
      onClick={onPenClick}
      onDoubleClick={onDblClick}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={() => setCursor(null)}
    >
      <rect width={width} height={height} fill="transparent" />

      {/* Crosshair guides */}
      {cursor && (mode === 'pen' || mode === 'mask' || mode === 'shape') && <>
        <line x1={cursor.x} y1={0}      x2={cursor.x} y2={height}
              stroke="rgba(99,102,241,0.3)" strokeWidth={0.5} strokeDasharray="4,3" />
        <line x1={0}        y1={cursor.y} x2={width}  y2={cursor.y}
              stroke="rgba(99,102,241,0.3)" strokeWidth={0.5} strokeDasharray="4,3" />
      </>}

      {/* Shape drag preview */}
      {shapePreview && <>
        <rect
          x={shapePreview.x} y={shapePreview.y}
          width={shapePreview.w} height={shapePreview.h}
          fill="rgba(99,102,241,0.12)"
          stroke="rgba(99,102,241,0.9)"
          strokeWidth={1.5} strokeDasharray="5,3"
        />
        <text
          x={shapePreview.x + shapePreview.w / 2} y={shapePreview.y - 4}
          textAnchor="middle" fill="rgba(99,102,241,0.9)"
          fontSize={10} fontFamily="Inter, sans-serif"
        >
          {Math.round(shapePreview.w)} × {Math.round(shapePreview.h)}
        </text>
      </>}

      {/* Pen path preview */}
      {pathD && (
        <path
          d={pathD}
          fill={closed ? 'rgba(99,102,241,0.12)' : 'none'}
          stroke="rgba(99,102,241,0.9)"
          strokeWidth={1.5}
        />
      )}

      {/* Bezier control handles + anchors */}
      {points.map((pp, i) => (
        <g key={pp.id}>
          {(pp.outX !== 0 || pp.outY !== 0) && <>
            <line x1={pp.x} y1={pp.y} x2={pp.x+pp.outX} y2={pp.y+pp.outY}
                  stroke="rgba(251,191,36,0.7)" strokeWidth={1} strokeDasharray="3,2" />
            <circle cx={pp.x+pp.outX} cy={pp.y+pp.outY} r={4}
                    fill="#fbbf24" stroke="#fff" strokeWidth={1} style={{ cursor: 'grab' }}
                    onMouseDown={e => onDragStart({ kind: 'outHandle', idx: i }, e)} />
          </>}
          {(pp.inX !== 0 || pp.inY !== 0) && <>
            <line x1={pp.x} y1={pp.y} x2={pp.x+pp.inX} y2={pp.y+pp.inY}
                  stroke="rgba(251,191,36,0.7)" strokeWidth={1} strokeDasharray="3,2" />
            <circle cx={pp.x+pp.inX} cy={pp.y+pp.inY} r={4}
                    fill="#fbbf24" stroke="#fff" strokeWidth={1} style={{ cursor: 'grab' }}
                    onMouseDown={e => onDragStart({ kind: 'inHandle', idx: i }, e)} />
          </>}
          <rect data-anchor="1"
                x={pp.x-5} y={pp.y-5} width={10} height={10}
                fill="rgb(99,102,241)" stroke="#fff" strokeWidth={1.5} rx={1}
                style={{ cursor: 'move' }}
                onMouseDown={e => onDragStart({ kind: 'anchor', idx: i }, e)} />
        </g>
      ))}

      {/* Empty-state hints */}
      {points.length === 0 && mode === 'pen' && (
        <text x={width/2} y={height/2} textAnchor="middle"
              fill="rgba(255,255,255,0.35)" fontSize={13} fontFamily="Inter, sans-serif">
          Click to place points · Double-click or Enter to close
        </text>
      )}
      {!shapeStart && mode === 'shape' && (
        <text x={width/2} y={height/2} textAnchor="middle"
              fill="rgba(255,255,255,0.35)" fontSize={13} fontFamily="Inter, sans-serif">
          Drag to draw shape · Escape to cancel
        </text>
      )}
    </svg>
  );
}

// ── Path builder ──────────────────────────────────────────────────────────────

function buildPath(pts: PtState[], closed: boolean): string {
  if (pts.length === 0) return '';
  let d = `M ${pts[0].x},${pts[0].y}`;
  for (let i = 1; i < pts.length; i++) {
    const prev = pts[i-1], curr = pts[i];
    const c1x = prev.x+prev.outX, c1y = prev.y+prev.outY;
    const c2x = curr.x+curr.inX,  c2y = curr.y+curr.inY;
    if (prev.outX || prev.outY || curr.inX || curr.inY)
      d += ` C ${c1x},${c1y} ${c2x},${c2y} ${curr.x},${curr.y}`;
    else
      d += ` L ${curr.x},${curr.y}`;
  }
  if (closed && pts.length >= 2) {
    const last  = pts[pts.length-1];
    const first = pts[0];
    const c1x = last.x+last.outX,   c1y = last.y+last.outY;
    const c2x = first.x+first.inX,  c2y = first.y+first.inY;
    if (last.outX || last.outY || first.inX || first.inY)
      d += ` C ${c1x},${c1y} ${c2x},${c2y} ${first.x},${first.y}`;
    d += ' Z';
  }
  return d;
}
