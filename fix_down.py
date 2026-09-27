import os
path = 'src/workspaces/viewport/TransformGizmo.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_down = """  const handlePointerDown = (e: React.PointerEvent, type: string) => {
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
       localMinX, localMaxX, localMinY, localMaxY, imgW, imgH,
       startMouseAngle
    } as any;
    
    dragStartRef.current = startCoord;
    setDragType(type);
    setIsDragging(true);
    (e.target as Element).setPointerCapture(e.pointerId);
  };"""

new_down = """  const handlePointerDown = (e: React.PointerEvent, type: string) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    const startCoord = designCoord(e);
    let startMouseAngle = 0;
    if (type === 'rotate') {
       console.log('[ROTATE_START]');
       const objCenter = applyMatrix({x: 0, y: 0});
       startMouseAngle = Math.atan2(startCoord.y - objCenter.y, startCoord.x - objCenter.x);
    }
    
    initialTransformRef.current = { 
       px, py, sx, sy, rot, ax, ay, 
       cropL, cropR, cropT, cropB, 
       localMinX, localMaxX, localMinY, localMaxY, imgW, imgH,
       startMouseAngle
    } as any;
    
    dragStartRef.current = startCoord;
    setDragType(type);
    setIsDragging(true);
    isDraggingRef.current = true;
    (e.target as Element).setPointerCapture(e.pointerId);
  };"""

if old_down in content:
    content = content.replace(old_down, new_down)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Replaced handlePointerDown successfully")
else:
    print("Exact old_down string not found!")

