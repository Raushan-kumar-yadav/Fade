import re

with open('src/workspaces/viewport/TransformGizmo.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# I added an unclosed <> in patch19.py. Let's fix it.
content = content.replace(
    '          <>\n            <polygon points={polygonPoints}',
    '            <polygon points={polygonPoints}'
)

with open('src/workspaces/viewport/TransformGizmo.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
print("Fixed JSX error")
