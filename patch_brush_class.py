import os

with open('src/workspaces/viewport/BrushOverlay.tsx', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('className="vw-canvas__overlay"', '')

with open('src/workspaces/viewport/BrushOverlay.tsx', 'w', encoding='utf-8') as f:
    f.write(text)
