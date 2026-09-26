import sys

with open('src/workspaces/viewport/ViewportWidget.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

import_stmt = "import TransformOverlay from './TransformOverlay';\n"
if import_stmt not in content:
    content = content.replace("import BrushOverlay from './BrushOverlay';", import_stmt + "import BrushOverlay from './BrushOverlay';")

target = """          {/* Brush / Eraser overlay */}
          {(activeTool === 'brush' || activeTool === 'eraser') && (
            <BrushOverlay"""

replacement = """          {/* Direct Manipulation overlay */}
          {activeTool === 'pointer' && (
            <TransformOverlay
              width={1920}
              height={1080}
              currentFrame={currentFrame}
              activeTool={activeTool}
              pan={vpPan}
              zoom={vpZoom}
            />
          )}
          
          {/* Brush / Eraser overlay */}
          {(activeTool === 'brush' || activeTool === 'eraser') && (
            <BrushOverlay"""

content = content.replace('\r\n', '\n')
target = target.replace('\r\n', '\n')
replacement = replacement.replace('\r\n', '\n')

if target in content:
    content = content.replace(target, replacement)
    with open('src/workspaces/viewport/ViewportWidget.tsx', 'w', encoding='utf-8', newline='') as f:
        f.write(content)
    print('Replaced!')
else:
    print('Not found!')
