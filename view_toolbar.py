import os
path = 'src/workspaces/viewport/TransformGizmo.tsx'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.read().split('\n')
for i, line in enumerate(lines):
    if "foreignObject" in line:
        for j in range(max(0, i-5), min(len(lines), i+20)):
            print(f"{j}: {lines[j]}")
