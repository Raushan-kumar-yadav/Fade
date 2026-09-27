import os
import re

path = 'src/workspaces/viewport/TransformGizmo.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_am = '''    const applyMatrix = (pt: {x: number, y: number}) => {
      let nx = pt.x - ax; let ny = pt.y - ay;
      nx *= sx; ny *= sy;
      const rad = rot * Math.PI / 180;
      const cosA = Math.cos(rad); const sinA = Math.sin(rad);
      const rx = nx * cosA - ny * sinA;
      const ry = nx * sinA + ny * cosA;
      return compositionToViewport(rx + ax + px, ry + ay + py, compW, compH);
    };'''

new_am = '''    const applyMatrix = (pt: {x: number, y: number}) => {
      let nx = pt.x - ax; let ny = pt.y - ay;
      nx *= sx; ny *= sy;
      const rad = rot * Math.PI / 180;
      const cosA = Math.cos(rad); const sinA = Math.sin(rad);
      const rx = nx * cosA - ny * sinA;
      const ry = nx * sinA + ny * cosA;
      // C++ renderer considers (0,0) as the center of the composition
      return compositionToViewport(rx + ax + px + compW / 2, ry + ay + py + compH / 2, compW, compH);
    };'''

old_iam = '''    const inverseApplyMatrix = (screenPt: {x: number, y: number}) => {
      const compPt = viewportToComposition(screenPt.x, screenPt.y, compW, compH, false)!;
      let rx = compPt.x - ax - px; let ry = compPt.y - ay - py;
      const rad = -rot * Math.PI / 180;
      const cosA = Math.cos(rad); const sinA = Math.sin(rad);
      let nx = rx * cosA - ry * sinA;
      let ny = rx * sinA + ry * cosA;
      nx /= (sx === 0 ? 0.001 : sx); ny /= (sy === 0 ? 0.001 : sy);
      return { x: nx + ax, y: ny + ay };
    };'''

new_iam = '''    const inverseApplyMatrix = (screenPt: {x: number, y: number}) => {
      const compPt = viewportToComposition(screenPt.x, screenPt.y, compW, compH, false)!;
      let rx = compPt.x - compW / 2 - ax - px; let ry = compPt.y - compH / 2 - ay - py;
      const rad = -rot * Math.PI / 180;
      const cosA = Math.cos(rad); const sinA = Math.sin(rad);
      let nx = rx * cosA - ry * sinA;
      let ny = rx * sinA + ry * cosA;
      nx /= (sx === 0 ? 0.001 : sx); ny /= (sy === 0 ? 0.001 : sy);
      return { x: nx + ax, y: ny + ay };
    };'''

content = content.replace(old_am, new_am).replace(old_iam, new_iam)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Fixed Gizmo Matrix Offset")
