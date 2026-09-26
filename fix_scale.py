import sys
with open('src/workspaces/viewport/TransformOverlay.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

search = """    if (dragType === 'move') {
      const scaleX = 1920 / compW;
      const scaleY = 1080 / compH;
      next.px = init.px + dx / scaleX;
      next.py = init.py + dy / scaleY;"""

replacement = """    if (dragType === 'move') {
      const scale = Math.min(1920 / compW, 1080 / compH);
      next.px = init.px + dx / scale;
      next.py = init.py + dy / scale;"""

content = content.replace(search.replace('\r\n', '\n'), replacement.replace('\r\n', '\n'))
with open('src/workspaces/viewport/TransformOverlay.tsx', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
print('Fixed scale!')
