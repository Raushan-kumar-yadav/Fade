import re

with open('src/workspaces/viewport/TransformGizmo.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Add a diagnostic overlay
new_overlay = '''        <foreignObject x={toolbarPos.x} y={toolbarPos.y} width={toolbarWidth} height={toolbarHeight} style={{ pointerEvents: 'all', overflow: 'visible' }}>'''

diagnostic = '''        {/* Rotation Diagnostic Overlay */}
        <foreignObject x={10} y={10} width={400} height={200} style={{ pointerEvents: 'none' }}>
          <div style={{ background: 'rgba(0,0,0,0.8)', color: '#0f0', padding: '10px', fontFamily: 'monospace', fontSize: '12px', borderRadius: '8px' }}>
            <div>Object center (local): 0, 0</div>
            <div>Object pivot (global): {(compW/2 + ax + px).toFixed(1)}, {(compH/2 + ay + py).toFixed(1)}</div>
            <div>Current rotation: {rot.toFixed(2)}°</div>
            <div>Position: {px.toFixed(1)}, {py.toFixed(1)}</div>
            <div>Anchor: {ax.toFixed(1)}, {ay.toFixed(1)}</div>
          </div>
        </foreignObject>
        
        <foreignObject x={toolbarPos.x} y={toolbarPos.y} width={toolbarWidth} height={toolbarHeight} style={{ pointerEvents: 'all', overflow: 'visible' }}>'''

content = content.replace(new_overlay, diagnostic)

with open('src/workspaces/viewport/TransformGizmo.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
print("Added diagnostic overlay")
