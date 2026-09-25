import os

with open('src/workspaces/viewport/ViewportWidget.tsx', 'r', encoding='utf-8') as f:
    text = f.read()

if "import BrushOverlay" not in text:
    text = text.replace("import OverlayCanvas from './OverlayCanvas';", "import OverlayCanvas from './OverlayCanvas';\nimport BrushOverlay from './BrushOverlay';")

target = '''          {/* Shape draw overlay */}
          {activeTool !== 'shape:path' && activeTool.startsWith('shape:') && (
            <OverlayCanvas
              mode="shape"
              width={1920}
              height={1080}
            />
          )}'''

replacement = '''          {/* Shape draw overlay */}
          {activeTool !== 'shape:path' && activeTool.startsWith('shape:') && (
            <OverlayCanvas
              mode="shape"
              width={1920}
              height={1080}
            />
          )}
          
          {/* Brush / Eraser overlay */}
          {(activeTool === 'brush' || activeTool === 'eraser') && (
            <BrushOverlay
              mode={activeTool as 'brush' | 'eraser'}
              width={1920}
              height={1080}
            />
          )}'''

if "<BrushOverlay" not in text:
    text = text.replace(target, replacement)

with open('src/workspaces/viewport/ViewportWidget.tsx', 'w', encoding='utf-8') as f:
    f.write(text)
