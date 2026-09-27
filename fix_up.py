import os
path = 'src/workspaces/viewport/TransformGizmo.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_up = """  const handlePointerUp = (e: React.PointerEvent) => {
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
  };"""

new_up = """  const isDraggingRef = useRef(false);

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
      
      init.cropLeft = init.cropL; init.cropRight = init.cropR;
      init.cropTop = init.cropT; init.cropBottom = init.cropB;
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

if old_up in content:
    content = content.replace(old_up, new_up)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Replaced handlePointerUp successfully")
else:
    print("Exact old_up string not found!")

