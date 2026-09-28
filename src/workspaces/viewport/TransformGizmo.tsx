import React, { useState, useEffect, useRef } from 'react';
import { useSelection } from '../../context/selectionContext';
import { useTimeline } from '../timeline/TimelineContext';
import { inspectorApi, type ParamRow } from '../../api/inspectorApi';
import { compositionToViewport, viewportToComposition } from './viewportUtils';

function rotatePoint(px: number, py: number, cx: number, cy: number, angleDeg: number) {
  const rad = (angleDeg * Math.PI) / 180;
  const cos = Math.cos(rad);
  const sin = Math.sin(rad);
  const nx = px - cx;
  const ny = py - cy;
  return {
    x: nx * cos - ny * sin + cx,
    y: nx * sin + ny * cos + cy
  };
}

export default function TransformGizmo({ currentFrame, activeTool }: { currentFrame: number, activeTool: string }) {
  const { selected, setSelected } = useSelection();
  const { state } = useTimeline();
  const svgRef = useRef<SVGSVGElement>(null);
  
  const [params, setParams] = useState<ParamRow[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [dragType, setDragType] = useState<string | null>(null);
  const [mode, setMode] = useState<'normal' | 'crop'>('normal');
  const [hoveredHandle, setHoveredHandle] = useState<string | null>(null);
  const [svgScale, setSvgScale] = useState(1);

  const initialTransformRef = useRef<any>(null);
  const dragStartRef = useRef<{x: number, y: number}>({x: 0, y: 0});

  useEffect(() => {
    if (!svgRef.current) return;
    const observer = new ResizeObserver((entries) => {
      for (let entry of entries) {
        setSvgScale(1920 / entry.contentRect.width);
      }
    });
    observer.observe(svgRef.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    setMode('normal');
  }, [selected?.type === 'clip' ? selected.clipId : null, activeTool]);

  // Single param poll — provides transform values AND base_width/base_height
  // (backend now exposes those as hidden params for image/video/shape clips)
  useEffect(() => {
    if (!selected || selected.type !== 'clip') return;
    let isSubscribed = true;
    let timer: ReturnType<typeof setInterval> | null = null;
    const updateParams = async () => {
      try {
        const p = await inspectorApi.getParams(selected.clipId, currentFrame);
        if (isSubscribed && !isDragging) {
          setParams(p.params);
        }
      } catch (e: any) {
        const msg = (e instanceof Error ? e.message : String(e)).toLowerCase();
        if (msg.includes('not found') || msg.includes('404')) {
          if (timer !== null) { clearInterval(timer); timer = null; }
        }
      }
    };
    updateParams();
    timer = setInterval(updateParams, 100);
    return () => { isSubscribed = false; if (timer !== null) clearInterval(timer); };
  }, [selected, isDragging, currentFrame]);


  if (!selected || selected.type !== 'clip' || activeTool !== 'pointer') return null;

  const clip = state.tracks.flatMap(tr => tr.clips).find(c => c.id === selected.clipId);
  if (!clip) return null;

  const getParam = (id: string, defaultVal: number) => {
    const row = params.find(r => r.id === id);
    return row !== undefined ? row.value : defaultVal;
  };

  const px = getParam('pos_x', 0);
  const py = getParam('pos_y', 0);
  const sx = getParam('scale_x', 1);
  const sy = getParam('scale_y', 1);
  const rot = getParam('rotation', 0);
  const ax = getParam('anchor_x', 0);
  const ay = getParam('anchor_y', 0);
  // base_width/base_height come from the same params poll (added in backend/routers/clips.py)
  // Falls back to comp size which gives correct layout for shapes / text
  const baseWidth  = getParam('base_width',  state.width  || 1920);
  const baseHeight = getParam('base_height', state.height || 1080);

  const cropL = getParam('cropLeft', 0);
  const cropR = getParam('cropRight', 0);
  const cropT = getParam('cropTop', 0);
  const cropB = getParam('cropBottom', 0);

  const compW = state.width || 1920;
  const compH = state.height || 1080;

  // ── Bounding box in local (pre-transform) space ───────────────────────────
  // Mirrors exactly what the C++ renderer does:
  //
  // Shapes / text / pen:
  //   Drawn at their own pixel size, centered at 0,0 locally.
  //   pos_x=0 → top-left of comp (no center offset needed).
  //
  // Image / video:
  //   C++ applies object-fit:contain to fill the composition canvas, then
  //   draws the scaled image centered in that canvas.
  //   The resulting fitted dimensions are:
  //     fitScale = min(compW / imgW, compH / imgH)
  //     fittedW  = imgW * fitScale
  //     fittedH  = imgH * fitScale
  //   The bounding box in local space is [-fittedW/2, +fittedW/2] because
  //   the anchor is auto-normalized to 0.5 (comp center).
  //   pos_x=0 → comp center  (anchorX=0.5 in C++ → cx = compW/2).

  // ── C++ renderer constants ───────────────────────────────────────────────
  // The C++ HeadlessCompositor *always* renders into a 1920×1080 canvas
  // (m_width=1920, m_height=1080) regardless of the composition dimensions.
  // Therefore all image/video bounding-box math must use these renderer
  // dimensions, NOT compW/compH.
  const REND_W = 1920;
  const REND_H = 1080;

  let localMinX = 0, localMinY = 0, localMaxX = compW, localMaxY = compH;
  let imgW = compW, imgH = compH;       // native image pixels (from backend)
  let fittedW = compW, fittedH = compH; // what the C++ actually draws

  if (clip.type === 'shape') {
    imgW = getParam('shape_w', baseWidth);
    imgH = getParam('shape_h', baseHeight);
    fittedW = imgW;
    fittedH = imgH;
    localMinX = -fittedW / 2;
    localMinY = -fittedH / 2;
    localMaxX =  fittedW / 2;
    localMaxY =  fittedH / 2;
  } else if (clip.type === 'image' || clip.type === 'video') {
    imgW = baseWidth  || REND_W;
    imgH = baseHeight || REND_H;
    // C++ object-fit:contain into the 1920×1080 renderer canvas (not compW/compH)
    const fitScale = Math.min(REND_W / imgW, REND_H / imgH);
    fittedW = imgW * fitScale;
    fittedH = imgH * fitScale;
    localMinX = -fittedW / 2;
    localMinY = -fittedH / 2;
    localMaxX =  fittedW / 2;
    localMaxY =  fittedH / 2;
  }


  // Crop is a fraction of the fitted (visible) dimensions
  const visualMinX = localMinX + cropL * fittedW;
  const visualMaxX = localMaxX - cropR * fittedW;
  const visualMinY = localMinY + cropT * fittedH;
  const visualMaxY = localMaxY - cropB * fittedH;

  // ── Coordinate origin ─────────────────────────────────────────────────────
  // image/video: C++ translate(pos_x + REND_W/2, pos_y + REND_H/2) so
  //   pos_x=0 puts the clip center at the renderer canvas center (960, 540).
  //   SVG viewBox is also 0 0 1920 1080 = renderer space, so we add 960/540
  //   directly without going through compositionToViewport.
  // shape/text/pen: pos_x=0 is top-left of comp → still needs compositionToViewport.
  const isImageVideo = (clip.type === 'image' || clip.type === 'video');
  const originOffsetX = isImageVideo ? REND_W / 2 : 0;  // always 960 for img/vid
  const originOffsetY = isImageVideo ? REND_H / 2 : 0;  // always 540 for img/vid

  const applyMatrix = (pt: {x: number, y: number}) => {
    let nx = pt.x - ax; let ny = pt.y - ay;
    nx *= sx; ny *= sy;
    const rad = rot * Math.PI / 180;
    const cosA = Math.cos(rad); const sinA = Math.sin(rad);
    const rx = nx * cosA - ny * sinA;
    const ry = nx * sinA + ny * cosA;
    const worldX = rx + ax + px + originOffsetX;
    const worldY = ry + ay + py + originOffsetY;
    if (isImageVideo) {
      // Already in 1920×1080 renderer space = SVG space. No further transform.
      return { x: worldX, y: worldY };
    }
    return compositionToViewport(worldX, worldY, compW, compH);
  };

  const inverseApplyMatrix = (svgPt: {x: number, y: number}) => {
    // For image/video: SVG coords are already renderer/comp coords. No inverse needed.
    const worldX = isImageVideo ? svgPt.x : (viewportToComposition(svgPt.x, svgPt.y, compW, compH, false)?.x ?? svgPt.x);
    const worldY = isImageVideo ? svgPt.y : (viewportToComposition(svgPt.x, svgPt.y, compW, compH, false)?.y ?? svgPt.y);
    let rx = worldX - ax - px - originOffsetX;
    let ry = worldY - ay - py - originOffsetY;
    const rad = -rot * Math.PI / 180;
    const cosA = Math.cos(rad); const sinA = Math.sin(rad);
    let nx = rx * cosA - ry * sinA;
    let ny = rx * sinA + ry * cosA;
    nx /= (sx === 0 ? 0.001 : sx);
    ny /= (sy === 0 ? 0.001 : sy);
    return { x: nx + ax, y: ny + ay };
  };



  const vCorners = [
    { x: visualMinX, y: visualMinY }, { x: visualMaxX, y: visualMinY },
    { x: visualMaxX, y: visualMaxY }, { x: visualMinX, y: visualMaxY }
  ].map(applyMatrix);

  // DEBUG — remove after fixing offset
  if (isImageVideo) {
    console.log('[Gizmo]', {
      clipType: clip.type,
      compW, compH,
      baseWidth, baseHeight,
      fittedW, fittedH,
      px, py, ax, ay, sx, sy, rot,
      originOffsetX, originOffsetY,
      localMinX, localMaxX,
      visualMinX, visualMaxX,
      topLeftSVG: vCorners[0],
      topRightSVG: vCorners[1],
      // C++ expected left edge = originOffsetX - fittedW/2 + px  (for scale=1, no rot)
      expectedCppLeft: (compW / 2) - (fittedW / 2) + px,
    });
  }



  const edgeMidpoints = [
    { x: (vCorners[0].x + vCorners[1].x) / 2, y: (vCorners[0].y + vCorners[1].y) / 2 },
    { x: (vCorners[1].x + vCorners[2].x) / 2, y: (vCorners[1].y + vCorners[2].y) / 2 },
    { x: (vCorners[2].x + vCorners[3].x) / 2, y: (vCorners[2].y + vCorners[3].y) / 2 },
    { x: (vCorners[3].x + vCorners[0].x) / 2, y: (vCorners[3].y + vCorners[0].y) / 2 },
  ];

  const polygonPoints = vCorners.map(p => `${p.x},${p.y}`).join(' ');

  const fCorners = [
    { x: localMinX, y: localMinY }, { x: localMaxX, y: localMinY },
    { x: localMaxX, y: localMaxY }, { x: localMinX, y: localMaxY }
  ].map(applyMatrix);

  const dimPath = `M0,0 L1920,0 L1920,1080 L0,1080 Z M${vCorners[0].x},${vCorners[0].y} L${vCorners[3].x},${vCorners[3].y} L${vCorners[2].x},${vCorners[2].y} L${vCorners[1].x},${vCorners[1].y} Z`;

  const rotDist = 50 * svgScale;
  const radRot = rot * Math.PI / 180;
  const rotHandle = {
    x: edgeMidpoints[2].x + Math.sin(radRot + Math.PI) * rotDist * Math.sign(sy || 1),
    y: edgeMidpoints[2].y - Math.cos(radRot + Math.PI) * rotDist * Math.sign(sy || 1)
  }; // Moved to Bottom edge Canva-style

  const designCoord = (e: React.PointerEvent) => {
    if (!svgRef.current) return { x: 0, y: 0 };
    const rect = svgRef.current.getBoundingClientRect();
    return {
      x: (e.clientX - rect.left) * (1920 / rect.width),
      y: (e.clientY - rect.top) * (1080 / rect.height)
    };
  };

  const handleSvgPointerDown = (e: React.PointerEvent) => {
    const pt = designCoord(e);
    let inside = false;
    const poly = mode === 'crop' ? fCorners : vCorners;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
        const xi = poly[i].x, yi = poly[i].y;
        const xj = poly[j].x, yj = poly[j].y;
        const intersect = ((yi > pt.y) !== (yj > pt.y)) && (pt.x < (xj - xi) * (pt.y - yi) / (yj - yi) + xi);
        if (intersect) inside = !inside;
    }
    
    if (inside) {
       e.stopPropagation();
       initialTransformRef.current = { px, py, sx, sy, rot, ax, ay, cropL, cropR, cropT, cropB, localMinX, localMaxX, localMinY, localMaxY, imgW, imgH, fittedW, fittedH };
       dragStartRef.current = pt;
       setDragType('move');
       setIsDragging(true);
       (e.target as Element).setPointerCapture(e.pointerId);
    } else {
       setSelected(null);
       setMode('normal');
    }
  };

  const handlePointerDown = (e: React.PointerEvent, type: string) => {
    e.stopPropagation();
    const startCoord = designCoord(e);
    let startMouseAngle = 0;
    if (type === 'rotate') {
       const objCenter = applyMatrix({x: 0, y: 0});
       startMouseAngle = Math.atan2(startCoord.y - objCenter.y, startCoord.x - objCenter.x);
    }
    
    initialTransformRef.current = { 
       px, py, sx, sy, rot, ax, ay, 
       cropL, cropR, cropT, cropB, 
       localMinX, localMaxX, localMinY, localMaxY,
       imgW, imgH,
       fittedW, fittedH,   // ← actual drawn size, used for crop delta math
       startMouseAngle
    } as any;
    
    dragStartRef.current = startCoord;
    setDragType(type);
    setIsDragging(true);
    (e.target as Element).setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!isDragging || !initialTransformRef.current) return;
    const pt = designCoord(e);
    const init = initialTransformRef.current;
    let next = { ...init };
    
    if (dragType === 'move') {
      if (mode === 'crop') {
         const dxLocal = inverseApplyMatrix(pt).x - inverseApplyMatrix(dragStartRef.current).x;
         const dyLocal = inverseApplyMatrix(pt).y - inverseApplyMatrix(dragStartRef.current).y;
         // SVG space = renderer space for image/video → scaleFactor = 1
         const sf = isImageVideo ? 1 : Math.min(REND_W / compW, REND_H / compH);
         next.px += (pt.x - dragStartRef.current.x) / sf;
         next.py += (pt.y - dragStartRef.current.y) / sf;
         
         next.cropL = Math.max(0, Math.min(1, init.cropL - dxLocal / init.fittedW));
         next.cropR = Math.max(0, Math.min(1, init.cropR + dxLocal / init.fittedW));
         next.cropT = Math.max(0, Math.min(1, init.cropT - dyLocal / init.fittedH));
         next.cropB = Math.max(0, Math.min(1, init.cropB + dyLocal / init.fittedH));
      } else {
         // designCoord returns SVG coords (= renderer 1920x1080 space) → delta = pos delta
         next.px = init.px + (pt.x - dragStartRef.current.x);
         next.py = init.py + (pt.y - dragStartRef.current.y);
      }
    } 
    else if (dragType === 'rotate') {
         const objectCenter = applyMatrix({x: 0, y: 0});
         const currentMouseAngle = Math.atan2(pt.y - objectCenter.y, pt.x - objectCenter.x);
         let deltaAngle = currentMouseAngle - (init as any).startMouseAngle;
         
         if (deltaAngle > Math.PI) deltaAngle -= 2 * Math.PI;
         if (deltaAngle < -Math.PI) deltaAngle += 2 * Math.PI;
         
         next.rot = init.rot + (deltaAngle * 180 / Math.PI);
         
         next.px = init.px;
         next.py = init.py;
         next.sx = init.sx;
         next.sy = init.sy;
         next.ax = init.ax;
         next.ay = init.ay;
      } 
    else if (dragType?.startsWith('resize_')) {
       const isEdge = dragType.includes('edge');
       const index = parseInt(dragType.split('_').pop()!, 10);
       const oppIndex = (index + 2) % 4;
       
       const startLocalCorners = [
         { x: init.localMinX + init.cropL * init.fittedW, y: init.localMinY + init.cropT * init.fittedH },
         { x: init.localMaxX - init.cropR * init.fittedW, y: init.localMinY + init.cropT * init.fittedH },
         { x: init.localMaxX - init.cropR * init.fittedW, y: init.localMaxY - init.cropB * init.fittedH },
         { x: init.localMinX + init.cropL * init.fittedW, y: init.localMaxY - init.cropB * init.fittedH }
       ];
       
       let dragLocal = startLocalCorners[index];
       let oppLocal = startLocalCorners[oppIndex];
       
       if (isEdge) {
           dragLocal = { x: (startLocalCorners[index].x + startLocalCorners[(index+1)%4].x)/2, y: (startLocalCorners[index].y + startLocalCorners[(index+1)%4].y)/2 };
           oppLocal = { x: (startLocalCorners[oppIndex].x + startLocalCorners[(oppIndex+1)%4].x)/2, y: (startLocalCorners[oppIndex].y + startLocalCorners[(oppIndex+1)%4].y)/2 };
       }
       
       const curLocal = inverseApplyMatrix(pt);
       const dxDrag = dragLocal.x - oppLocal.x;
       const dyDrag = dragLocal.y - oppLocal.y;
       const dxCur = curLocal.x - oppLocal.x;
       const dyCur = curLocal.y - oppLocal.y;
       
       if (isEdge) {
           if (index === 0 || index === 2) { 
               if (Math.abs(dyDrag) > 0.01) next.sy = init.sy * (dyCur / dyDrag);
           } else { 
               if (Math.abs(dxDrag) > 0.01) next.sx = init.sx * (dxCur / dxDrag);
           }
       } else {
           let scaleFactor = 1;
           if (Math.abs(dxDrag) > Math.abs(dyDrag) && Math.abs(dxDrag) > 0.01) scaleFactor = dxCur / dxDrag;
           else if (Math.abs(dyDrag) > 0.01) scaleFactor = dyCur / dyDrag;
           next.sx = init.sx * scaleFactor;
           next.sy = init.sy * scaleFactor;
       }
       
       const calcWorld = (lPt: {x: number, y: number}, state: any) => {
          let nx = lPt.x - state.ax; let ny = lPt.y - state.ay;
          nx *= state.sx; ny *= state.sy;
          const r = state.rot * Math.PI / 180;
          const cx = Math.cos(r); const sx = Math.sin(r);
          return {
             x: nx * cx - ny * sx + state.ax + state.px,
             y: nx * sx + ny * cx + state.ay + state.py
          };
       };
       
       const oldW = calcWorld(oppLocal, init);
       const newW = calcWorld(oppLocal, next);
       next.px += (oldW.x - newW.x);
       next.py += (oldW.y - newW.y);
    }
    else if (dragType?.startsWith('crop_')) {
       const cornerIndex = parseInt(dragType.split('_')[1], 10);
       const localPt = inverseApplyMatrix(pt);
       
       if (cornerIndex === 0 || cornerIndex === 3) {
          next.cropL = Math.max(0, Math.min(1 - next.cropR, (localPt.x - init.localMinX) / init.fittedW));
       }
       if (cornerIndex === 1 || cornerIndex === 2) {
          next.cropR = Math.max(0, Math.min(1 - next.cropL, (init.localMaxX - localPt.x) / init.fittedW));
       }
       if (cornerIndex === 0 || cornerIndex === 1) {
          next.cropT = Math.max(0, Math.min(1 - next.cropB, (localPt.y - init.localMinY) / init.fittedH));
       }
       if (cornerIndex === 2 || cornerIndex === 3) {
          next.cropB = Math.max(0, Math.min(1 - next.cropT, (init.localMaxY - localPt.y) / init.fittedH));
       }
    }

    setParams(prev => {
      const nextParams = [...prev];
      const updateOrAdd = (id: string, value: number) => {
         const idx = nextParams.findIndex(p => p.id === id);
         if (idx >= 0) nextParams[idx] = { ...nextParams[idx], value };
         else nextParams.push({ id, value, type: 'number' } as any);
      };
      updateOrAdd('pos_x', next.px);
      updateOrAdd('pos_y', next.py);
      updateOrAdd('scale_x', next.sx);
      updateOrAdd('scale_y', next.sy);
      updateOrAdd('rotation', next.rot);
      updateOrAdd('cropLeft', next.cropL);
      updateOrAdd('cropRight', next.cropR);
      updateOrAdd('cropTop', next.cropT);
      updateOrAdd('cropBottom', next.cropB);
      return nextParams;
    });

    inspectorApi.setParam(selected.clipId, 'pos_x', next.px);
    inspectorApi.setParam(selected.clipId, 'pos_y', next.py);
    inspectorApi.setParam(selected.clipId, 'scale_x', next.sx);
    inspectorApi.setParam(selected.clipId, 'scale_y', next.sy);
    inspectorApi.setParam(selected.clipId, 'rotation', next.rot);
    if (mode === 'crop') {
       inspectorApi.setParam(selected.clipId, 'cropLeft', next.cropL);
       inspectorApi.setParam(selected.clipId, 'cropRight', next.cropR);
       inspectorApi.setParam(selected.clipId, 'cropTop', next.cropT);
       inspectorApi.setParam(selected.clipId, 'cropBottom', next.cropB);
    }
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    if (!isDragging || !initialTransformRef.current) return;
    setIsDragging(false);
    setDragType(null);
    (e.target as Element).releasePointerCapture(e.pointerId);

    const init = initialTransformRef.current;
    const finalParams = {
      pos_x: getParam('pos_x', init.px), pos_y: getParam('pos_y', init.py),
      scale_x: getParam('scale_x', init.sx), scale_y: getParam('scale_y', init.sy),
      rotation: getParam('rotation', init.rot)
    } as any;
    
    if (mode === 'crop') {
      finalParams.cropLeft = getParam('cropLeft', init.cropL);
      finalParams.cropRight = getParam('cropRight', init.cropR);
      finalParams.cropTop = getParam('cropTop', init.cropT);
      finalParams.cropBottom = getParam('cropBottom', init.cropB);
      
      init.cropLeft = init.cropL; init.cropRight = init.cropR;
      init.cropTop = init.cropT; init.cropBottom = init.cropB;
    }
    
    fetch(`http://127.0.0.1:${(window as any).__FADE_PORT__ || 8000}/clips/transform-batch`, {
       method: 'POST', headers: { 'Content-Type': 'application/json' },
       body: JSON.stringify({ clip_id: selected.clipId, before: init, after: finalParams })
    }).catch(() => {});
  };

  const toolbarHeight = 60 * svgScale;
  const toolbarWidth = 240 * svgScale;
  const minY = Math.min(...vCorners.map(p => p.y));
  const maxY = Math.max(...vCorners.map(p => p.y));
  
  let ty = minY - toolbarHeight - (16 * svgScale);
  if (ty < 0) {
      ty = maxY + (16 * svgScale);
      if (ty + toolbarHeight > 1080) {
          ty = Math.max(0, minY + (16 * svgScale)); // clamp inside if massive
      }
  }
  
  let tx = (vCorners[0].x + vCorners[1].x) / 2 - (toolbarWidth / 2);
  tx = Math.max(0, Math.min(1920 - toolbarWidth, tx));

  const toolbarPos = { x: tx, y: ty };

  // Canva Style Styling
  const cornerR = 8 * svgScale;
  const edgeW = 28 * svgScale;
  const edgeH = 8 * svgScale;
  const hitR = 24 * svgScale;
  const strokeW = 2 * svgScale;
  const brandColor = "#8b3dff"; // Canva Purple
  const glowColor = "rgba(139, 61, 255, 0.4)";

  return (
    <svg 
      ref={svgRef} 
      style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 50 }} 
      viewBox="0 0 1920 1080" preserveAspectRatio="xMidYMid meet"
    >
      <rect 
        width={1920} height={1080} fill="transparent"
        pointerEvents="all" 
        onPointerDown={handleSvgPointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
      />
      
      {mode === 'crop' && (
        <path 
          d={dimPath}
          fill="rgba(0,0,0,0.65)"
          fillRule="evenodd"
          pointerEvents="none"
        />
      )}

      {mode === 'normal' && (
        <>
                      <polygon points={polygonPoints} fill="transparent" stroke={brandColor} strokeWidth={strokeW} pointerEvents="none" />
            
            {/* Pivot Marker — use same coordinate transform as the gizmo corners */}
            {(() => {
              const pivot = compositionToViewport(
                ax + px + originOffsetX,
                ay + py + originOffsetY,
                compW, compH
              );
              return (
                <>
                  <circle cx={pivot.x} cy={pivot.y} r={4 * svgScale} fill="#0f0" pointerEvents="none" />
                  <circle cx={pivot.x} cy={pivot.y} r={6 * svgScale} fill="transparent" stroke="#0f0" strokeWidth={2 * svgScale} pointerEvents="none" />
                </>
              );
            })()}

          {/* Canva Rotation Handle - Below Image */}
          <g 
             onPointerEnter={() => setHoveredHandle('rotate')}
             onPointerLeave={() => setHoveredHandle(null)}
             onPointerDown={(e) => handlePointerDown(e, 'rotate')}
             onPointerMove={handlePointerMove} onPointerUp={handlePointerUp}
             style={{ cursor: 'crosshair', pointerEvents: 'all' }}
          >
             <circle cx={rotHandle.x} cy={rotHandle.y} r={hitR} fill="transparent" />
             {hoveredHandle === 'rotate' && <circle cx={rotHandle.x} cy={rotHandle.y} r={cornerR * 2} fill={glowColor} pointerEvents="none" />}
             <circle cx={rotHandle.x} cy={rotHandle.y} r={cornerR * 1.6} fill="#ffffff" stroke="rgba(0,0,0,0.15)" strokeWidth={strokeW * 1.5} pointerEvents="none" />
             <circle cx={rotHandle.x} cy={rotHandle.y} r={cornerR * 1.6} fill="#ffffff" stroke={brandColor} strokeWidth={strokeW} pointerEvents="none" />
             <path 
                d={`M${rotHandle.x - cornerR*0.6} ${rotHandle.y} A ${cornerR*0.6} ${cornerR*0.6} 0 1 1 ${rotHandle.x + cornerR*0.6} ${rotHandle.y}`} 
                fill="transparent" stroke={brandColor} strokeWidth={strokeW * 0.8} strokeLinecap="round" pointerEvents="none" 
             />
             <polygon points={`${rotHandle.x + cornerR*0.4},${rotHandle.y + cornerR*0.2} ${rotHandle.x + cornerR*0.8},${rotHandle.y + cornerR*0.2} ${rotHandle.x + cornerR*0.6},${rotHandle.y + cornerR*0.5}`} fill={brandColor} pointerEvents="none" />
          </g>

          {/* Canva Edge Pill Handles */}
          {edgeMidpoints.map((pt, i) => {
             const key = `resize_edge_${i}`;
             const isHover = hoveredHandle === key;
             const isTopBottom = i === 0 || i === 2;
             const ew = isTopBottom ? edgeW : edgeH;
             const eh = isTopBottom ? edgeH : edgeW;
             const cursor = isTopBottom ? 'ns-resize' : 'ew-resize';
             return (
               <g key={key}
                  transform={`rotate(${rot}, ${pt.x}, ${pt.y})`}
                  onPointerEnter={() => setHoveredHandle(key)}
                  onPointerLeave={() => setHoveredHandle(null)}
                  onPointerDown={(e) => handlePointerDown(e, key)}
                  onPointerMove={handlePointerMove} onPointerUp={handlePointerUp}
                  style={{ cursor, pointerEvents: 'all' }}
               >
                 <circle cx={pt.x} cy={pt.y} r={hitR} fill="transparent" />
                 {isHover && <rect x={pt.x - ew/2} y={pt.y - eh/2} width={ew} height={eh} fill={glowColor} rx={eh/2} pointerEvents="none" />}
                 <rect x={pt.x - ew/2} y={pt.y - eh/2} width={ew} height={eh} fill="#ffffff" stroke="rgba(0,0,0,0.15)" strokeWidth={strokeW*1.5} rx={eh/2} pointerEvents="none" />
                 <rect x={pt.x - ew/2} y={pt.y - eh/2} width={ew} height={eh} fill="#ffffff" stroke={brandColor} strokeWidth={strokeW} rx={eh/2} pointerEvents="none" />
               </g>
             );
          })}

          {/* Canva Corner Circle Handles */}
          {vCorners.map((pt, i) => {
             const key = `resize_${i}`;
             const isHover = hoveredHandle === key;
             return (
               <g key={key}
                  onPointerEnter={() => setHoveredHandle(key)}
                  onPointerLeave={() => setHoveredHandle(null)}
                  onPointerDown={(e) => handlePointerDown(e, key)}
                  onPointerMove={handlePointerMove} onPointerUp={handlePointerUp}
                  style={{ cursor: i % 2 === 0 ? 'nwse-resize' : 'nesw-resize', pointerEvents: 'all' }}
               >
                 <circle cx={pt.x} cy={pt.y} r={hitR} fill="transparent" />
                 {isHover && <circle cx={pt.x} cy={pt.y} r={cornerR * 2} fill={glowColor} pointerEvents="none" />}
                 <circle cx={pt.x} cy={pt.y} r={cornerR} fill="#ffffff" stroke="rgba(0,0,0,0.15)" strokeWidth={strokeW * 1.5} pointerEvents="none" />
                 <circle cx={pt.x} cy={pt.y} r={cornerR} fill="#ffffff" stroke={brandColor} strokeWidth={strokeW} pointerEvents="none" />
               </g>
             );
          })}
        </>
      )}

      {mode === 'crop' && vCorners.map((pt, i) => {
         const key = `crop_${i}`;
         const isHover = hoveredHandle === key;
         const cr = 14 * svgScale;
         return (
           <g key={key}
              onPointerEnter={() => setHoveredHandle(key)}
              onPointerLeave={() => setHoveredHandle(null)}
              onPointerDown={(e) => handlePointerDown(e, key)}
              onPointerMove={handlePointerMove} onPointerUp={handlePointerUp}
              style={{ cursor: 'crosshair', pointerEvents: 'all' }}
           >
             <circle cx={pt.x} cy={pt.y} r={hitR} fill="transparent" />
             {isHover && <rect x={pt.x - cr} y={pt.y - cr} width={cr*2} height={cr*2} fill="rgba(255,255,255,0.3)" pointerEvents="none" />}
             <rect x={pt.x - cr} y={pt.y - cr} width={cr*2} height={cr*2} fill="#ffffff" stroke="rgba(0,0,0,0.5)" strokeWidth={strokeW} rx={3 * svgScale} pointerEvents="none" />
           </g>
         );
      })}

      <foreignObject x={toolbarPos.x} y={toolbarPos.y} width={toolbarWidth} height={toolbarHeight} style={{ pointerEvents: 'all', overflow: 'visible' }}>
        <div style={{
          width: '100%', height: '100%',
          background: '#ffffff', borderRadius: `${30 * svgScale}px`,
          display: 'flex', gap: `${16 * svgScale}px`, padding: `0 ${20 * svgScale}px`, 
          boxShadow: `0 ${8 * svgScale}px ${24 * svgScale}px rgba(0,0,0,0.3)`,
          justifyContent: 'center', alignItems: 'center'
        }}>
          {clip.type === 'image' && (
            <button 
              onClick={(e) => { e.stopPropagation(); setMode(mode === 'crop' ? 'normal' : 'crop'); }}
              style={{
                background: mode === 'crop' ? brandColor : 'transparent',
                color: mode === 'crop' ? '#ffffff' : '#000000', border: 'none', cursor: 'pointer', 
                padding: `${10 * svgScale}px ${16 * svgScale}px`, borderRadius: `${20 * svgScale}px`,
                fontSize: `${18 * svgScale}px`, fontWeight: '600', transition: 'all 0.15s ease'
              }}
              onMouseEnter={(e) => { if(mode !== 'crop') e.currentTarget.style.background = '#f3f4f6'; }}
              onMouseLeave={(e) => { if(mode !== 'crop') e.currentTarget.style.background = 'transparent'; }}
            >
              {mode === 'crop' ? 'Done' : 'Crop'}
            </button>
            )}
            <div style={{ width: `${2 * svgScale}px`, height: `${32 * svgScale}px`, background: '#e5e7eb' }} />
            <button 
              onPointerDown={(e) => {
                handlePointerDown(e, 'rotate');
              }}
              style={{ 
                background: 'transparent', color: '#000000', border: 'none', cursor: 'ew-resize', 
                fontSize: `${18 * svgScale}px`, fontWeight: '600', padding: `${10 * svgScale}px ${16 * svgScale}px`, 
                borderRadius: `${20 * svgScale}px`, transition: 'all 0.15s ease' 
              }}
              onMouseEnter={(e) => e.currentTarget.style.background = '#f3f4f6'}
              onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
            >
              Rotate
            </button>
          </div>
        </foreignObject>
      </svg>
    );
}