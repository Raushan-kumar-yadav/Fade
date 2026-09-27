import os
import re

path = 'src/workspaces/viewport/TransformGizmo.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Undo alignment fix in applyMatrix
content = content.replace(
    "compositionToViewport(rx + ax + px + compW / 2, ry + ay + py + compH / 2, compW, compH);",
    "compositionToViewport(rx + ax + px, ry + ay + py, compW, compH);"
)

# Undo alignment fix in inverseApplyMatrix
content = content.replace(
    "let rx = compPt.x - compW / 2 - ax - px; let ry = compPt.y - compH / 2 - ay - py;",
    "let rx = compPt.x - ax - px; let ry = compPt.y - ay - py;"
)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Undid alignment fix")
