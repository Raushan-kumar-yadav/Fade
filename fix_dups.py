import os
import re
path = 'src/workspaces/viewport/TransformGizmo.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

content = re.sub(r'onPointerCancel=\{handlePointerCancel\} onLostPointerCapture=\{handleLostCapture\} onPointerCancel=\{handlePointerCancel\} onLostPointerCapture=\{handleLostCapture\}', r'onPointerCancel={handlePointerCancel} onLostPointerCapture={handleLostCapture}', content)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Removed duplicates")
