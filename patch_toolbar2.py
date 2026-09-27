import os

path = 'src/workspaces/viewport/TransformGizmo.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('fontSize: ${18 * svgScale}px', 'fontSize: ${22 * svgScale}px')
content = content.replace('padding: ${10 * svgScale}px px', 'padding: ${14 * svgScale}px px')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Patched toolbar text size")

