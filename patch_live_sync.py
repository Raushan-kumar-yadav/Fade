import sys
with open('src/workspaces/viewport/TransformOverlay.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

search = """    if (dragType === 'move') {
      const scale = Math.min(1920 / compW, 1080 / compH);
      next.px = init.px + dx / scale;
      next.py = init.py + dy / scale;
    } else if (dragType === 'rotate') {
       const cx = posViewport.x;
       const cy = posViewport.y;
       const startAngle = Math.atan2(dragStartRef.current.y - cy, dragStartRef.current.x - cx);
       const curAngle = Math.atan2(pt.y - cy, pt.x - cx);
       let dRot = (curAngle - startAngle) * 180 / Math.PI;
       next.rot = init.rot + dRot;
    } else if (dragType?.startsWith('resize')) {
       // Distance-based uniform scaling
       const distStart = Math.hypot(dragStartRef.current.x - posViewport.x, dragStartRef.current.y - posViewport.y);
       const distCur = Math.hypot(pt.x - posViewport.x, pt.y - posViewport.y);
       if (distStart > 0) {
           const factor = distCur / distStart;
           next.sx = init.sx * factor;
           next.sy = init.sy * factor;
       }
    }
    
    setLocalTransform(next);"""

replacement = """    if (dragType === 'move') {
      const scale = Math.min(1920 / compW, 1080 / compH);
      next.px = init.px + dx / scale;
      next.py = init.py + dy / scale;
    } else if (dragType === 'rotate') {
       const cx = posViewport.x;
       const cy = posViewport.y;
       const startAngle = Math.atan2(dragStartRef.current.y - cy, dragStartRef.current.x - cx);
       const curAngle = Math.atan2(pt.y - cy, pt.x - cx);
       let dRot = (curAngle - startAngle) * 180 / Math.PI;
       next.rot = init.rot + dRot;
    } else if (dragType?.startsWith('resize')) {
       // Distance-based uniform scaling
       const distStart = Math.hypot(dragStartRef.current.x - posViewport.x, dragStartRef.current.y - posViewport.y);
       const distCur = Math.hypot(pt.x - posViewport.x, pt.y - posViewport.y);
       if (distStart > 0) {
           const factor = distCur / distStart;
           next.sx = init.sx * factor;
           next.sy = init.sy * factor;
       }
    }
    
    setLocalTransform(next);
    
    // Live update to backend so C++ renderer and Inspector show the drag in real-time!
    // We fire-and-forget to avoid blocking the React render thread.
    const port = (window as any).__FADE_PORT__ || 8000;
    fetch(`http://127.0.0.1:${port}/clips/set-param`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clip_id: selected.clipId, param: 'pos_x', value: next.px })
    }).catch(()=>{});
    fetch(`http://127.0.0.1:${port}/clips/set-param`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clip_id: selected.clipId, param: 'pos_y', value: next.py })
    }).catch(()=>{});
    fetch(`http://127.0.0.1:${port}/clips/set-param`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clip_id: selected.clipId, param: 'scale_x', value: next.sx })
    }).catch(()=>{});
    fetch(`http://127.0.0.1:${port}/clips/set-param`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clip_id: selected.clipId, param: 'scale_y', value: next.sy })
    }).catch(()=>{});
    fetch(`http://127.0.0.1:${port}/clips/set-param`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clip_id: selected.clipId, param: 'rotation', value: next.rot })
    }).catch(()=>{});"""

content = content.replace(search.replace('\r\n','\n'), replacement.replace('\r\n','\n'))

with open('src/workspaces/viewport/TransformOverlay.tsx', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
print('Updated TransformOverlay.tsx live sync!')
