import os
import re

path = 'src/workspaces/viewport/TransformGizmo.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

content = re.sub(r'<button[^>]*?\s*onClick=\{[^}]*?rot \+ 90.*?</button>', '', content, flags=re.DOTALL)

old_pd = '''  const handlePointerDown = (e: React.PointerEvent, type: string) => {
    e.stopPropagation();
    initialTransformRef.current = { px, py, sx, sy, rot, ax, ay, cropL, cropR, cropT, cropB, localMinX, localMaxX, localMinY, localMaxY, imgW, imgH };
    dragStartRef.current = designCoord(e);
    setDragType(type);
    setIsDragging(true);
    (e.target as Element).setPointerCapture(e.pointerId);
  };'''

new_pd = '''  const handlePointerDown = (e: React.PointerEvent, type: string) => {
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
  };'''

content = content.replace(old_pd, new_pd)


old_pm_rot = '''    else if (dragType === 'rotate') {
         const anchorScreen = applyMatrix({x: init.ax, y: init.ay});
         const startAngle = Math.atan2(dragStartRef.current.y - anchorScreen.y, dragStartRef.current.x - anchorScreen.x);
         const curAngle = Math.atan2(pt.y - anchorScreen.y, pt.x - anchorScreen.x);
         let deltaAngle = curAngle - startAngle;
         while (deltaAngle > Math.PI) deltaAngle -= 2 * Math.PI;
         while (deltaAngle < -Math.PI) deltaAngle += 2 * Math.PI;
         next.rot = init.rot + (deltaAngle * 180 / Math.PI);
      } '''

new_pm_rot = '''    else if (dragType === 'rotate') {
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
      } '''

content = content.replace(old_pm_rot, new_pm_rot)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Patched TransformGizmo.tsx")
