import re

with open('src/workspaces/viewport/TransformGizmo.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Fix local limits for images/videos
old_limits = '''  } else if (clip.type === 'image' || clip.type === 'video') {
    // FADE's C++ renderer draws images at their exact native pixel resolution (1:1).
    // It does NOT apply any automatic object-fit scaling.
    imgW = baseWidth;
    imgH = baseHeight;
    localMinX = 0;
    localMinY = 0;
    localMaxX = imgW;
    localMaxY = imgH;
  }'''

new_limits = '''  } else if (clip.type === 'image' || clip.type === 'video') {
    // FADE's C++ renderer draws images at their exact native pixel resolution (1:1).
    // CRITICAL: The local mesh in FADE is centered at 0,0 (from -0.5 to +0.5).
    // Therefore, the local bounding box goes from -width/2 to +width/2.
    imgW = baseWidth;
    imgH = baseHeight;
    localMinX = -imgW / 2;
    localMinY = -imgH / 2;
    localMaxX = imgW / 2;
    localMaxY = imgH / 2;
  }'''
content = content.replace(old_limits, new_limits)

# 2. Fix applyMatrix to add 1920/2 and 1080/2
# Because FADE's composition origin (0,0) is the CENTER of the screen, not top-left.
old_apply = '''    const applyMatrix = (lPt: {x: number, y: number}) => {
      let nx = lPt.x - ax; let ny = lPt.y - ay;
      nx *= sx; ny *= sy;
      const rad = rot * Math.PI / 180;
      const cosA = Math.cos(rad); const sinA = Math.sin(rad);
      let rx = nx * cosA - ny * sinA;
      let ry = nx * sinA + ny * cosA;
      return compositionToViewport(rx + ax + px, ry + ay + py, compW, compH);
    };'''

new_apply = '''    const applyMatrix = (lPt: {x: number, y: number}) => {
      let nx = lPt.x - ax; let ny = lPt.y - ay;
      nx *= sx; ny *= sy;
      const rad = rot * Math.PI / 180;
      const cosA = Math.cos(rad); const sinA = Math.sin(rad);
      let rx = nx * cosA - ny * sinA;
      let ry = nx * sinA + ny * cosA;
      // FADE's coordinate origin (0,0) is at the CENTER of the 1920x1080 composition.
      const compOriginX = compW / 2;
      const compOriginY = compH / 2;
      return compositionToViewport(rx + ax + px + compOriginX, ry + ay + py + compOriginY, compW, compH);
    };'''
content = content.replace(old_apply, new_apply)

# 3. Fix invertMatrix to subtract compOrigin
old_invert = '''    const invertMatrix = (compPt: {x: number, y: number}) => {
      let rx = compPt.x - ax - px; let ry = compPt.y - ay - py;
      const rad = -rot * Math.PI / 180;
      const cosA = Math.cos(rad); const sinA = Math.sin(rad);
      let nx = rx * cosA - ry * sinA;
      let ny = rx * sinA + ry * cosA;
      nx /= (sx === 0 ? 0.001 : sx); ny /= (sy === 0 ? 0.001 : sy);
      return { x: nx + ax, y: ny + ay };
    };'''

new_invert = '''    const invertMatrix = (compPt: {x: number, y: number}) => {
      const compOriginX = compW / 2;
      const compOriginY = compH / 2;
      let rx = compPt.x - compOriginX - ax - px; 
      let ry = compPt.y - compOriginY - ay - py;
      const rad = -rot * Math.PI / 180;
      const cosA = Math.cos(rad); const sinA = Math.sin(rad);
      let nx = rx * cosA - ry * sinA;
      let ny = rx * sinA + ry * cosA;
      nx /= (sx === 0 ? 0.001 : sx); ny /= (sy === 0 ? 0.001 : sy);
      return { x: nx + ax, y: ny + ay };
    };'''
content = content.replace(old_invert, new_invert)

# 4. Fix calcWorld in handlePointerMove
old_calcworld = '''         const calcWorld = (lPt: {x: number, y: number}, state: any) => {
            let nx = lPt.x - state.ax; let ny = lPt.y - state.ay;
            nx *= state.sx; ny *= state.sy;
            const r = state.rot * Math.PI / 180;
            const cx = Math.cos(r); const sx = Math.sin(r);
            return {
               x: nx * cx - ny * sx + state.ax + state.px,
               y: nx * sx + ny * cx + state.ay + state.py
            };
         };'''

new_calcworld = '''         const calcWorld = (lPt: {x: number, y: number}, state: any) => {
            let nx = lPt.x - state.ax; let ny = lPt.y - state.ay;
            nx *= state.sx; ny *= state.sy;
            const r = state.rot * Math.PI / 180;
            const cx = Math.cos(r); const sine = Math.sin(r);
            return {
               x: nx * cx - ny * sine + state.ax + state.px,
               y: nx * sine + ny * cx + state.ay + state.py
            };
         };'''
# (Fixed a tiny bug in calcWorld where Math.sin was assigned to sx shadowing state.sx)
content = content.replace(old_calcworld, new_calcworld)


with open('src/workspaces/viewport/TransformGizmo.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
print("Applied Origin Patch.")
