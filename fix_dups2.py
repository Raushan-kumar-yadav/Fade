import os
import re
path = 'src/workspaces/viewport/TransformGizmo.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

content = re.sub(r'(onPointerCancel=\{handlePointerCancel\}\s*)+', 'onPointerCancel={handlePointerCancel} ', content)
content = re.sub(r'(onLostPointerCapture=\{handleLostCapture\}\s*)+', 'onLostPointerCapture={handleLostCapture} ', content)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Removed duplicates regex")
