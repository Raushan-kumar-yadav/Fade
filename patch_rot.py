import os
import re

path = 'src/workspaces/viewport/TransformGizmo.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Remove the 90 degree button
btn_regex = r"<span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>.*?90&deg;.*?</span>"
content = re.sub(btn_regex, "", content, flags=re.DOTALL)
content = re.sub(r"<button[^>]*onClick=\{\(e\) => \{\s*e\.stopPropagation\(\);\s*inspectorApi\.setParam\(selected\.clipId, 'rotation', rot \+ 90\);.*?</button>", "", content, flags=re.DOTALL)

# Let's just find the whole Toolbar button for rotation and nuke it.
# It has ot + 90 in it.
def remove_rot_button(text):
    lines = text.split('\n')
    out = []
    skip = 0
    for i, line in enumerate(lines):
        if skip > 0:
            skip -= 1
            continue
        if "inspectorApi.setParam(selected.clipId, 'rotation', rot + 90);" in line:
            # We need to drop backwards to the <button> tag
            # Since we iterate forward, this is hard. Let's use regex on the whole string.
            pass
    return text

# The button HTML in TransformGizmo.tsx looks like:
# <button
#   title="Rotate 90°"
#   onClick={(e) => {
#     ... rot + 90 ...
#   }}
# ...>
# </button>
content = re.sub(r"<button[^>]*?\s*onClick=\{[^}]*?rot \+ 90.*?</button>", "", content, flags=re.DOTALL)


# 2. Fix Pointer Down for rotate
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


# 3. Fix Pointer Move for rotate
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
         // Goal: image rotates around its own visible center.
         const objectCenter = applyMatrix({x: 0, y: 0});
         const currentMouseAngle = Math.atan2(pt.y - objectCenter.y, pt.x - objectCenter.x);
         let deltaAngle = currentMouseAngle - (init as any).startMouseAngle;
         
         if (deltaAngle > Math.PI) deltaAngle -= 2 * Math.PI;
         if (deltaAngle < -Math.PI) deltaAngle += 2 * Math.PI;
         
         next.rot = init.rot + (deltaAngle * 180 / Math.PI);
         
         // Update only rotation. Do not modify px, py, sx, sy, ax, ay
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
