import re

with open('src/workspaces/viewport/TransformGizmo.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

content = re.sub(
    r"else if \(dragType === 'rotate'\) \{\s*const anchorScreen = applyMatrix\(\{x: init\.ax, y: init\.ay\}\);\s*const startAngle = Math\.atan2\(dragStartRef\.current\.y - anchorScreen\.y, dragStartRef\.current\.x - anchorScreen\.x\);\s*const curAngle = Math\.atan2\(pt\.y - anchorScreen\.y, pt\.x - anchorScreen\.x\);\s*next\.rot = init\.rot \+ \(curAngle - startAngle\) \* 180 / Math\.PI;\s*\}",
    '''else if (dragType === 'rotate') {
         const anchorScreen = applyMatrix({x: init.ax, y: init.ay});
         const startAngle = Math.atan2(dragStartRef.current.y - anchorScreen.y, dragStartRef.current.x - anchorScreen.x);
         const curAngle = Math.atan2(pt.y - anchorScreen.y, pt.x - anchorScreen.x);
         let deltaAngle = curAngle - startAngle;
         while (deltaAngle > Math.PI) deltaAngle -= 2 * Math.PI;
         while (deltaAngle < -Math.PI) deltaAngle += 2 * Math.PI;
         next.rot = init.rot + (deltaAngle * 180 / Math.PI);
      }''',
    content
)

with open('src/workspaces/viewport/TransformGizmo.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
print("Patched TransformGizmo.tsx")
