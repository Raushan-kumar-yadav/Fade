import os

with open('src/workspaces/viewport/BrushOverlay.tsx', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace("fade:masks-changed", "fade:tracks-changed")

with open('src/workspaces/viewport/BrushOverlay.tsx', 'w', encoding='utf-8') as f:
    f.write(text)
