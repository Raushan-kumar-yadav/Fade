import os

with open('src/workspaces/viewport/BrushOverlay.tsx', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('fetch(http://localhost:8000/clips/pen//points', 'fetch(http://localhost:8000/clips/pen//points')
text = text.replace('fetch(http://localhost:8000', 'fetch(http://localhost:8000')

with open('src/workspaces/viewport/BrushOverlay.tsx', 'w', encoding='utf-8') as f:
    f.write(text)
