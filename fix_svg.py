import sys
with open('src/workspaces/viewport/TransformOverlay.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

search = "<g transform={`translate(${posViewport.x}, ${posViewport.y}) rotate(${t.rot}) scale(${t.sx}, ${t.sy})`}>"
replacement = "<g transform={`translate(${posViewport.x}, ${posViewport.y}) translate(${t.ax}, ${t.ay}) rotate(${t.rot}) scale(${t.sx}, ${t.sy}) translate(${-t.ax}, ${-t.ay})`}>"

content = content.replace(search, replacement)
with open('src/workspaces/viewport/TransformOverlay.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed SVG transform!')
