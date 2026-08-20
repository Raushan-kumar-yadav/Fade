/**
 * OverlayCanvas.tsx
 * 
 * Transparent SVG canvas overlaid on the viewport.
 * In 'pen' mode: Bezier control point editor.
 * In 'mask' mode: Same interaction for mask path editing.
 * 
 * Click to add points. Drag handles to adjust tangents.
 * Double-click to close/finish the path.
 */
import React, { useState, useCallback, useRef, useEffect } from 'react';
import './OverlayCanvas.css';
import { penApi, maskApi, type BezierPoint } from '../../api/toolsApi';

export type OverlayMode = 'pen' | 'mask' | 'none';

interface Props {
  mode:         OverlayMode;
  clipId?:      string;       // pen clip or clip with mask
  maskId?:      string;       // if mask mode
  width:        number;
  height:       number;
  viewScale?:   number;       // viewport zoom factor
  onDone?:      (clipId: string) => void;
}

interface PtState extends BezierPoint {
  id: string;
}

type DragTarget =
  | { kind: 'anchor'; idx: number }
  | { kind: 'inHandle';  idx: number }
  | { kind: 'outHandle'; idx: number }
  | null;

export default function OverlayCanvas({ mode, clipId, maskId, width, height, viewScale = 1, onDone }: Props) {
  const [points,   setPoints]   = useState<PtState[]>([]);
  const [closed,   setClosed]   = useState(false);
  const [dragging, setDragging] = useState<DragTarget>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const penClipId = useRef<string | null>(clipId ?? null);

  const svgPt = useCallback((e: React.MouseEvent) => {
    const svg = svgRef.current!;
    const rect = svg.getBoundingClientRect();
    return {
      x: (e.clientX - rect.left) / viewScale,
      y: (e.clientY - rect.top)  / viewScale,
    };
  }, [viewScale]);

  // ── Add point on click ───────────────────────────────────────────────────
  const handleSvgClick = useCallback((e: React.MouseEvent) => {
    if (e.target !== svgRef.current && (e.target as Element).tagName !== 'rect') return;
    if (closed) return;
    const { x, y } = svgPt(e);
    const id = crypto.randomUUID();
    setPoints(prev => [...prev, { id, x, y, inX: 0, inY: 0, outX: 0, outY: 0 }]);
  }, [closed, svgPt]);

  // ── Double-click = close path ────────────────────────────────────────────
  const handleDblClick = useCallback(() => {
    if (points.length >= 2) setClosed(true);
  }, [points.length]);

  // ── Drag logic ───────────────────────────────────────────────────────────
  const onDragStart = useCallback((target: DragTarget, e: React.MouseEvent) => {
    e.stopPropagation();
    setDragging(target);
  }, []);

  const onMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragging) return;
    const { x, y } = svgPt(e);
    setPoints(prev => {
      const pts = [...prev];
      const pt  = { ...pts[dragging!.idx] };
      if (dragging.kind === 'anchor') {
        const dx = x - pt.x;
        const dy = y - pt.y;
        pt.x += dx; pt.y += dy;
      } else if (dragging.kind === 'outHandle') {
        pt.outX = x - pt.x; pt.outY = y - pt.y;
        // mirror in handle
        pt.inX = -(pt.outX); pt.inY = -(pt.outY);
      } else {
        pt.inX = x - pt.x; pt.inY = y - pt.y;
        pt.outX = -(pt.inX); pt.outY = -(pt.inY);
      }
      pts[dragging.idx] = pt;
      return pts;
    });
  }, [dragging, svgPt]);

  const onMouseUp = useCallback(async () => {
    setDragging(null);
    await pushPoints();
  }, [points, closed, clipId, maskId, mode]);

  // ── Push points to backend ───────────────────────────────────────────────
  const pushPoints = useCallback(async () => {
    const bpts = points.map(({ x, y, inX, inY, outX, outY }) =>
      ({ x, y, inX, inY, outX, outY }));

    if (mode === 'pen') {
      if (!penClipId.current && points.length >= 1) {
        // Create pen clip on first point
        const clip: any = await penApi.add(0, 150, bpts, closed);
        penClipId.current = clip.clipId;
      } else if (penClipId.current) {
        await penApi.updatePoints(penClipId.current, bpts, closed);
      }
    } else if (mode === 'mask' && clipId && maskId) {
      await maskApi.update(clipId, maskId, { points: bpts });
    }
  }, [points, closed, mode, clipId, maskId]);

  // Push whenever closed changes
  useEffect(() => { if (closed && points.length >= 2) pushPoints(); }, [closed]);

  // ── Build SVG path string ─────────────────────────────────────────────────
  const pathD = buildPath(points, closed);

  return (
    <svg
      ref={svgRef}
      className="overlay-canvas"
      width={width} height={height}
      viewBox={`0 0 ${width} ${height}`}
      onClick={handleSvgClick}
      onDoubleClick={handleDblClick}
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
      onMouseLeave={onMouseUp}
    >
      {/* Hit area */}
      <rect width={width} height={height} fill="transparent" />

      {/* Path preview */}
      {pathD && (
        <path
          d={pathD}
          fill={closed ? 'rgba(99,102,241,0.15)' : 'none'}
          stroke="rgba(99,102,241,0.9)"
          strokeWidth={1.5}
        />
      )}

      {/* Control handles + anchor points */}
      {points.map((pt, i) => (
        <g key={pt.id}>
          {/* Out tangent handle line + circle */}
          {(pt.outX !== 0 || pt.outY !== 0) && <>
            <line
              x1={pt.x} y1={pt.y}
              x2={pt.x + pt.outX} y2={pt.y + pt.outY}
              stroke="rgba(251,191,36,0.7)" strokeWidth={1} strokeDasharray="3,2"
            />
            <circle
              cx={pt.x + pt.outX} cy={pt.y + pt.outY} r={4}
              fill="#fbbf24" stroke="#fff" strokeWidth={1}
              style={{ cursor: 'grab' }}
              onMouseDown={e => onDragStart({ kind: 'outHandle', idx: i }, e)}
            />
          </>}
          {/* In tangent handle */}
          {(pt.inX !== 0 || pt.inY !== 0) && <>
            <line
              x1={pt.x} y1={pt.y}
              x2={pt.x + pt.inX} y2={pt.y + pt.inY}
              stroke="rgba(251,191,36,0.7)" strokeWidth={1} strokeDasharray="3,2"
            />
            <circle
              cx={pt.x + pt.inX} cy={pt.y + pt.inY} r={4}
              fill="#fbbf24" stroke="#fff" strokeWidth={1}
              style={{ cursor: 'grab' }}
              onMouseDown={e => onDragStart({ kind: 'inHandle', idx: i }, e)}
            />
          </>}
          {/* Anchor point */}
          <rect
            x={pt.x - 5} y={pt.y - 5} width={10} height={10}
            fill="rgb(99,102,241)" stroke="#fff" strokeWidth={1.5} rx={1}
            style={{ cursor: 'move' }}
            onMouseDown={e => onDragStart({ kind: 'anchor', idx: i }, e)}
          />
        </g>
      ))}

      {/* Hint */}
      {points.length === 0 && (
        <text x={width / 2} y={height / 2} textAnchor="middle" fill="rgba(255,255,255,0.4)" fontSize={14}>
          Click to place points · Double-click to close
        </text>
      )}
    </svg>
  );
}

function buildPath(pts: PtState[], closed: boolean): string {
  if (pts.length === 0) return '';
  let d = `M ${pts[0].x},${pts[0].y}`;
  for (let i = 1; i < pts.length; i++) {
    const prev = pts[i - 1];
    const curr = pts[i];
    const c1x = prev.x + prev.outX; const c1y = prev.y + prev.outY;
    const c2x = curr.x + curr.inX;  const c2y = curr.y + curr.inY;
    if (prev.outX || prev.outY || curr.inX || curr.inY) {
      d += ` C ${c1x},${c1y} ${c2x},${c2y} ${curr.x},${curr.y}`;
    } else {
      d += ` L ${curr.x},${curr.y}`;
    }
  }
  if (closed && pts.length >= 2) {
    const last  = pts[pts.length - 1];
    const first = pts[0];
    const c1x = last.x + last.outX;   const c1y = last.y + last.outY;
    const c2x = first.x + first.inX;  const c2y = first.y + first.inY;
    if (last.outX || last.outY || first.inX || first.inY) {
      d += ` C ${c1x},${c1y} ${c2x},${c2y} ${first.x},${first.y}`;
    }
    d += ' Z';
  }
  return d;
}
