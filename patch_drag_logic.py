import os
import re

path = 'src/workspaces/viewport/TransformGizmo.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. We need to introduce endDrag and replace handlePointerUp.
# Let's find handlePointerUp.
up_regex = r"const handlePointerUp = \(e: React\.PointerEvent\) => \{.*?\n    \};\n"
m = re.search(up_regex, content, flags=re.DOTALL)
if m:
    old_up = m.group(0)
    
    new_handlers = """  const isDraggingRef = useRef(false);

  const endDrag = (reason: string, target?: EventTarget | Element, pointerId?: number) => {
    if (!isDraggingRef.current || !initialTransformRef.current) return;
    if (dragType === 'rotate') console.log(`[ROTATE_END] with reason: ${reason}`);
    
    setIsDragging(false);
    isDraggingRef.current = false;
    setDragType(null);
    
    if (target && pointerId !== undefined && 'releasePointerCapture' in target) {
      try { (target as Element).releasePointerCapture(pointerId); } catch(err) {}
    }

    const init = initialTransformRef.current;
    initialTransformRef.current = null;
    
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
    }
    
    fetch(`http://127.0.0.1:${(window as any).__FADE_PORT__ || 8000}/clips/transform-batch`, {
       method: 'POST', headers: { 'Content-Type': 'application/json' },
       body: JSON.stringify({ clip_id: selected.clipId, before: init, after: finalParams })
    }).catch(() => {});
  };

  const handlePointerUp = (e: React.PointerEvent) => endDrag('pointerup', e.target, e.pointerId);
  const handlePointerCancel = (e: React.PointerEvent) => endDrag('pointercancel', e.target, e.pointerId);
  const handleLostCapture = (e: React.PointerEvent) => endDrag('lostcapture', e.target, e.pointerId);

  useEffect(() => {
    const onBlur = () => endDrag('blur');
    window.addEventListener('blur', onBlur);
    return () => window.removeEventListener('blur', onBlur);
  }, []);

  useEffect(() => {
    endDrag('selection change');
  }, [selected.clipId]);
"""
    content = content.replace(old_up, new_handlers)
else:
    print("Could not find handlePointerUp")


# 2. Update handlePointerDown
down_regex = r"const handlePointerDown = \(e: React\.PointerEvent, type: string\) => \{.*?setIsDragging\(true\);\s*\(e\.target as Element\)\.setPointerCapture\(e\.pointerId\);\s*\};"
m = re.search(down_regex, content, flags=re.DOTALL)
if m:
    old_down = m.group(0)
    new_down = """const handlePointerDown = (e: React.PointerEvent, type: string) => {
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
    content = content.replace(old_down, new_down)
else:
    print("Could not find handlePointerDown")


# 3. Update handlePointerMove
move_regex = r"const handlePointerMove = \(e: React\.PointerEvent\) => \{\s*if \(!isDragging \|\| !initialTransformRef\.current\) return;\s*const pt = designCoord\(e\);\s*const init = initialTransformRef\.current;\s*let next = \{ \.\.\.init \};"
m = re.search(move_regex, content, flags=re.DOTALL)
if m:
    old_move = m.group(0)
    new_move = """const handlePointerMove = (e: React.PointerEvent) => {
    if (!isDraggingRef.current || !initialTransformRef.current) return;
    
    if ((e.buttons & 1) === 0) {
        endDrag('buttons-released', e.target, e.pointerId);
        return;
    }

    if (dragType === 'rotate') {
        console.log('[ROTATE_MOVE]');
    }

    const pt = designCoord(e);
    const init = initialTransformRef.current;
    let next = { ...init };"""
    content = content.replace(old_move, new_move)
else:
    print("Could not find handlePointerMove start")

# 4. Attach handlePointerCancel and handleLostCapture anywhere onPointerUp is used.
content = content.replace("onPointerUp={handlePointerUp}", "onPointerUp={handlePointerUp} onPointerCancel={handlePointerCancel} onLostPointerCapture={handleLostCapture}")

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Patched pointer drag events")
