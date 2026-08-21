/**
 * OverlayCanvas.tsx — After Effects style tool overlay
 *
 * Modes:
 *   'pen'   — click to add bezier points, drag handles for tangents
 *   'shape' — drag to draw bounding rectangle
 *   'mask'  — same as pen but for clip masks
 *   'none'  — hidden
 *
 * Coordinate system: SVG viewBox is always 1920×1080 (design space).
 * The SVG element stretches to fill the display area. All coordinates
 * stored/sent to the backend are in design-space pixels (0–1920, 0–1080).
 */
import React, { useState, useCallback, useRef, useEffect } from 'react';
import './OverlayCanvas.css';
import { penApi, shapeApi, maskApi, type BezierPoint } from '../../api/toolsApi';
import { useTool, shapeTypeOf } from '../../context/toolContext';
import type { PenSubMode } from '../../context/toolContext';

export type OverlayMode = 'pen' | 'mask' | 'shape' | 'none';

const DESIGN_W = 1920;
const DESIGN_H = 1080;

interface Props {
  mode:        OverlayMode;
  clipId?:     string;
  maskId?:     string;
  width:       number;   // display pixel width of the canvas area
  height:      number;   // display pixel height of the canvas area
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

// Convert a mouse/pointer event to design-space coords using the SVG element's CTM
function designCoord(e: React.MouseEvent, svg: SVGSVGElement): { x: number; y: number } {
  const pt = svg.createSVGPoint();
  pt.x = e.clientX;
  pt.y = e.clientY;
  const ctm = svg.getScreenCTM();
  if (!ctm) return { x: 0, y: 0 };
  const transformed = pt.matrixTransform(ctm.inverse());
  return { x: transformed.x, y: transformed.y };
}

export default function OverlayCanvas({
  mode, clipId, maskId, width, height,
  startFrame = 0, duration = 150, onDone,
}: Props) {
  const { activeTool, penSubMode, penOutputMode } = useTool();

  // ── Pen / Mask state ──────────────────────────────────────────────────────
  const [points,   setPoints]   = useState<PtState[]>([]);
  const [closed,   setClosed]   = useState(false);
  const [dragging, setDragging] = useState<DragTarget>(null);
  const [selectedIdx, setSelectedIdx] = useState<Set<number>>(new Set());
  const penClipId  = useRef<string | null>(clipId ?? null);
  const maskClipId = useRef<string | null>(clipId ?? null);   // target clip for mask
  const createdMaskId = useRef<string | null>(maskId ?? null); // backend mask id

  // ── Shape-draw state ──────────────────────────────────────────────────────
  const [shapeStart, setShapeStart] = useState<{ x: number; y: number } | null>(null);
  const [shapeCur,   setShapeCur]   = useState<{ x: number; y: number } | null>(null);
  const shapeDrawing = useRef(false);

  // ── Crosshair cursor ─────────────────────────────────────────────────────
  const [cursor, setCursor] = useState<{ x: number; y: number } | null>(null);

  // ── Viewport pan / zoom (space+drag or middle-mouse) ─────────────────────
  const [vpPan,  setVpPan]  = useState({ x: 0, y: 0 });
  const [vpZoom, setVpZoom] = useState(1);
  const panning     = useRef(false);
  const panOrigin   = useRef({ x: 0, y: 0 });
  const panStart    = useRef({ x: 0, y: 0 });
  const spaceDown   = useRef(false);

  const svgRef = useRef<SVGSVGElement>(null);

  const getDC = useCallback((e: React.MouseEvent) =>
    svgRef.current ? designCoord(e, svgRef.current) : { x: 0, y: 0 }, []);

  // ── Space key → pan mode ──────────────────────────────────────────────────
  useEffect(() => {
    const kd = (e: KeyboardEvent) => {
      if (e.code === 'Space') { e.preventDefault(); spaceDown.current = true; }
      if (mode === 'none') return;
      if (e.key === 'Enter' && (mode === 'pen' || mode === 'mask') && points.length >= 2) {
        setClosed(true); commitPoints(points, true);
      }
      if (e.key === 'Escape') {
        setPoints([]); setClosed(false);
        setShapeStart(null); setShapeCur(null);
      }
      if ((e.key === 'Backspace' || e.key === 'Delete') && !e.repeat) {
        setPoints(prev => prev.slice(0, -1));
      }
    };
    const ku = (e: KeyboardEvent) => {
      if (e.code === 'Space') spaceDown.current = false;
    };
    window.addEventListener('keydown', kd);
    window.addEventListener('keyup',   ku);
    return () => { window.removeEventListener('keydown', kd); window.removeEventListener('keyup', ku); };
  }, [mode, points]);

  // ── Wheel zoom ────────────────────────────────────────────────────────────
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey) return; // only ctrl/cmd+wheel = zoom
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.1 : 0.9;
      setVpZoom(z => Math.max(0.1, Math.min(20, z * factor)));
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, []);

  // ── Shape draw ────────────────────────────────────────────────────────────
  const onShapeDown = useCallback((e: React.MouseEvent) => {
    if (mode !== 'shape') return;
    const p = getDC(e);
    setShapeStart(p); setShapeCur(p);
    shapeDrawing.current = true;
    e.preventDefault();
  }, [mode, getDC]);

  const onShapeMove = useCallback((e: React.MouseEvent) => {
    const p = getDC(e);
    setCursor(p);
    if (mode === 'shape' && shapeDrawing.current) setShapeCur(p);
  }, [mode, getDC]);

  const onShapeUp = useCallback(async (e: React.MouseEvent) => {
    if (mode !== 'shape' || !shapeDrawing.current || !shapeStart) return;
    shapeDrawing.current = false;
    const end = getDC(e);

    // Bounding box in design space
    const x1 = Math.min(shapeStart.x, end.x);
    const y1 = Math.min(shapeStart.y, end.y);
    const x2 = Math.max(shapeStart.x, end.x);
    const y2 = Math.max(shapeStart.y, end.y);
    const w  = x2 - x1;
    const h  = y2 - y1;
    // Center of the drawn box (design-space pixels)
    const cx = (x1 + x2) / 2;
    const cy = (y1 + y2) / 2;

    setShapeStart(null); setShapeCur(null);
    if (w < 4 || h < 4) return;

    const sType = shapeTypeOf(activeTool) ?? 'rect';
    const halfW = w / 2;
    const halfH = h / 2;
    const minR  = Math.min(halfW, halfH);
    try {
      const result: any = await shapeApi.add(
        startFrame, duration,
        {
          shapeType:     sType as any,
          width:         w,
          height:        h,
          radiusX:       halfW,
          radiusY:       halfH,
          outerRadius:   minR,
          innerRadius:   minR * 0.45,
          numPoints:     5,
          numSides:      6,
          polygonRadius: minR,
          arcRadius:     minR,
          arcStartAngle: 0,
          arcSweepAngle: 270,
          x1:  -halfW, y1:  -halfH,   // line endpoints relative to center
          x2:   halfW, y2:   halfH,
          fillColor: [0.4, 0.4, 1.0, 1.0],
        },
        cx, cy,  // position = center of drawn box
      );
      window.dispatchEvent(new CustomEvent('fade:tracks-changed'));
      onDone?.(result.clipId);
    } catch (err) {
      console.error('[OverlayCanvas] shape create error', err);
    }
  }, [mode, shapeStart, getDC, activeTool, startFrame, duration, onDone]);

  // ── Pen / Mask ────────────────────────────────────────────────────────────
  const commitPoints = useCallback(async (pts: PtState[], isClosed: boolean) => {
    if (pts.length < 1) return;
    const bpts = pts.map(({ x, y, inX, inY, outX, outY }) => ({ x, y, inX, inY, outX, outY }));

    if (mode === 'pen') {
      if (!penClipId.current) {
        const clip: any = await penApi.add(startFrame, duration, bpts, isClosed);
        penClipId.current = clip.clipId;
        window.dispatchEvent(new CustomEvent('fade:tracks-changed'));
        onDone?.(clip.clipId);
      } else {
        await penApi.updatePoints(penClipId.current, bpts, isClosed);
      }
    } else if (mode === 'mask') {
      const targetClipId = maskClipId.current ?? clipId;
      if (!targetClipId) return;

      if (!createdMaskId.current) {
        // First commit — create the mask; use result.maskId (new stable field)
        const result = await maskApi.add(targetClipId, {
          shape: 'bezier', mode: 'add', points: bpts,
        });
        createdMaskId.current = result.maskId ?? null;
        console.log('[OverlayCanvas] mask created', result.maskId, 'pts', bpts.length);
        window.dispatchEvent(new CustomEvent('fade:masks-changed', { detail: targetClipId }));
        onDone?.(targetClipId);
      } else {
        // Subsequent commits — update the existing mask
        await maskApi.update(targetClipId, createdMaskId.current, { points: bpts, shape: 'bezier' });
        console.log('[OverlayCanvas] mask updated', createdMaskId.current, 'pts', bpts.length);
      }
    }
  }, [mode, clipId, maskId, startFrame, duration, onDone]);

  // ── Load existing mask on mount (mask mode) ───────────────────────────────
  // When the user re-selects the pen-mask tool for a clip that already has a
  // mask, fetch the existing points so the path is visible immediately.
  useEffect(() => {
    if (mode !== 'mask' || !clipId) return;
    let cancelled = false;
    (async () => {
      try {
        const { masks } = await maskApi.list(clipId);
        if (cancelled || masks.length === 0) return;
        // Use the maskId prop if given, otherwise take the last mask
        const target = maskId
          ? masks.find(m => m.maskId === maskId)
          : masks[masks.length - 1];
        if (!target || target.shape !== 'bezier') return;
        const pts = (target.points ?? []).map((p, i) => ({
          id: `loaded-${i}`,
          x: p.x, y: p.y,
          inX: p.inX ?? 0, inY: p.inY ?? 0,
          outX: p.outX ?? 0, outY: p.outY ?? 0,
        }));
        if (pts.length === 0) return;
        setPoints(pts);
        setClosed(true);
        createdMaskId.current = target.maskId;
        console.log('[OverlayCanvas] loaded existing mask', target.maskId, 'pts', pts.length);
      } catch (err) {
        console.warn('[OverlayCanvas] could not load existing mask', err);
      }
    })();
    return () => { cancelled = true; };
  }, [mode, clipId, maskId]);

  const onPenClick = useCallback((e: React.MouseEvent) => {
    if (mode !== 'pen' && mode !== 'mask') return;
    const target = e.target as Element;
    if (target.closest('circle') || target.getAttribute('data-anchor')) return;

    if (penSubMode === 'pen:add') {
      if (closed) return;
      const { x, y } = getDC(e);
      const id = crypto.randomUUID();
      const newPt = { id, x, y, inX: 0, inY: 0, outX: 0, outY: 0 };
      // Compute full updated list immediately so commitPoints has all N points
      // (mouseUp fires BEFORE click, so we can't rely on onPenUp having the new point)
      const newPoints = [...points, newPt];
      setPoints(newPoints);
      commitPoints(newPoints, closed);
    }
    // Other sub-modes (select, handle, delete, curve) handle via anchor events
  }, [mode, closed, getDC, penSubMode, points, commitPoints]);

  const onDblClick = useCallback(() => {
    if ((mode === 'pen' || mode === 'mask') && points.length >= 2) setClosed(true);
  }, [mode, points.length]);

  const onDragStart = useCallback((target: DragTarget, e: React.MouseEvent) => {
    e.stopPropagation();
    setDragging(target);
  }, []);

  const onPenMove = useCallback((e: React.MouseEvent) => {
    const p = getDC(e);
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
        pp.inX  = -pp.outX; pp.inY  = -pp.outY; // mirror
      } else {
        pp.inX  = x - pp.x; pp.inY  = y - pp.y;
        pp.outX = -pp.inX;  pp.outY = -pp.inY;
      }
      pts[dragging.idx] = pp;
      return pts;
    });
  }, [dragging, getDC]);

  // ── Sub-mode anchor event handlers ───────────────────────────────────────
  const onAnchorClick = useCallback((idx: number, e: React.MouseEvent) => {
    e.stopPropagation();
    if (penSubMode === 'pen:delete') {
      setPoints(prev => prev.filter((_, i) => i !== idx));
    } else if (penSubMode === 'pen:curve') {
      // Toggle corner ↔ smooth: if handles are 0, add default handles; if handles exist, remove
      setPoints(prev => {
        const pts = [...prev];
        const pp = { ...pts[idx] };
        const hasHandles = pp.inX !== 0 || pp.inY !== 0 || pp.outX !== 0 || pp.outY !== 0;
        if (hasHandles) {
          pp.inX = 0; pp.inY = 0; pp.outX = 0; pp.outY = 0;
        } else {
          // Auto-generate handles toward adjacent points
          const prev2 = pts[idx - 1];
          const next2 = pts[idx + 1];
          const dx = next2 ? (next2.x - (prev2?.x ?? pp.x)) / 3 : 40;
          const dy = next2 ? (next2.y - (prev2?.y ?? pp.y)) / 3 : 0;
          pp.outX = dx; pp.outY = dy; pp.inX = -dx; pp.inY = -dy;
        }
        pts[idx] = pp;
        return pts;
      });
    } else if (penSubMode === 'pen:select') {
      setSelectedIdx(prev => {
        const next = new Set(prev);
        if (next.has(idx)) next.delete(idx); else next.add(idx);
        return next;
      });
    }
  }, [penSubMode]);

  const onAnchorDragStart = useCallback((idx: number, e: React.MouseEvent) => {
    e.stopPropagation();
    if (penSubMode === 'pen:select' || penSubMode === 'pen:add') {
      onDragStart({ kind: 'anchor', idx }, e);
    }
  }, [penSubMode, onDragStart]);

  const onPenUp = useCallback(async () => {
    const wasDragging = dragging !== null;
    setDragging(null);
    // Only commit on mouseUp when finishing a handle-drag.
    // Plain clicks are handled inside onPenClick (which fires after mouseUp)
    // so that the new point is included in the commit.
    if (wasDragging) {
      await commitPoints(points, closed);
    }
  }, [dragging, points, closed, commitPoints]);

  useEffect(() => {
    if (closed && points.length >= 2) commitPoints(points, true);
  }, [closed]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Viewport pan logic ────────────────────────────────────────────────────
  const onPointerDown = useCallback((e: React.PointerEvent) => {
    if (e.button === 1 || spaceDown.current) {
      panning.current = true;
      panOrigin.current = { x: e.clientX, y: e.clientY };
      panStart.current  = { ...vpPan };
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
      e.preventDefault();
    }
  }, [vpPan]);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (panning.current) {
      const dx = e.clientX - panOrigin.current.x;
      const dy = e.clientY - panOrigin.current.y;
      setVpPan({ x: panStart.current.x + dx, y: panStart.current.y + dy });
    }
  }, []);

  const onPointerUp = useCallback((e: React.PointerEvent) => {
    panning.current = false;
  }, []);

  // ── Unified mouse handlers ─────────────────────────────────────────────────
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (mode === 'shape') onShapeDown(e);
  }, [mode, onShapeDown]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (mode === 'shape') onShapeMove(e);
    else onPenMove(e);
  }, [mode, onShapeMove, onPenMove]);

  const handleMouseUp = useCallback((e: React.MouseEvent) => {
    if (mode === 'shape') onShapeUp(e);
    else onPenUp();
  }, [mode, onShapeUp, onPenUp]);

  // ── Derived values ────────────────────────────────────────────────────────
  const shapePreview = shapeStart && shapeCur ? {
    x: Math.min(shapeStart.x, shapeCur.x),
    y: Math.min(shapeStart.y, shapeCur.y),
    w: Math.abs(shapeCur.x - shapeStart.x),
    h: Math.abs(shapeCur.y - shapeStart.y),
  } : null;

  const pathD = buildPath(points, closed);

  // Compute cursor CSS based on state
  const penCursorMap: Record<string, string> = {
    'pen:add':    'crosshair',
    'pen:select': 'default',
    'pen:handle': 'grab',
    'pen:delete': 'not-allowed',
    'pen:curve':  'cell',
  };
  const svgCursor = panning.current
    ? 'grabbing'
    : spaceDown.current
    ? 'grab'
    : (mode === 'pen' || mode === 'mask')
    ? (penCursorMap[penSubMode] ?? 'crosshair')
    : mode === 'shape'
    ? 'crosshair'
    : 'default';

  return (
    <svg
      ref={svgRef}
      className={`overlay-canvas overlay-canvas--${mode}`}
      width={width}
      height={height}
      viewBox={`0 0 ${DESIGN_W} ${DESIGN_H}`}
      preserveAspectRatio="xMidYMid meet"
      style={{ cursor: svgCursor, position: 'absolute', top: 0, left: 0 }}
      onClick={onPenClick}
      onDoubleClick={onDblClick}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={() => setCursor(null)}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
    >
      {/* Hit-test background */}
      <rect width={DESIGN_W} height={DESIGN_H} fill="transparent" />

      {/* Crosshair guides */}
      {cursor && (mode === 'pen' || mode === 'mask' || mode === 'shape') && <>
        <line x1={cursor.x} y1={0}        x2={cursor.x} y2={DESIGN_H}
              stroke="rgba(99,102,241,0.3)" strokeWidth={0.8} strokeDasharray="6,4" />
        <line x1={0}        y1={cursor.y} x2={DESIGN_W}  y2={cursor.y}
              stroke="rgba(99,102,241,0.3)" strokeWidth={0.8} strokeDasharray="6,4" />
        {/* Coord label */}
        <text x={cursor.x + 8} y={cursor.y - 6}
              fill="rgba(99,102,241,0.9)" fontSize={14} fontFamily="Inter, monospace">
          {Math.round(cursor.x)}, {Math.round(cursor.y)}
        </text>
      </>}

      {/* Shape drag preview — bounding box + actual shape */}
      {shapePreview && (() => {
        const { x, y, w, h } = shapePreview;
        const cx = x + w / 2;
        const cy = y + h / 2;
        const rx = w / 2;
        const ry = h / 2;
        const minR = Math.min(rx, ry);
        const sType = shapeTypeOf(activeTool) ?? 'rect';

        // Build star polygon points
        const starPoints = (outerR: number, innerR: number, n: number) => {
          const pts: string[] = [];
          for (let i = 0; i < n * 2; i++) {
            const r   = i % 2 === 0 ? outerR : innerR;
            const ang = (Math.PI / n) * i - Math.PI / 2;
            pts.push(`${cx + r * Math.cos(ang)},${cy + r * Math.sin(ang)}`);
          }
          return pts.join(' ');
        };
        const polyPoints = (r: number, n: number) => {
          const pts: string[] = [];
          for (let i = 0; i < n; i++) {
            const ang = (2 * Math.PI / n) * i - Math.PI / 2;
            pts.push(`${cx + r * Math.cos(ang)},${cy + r * Math.sin(ang)}`);
          }
          return pts.join(' ');
        };

        const sharedStyle = {
          fill:            'rgba(99,102,241,0.12)' as string,
          stroke:          'rgba(99,102,241,0.95)' as string,
          strokeWidth:     2 as number,
          strokeDasharray: '8,4' as string,
        };

        return (
          <>
            {/* Outer bounding guide */}
            <rect x={x} y={y} width={w} height={h}
              fill="none"
              stroke="rgba(99,102,241,0.3)"
              strokeWidth={1} strokeDasharray="4,4" />

            {/* Actual shape preview */}
            {sType === 'rect' && (
              <rect x={x} y={y} width={w} height={h} {...sharedStyle} />
            )}
            {(sType === 'circle' || sType === 'ellipse') && (
              <ellipse cx={cx} cy={cy} rx={rx} ry={ry} {...sharedStyle} />
            )}
            {sType === 'star' && (
              <polygon points={starPoints(minR, minR * 0.45, 5)} {...sharedStyle} />
            )}
            {sType === 'polygon' && (
              <polygon points={polyPoints(minR, 6)} {...sharedStyle} />
            )}
            {sType === 'line' && (
              <line x1={x} y1={y} x2={x + w} y2={y + h} {...sharedStyle} fill="none" />
            )}
            {sType === 'arc' && (
              <path
                d={`M ${cx} ${cy - minR} A ${minR} ${minR} 0 0 1 ${cx + minR} ${cy}`}
                {...sharedStyle} fill="none" />
            )}

            {/* Size label */}
            <rect
              x={cx - 36} y={y - 26} width={72} height={18}
              rx={4} fill="rgba(12,12,20,0.75)" />
            <text
              x={cx} y={y - 12}
              textAnchor="middle" fill="rgba(160,160,255,1)"
              fontSize={14} fontFamily="Inter, sans-serif" fontWeight={600}
            >
              {Math.round(w)} × {Math.round(h)}
            </text>
          </>
        );
      })()}

      {/* Pen path preview */}
      {pathD && (
        <path
          d={pathD}
          fill={closed ? 'rgba(99,102,241,0.1)' : 'none'}
          stroke="rgba(99,102,241,0.9)"
          strokeWidth={2}
        />
      )}

      {/* Bezier handles + anchors */}
      {points.map((pp, i) => (
        <g key={pp.id}>
          {(pp.outX !== 0 || pp.outY !== 0) && <>
            <line x1={pp.x} y1={pp.y} x2={pp.x + pp.outX} y2={pp.y + pp.outY}
                  stroke="rgba(251,191,36,0.7)" strokeWidth={1.5} strokeDasharray="4,3" />
            <circle cx={pp.x + pp.outX} cy={pp.y + pp.outY} r={6}
                    fill="#fbbf24" stroke="#fff" strokeWidth={1.5}
                    style={{ cursor: 'grab' }}
                    onMouseDown={e => { e.stopPropagation(); onDragStart({ kind: 'outHandle', idx: i }, e); }} />
          </>}
          {(pp.inX !== 0 || pp.inY !== 0) && <>
            <line x1={pp.x} y1={pp.y} x2={pp.x + pp.inX} y2={pp.y + pp.inY}
                  stroke="rgba(251,191,36,0.7)" strokeWidth={1.5} strokeDasharray="4,3" />
            <circle cx={pp.x + pp.inX} cy={pp.y + pp.inY} r={6}
                    fill="#fbbf24" stroke="#fff" strokeWidth={1.5}
                    style={{ cursor: 'grab' }}
                    onMouseDown={e => { e.stopPropagation(); onDragStart({ kind: 'inHandle', idx: i }, e); }} />
          </>}
          {/* Anchor square — color changes by sub-mode and selection */}
          <rect data-anchor="1"
                x={pp.x - 7} y={pp.y - 7} width={14} height={14}
                fill={
                  penSubMode === 'pen:delete' ? '#ef4444'
                  : penSubMode === 'pen:curve' ? '#f59e0b'
                  : selectedIdx.has(i) ? '#818cf8'
                  : 'rgb(99,102,241)'
                }
                stroke="#fff" strokeWidth={2} rx={2}
                style={{ cursor: penSubMode === 'pen:delete' ? 'not-allowed' : 'move' }}
                onClick={e => onAnchorClick(i, e)}
                onMouseDown={e => onAnchorDragStart(i, e)} />
          {/* Point index label */}
          <text x={pp.x + 10} y={pp.y - 10}
                fill="rgba(255,255,255,0.7)" fontSize={12} fontFamily="Inter, monospace">
            {i + 1}
          </text>
        </g>
      ))}

      {/* Empty-state hints */}
      {points.length === 0 && mode === 'pen' && (
        <text x={DESIGN_W / 2} y={DESIGN_H / 2} textAnchor="middle"
              fill="rgba(255,255,255,0.35)" fontSize={22} fontFamily="Inter, sans-serif">
          Click to place points · Double-click or Enter to close · Backspace to undo
        </text>
      )}
      {!shapeStart && mode === 'shape' && (
        <text x={DESIGN_W / 2} y={DESIGN_H / 2} textAnchor="middle"
              fill="rgba(255,255,255,0.35)" fontSize={22} fontFamily="Inter, sans-serif">
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
    const prev = pts[i - 1], curr = pts[i];
    const c1x = prev.x + prev.outX, c1y = prev.y + prev.outY;
    const c2x = curr.x + curr.inX,  c2y = curr.y + curr.inY;
    if (prev.outX || prev.outY || curr.inX || curr.inY)
      d += ` C ${c1x},${c1y} ${c2x},${c2y} ${curr.x},${curr.y}`;
    else
      d += ` L ${curr.x},${curr.y}`;
  }
  if (closed && pts.length >= 2) {
    const last  = pts[pts.length - 1];
    const first = pts[0];
    const c1x = last.x + last.outX,   c1y = last.y + last.outY;
    const c2x = first.x + first.inX,  c2y = first.y + first.inY;
    if (last.outX || last.outY || first.inX || first.inY)
      d += ` C ${c1x},${c1y} ${c2x},${c2y} ${first.x},${first.y}`;
    d += ' Z';
  }
  return d;
}
