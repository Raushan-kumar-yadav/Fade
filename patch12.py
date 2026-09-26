import re

with open('src/workspaces/viewport/TransformGizmo.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

old_code = '''      else if (dragType === 'rotate') {
         const anchorScreen = applyMatrix({x: init.ax, y: init.ay});
         const startAngle = Math.atan2(dragStartRef.current.y - anchorScreen.y, dragStartRef.current.x - anchorScreen.x);
         const curAngle = Math.atan2(pt.y - anchorScreen.y, pt.x - anchorScreen.x);
         next.rot = init.rot + (curAngle - startAngle) * 180 / Math.PI;
      }'''

new_code = '''      else if (dragType === 'rotate') {
         const anchorScreen = applyMatrix({x: init.ax, y: init.ay});
         const startAngle = Math.atan2(dragStartRef.current.y - anchorScreen.y, dragStartRef.current.x - anchorScreen.x);
         const curAngle = Math.atan2(pt.y - anchorScreen.y, pt.x - anchorScreen.x);
         let deltaAngle = curAngle - startAngle;
         // Normalize delta to avoid 360-degree wrap-around jumps
         while (deltaAngle > Math.PI) deltaAngle -= 2 * Math.PI;
         while (deltaAngle < -Math.PI) deltaAngle += 2 * Math.PI;
         
         // FADE uses continuous rotation, so we just add the delta smoothly
         next.rot = init.rot + (deltaAngle * 180 / Math.PI);
      }'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open('src/workspaces/viewport/TransformGizmo.tsx', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Patched TransformGizmo.tsx wrap-around")
else:
    print("Could not find block in TransformGizmo.tsx")
