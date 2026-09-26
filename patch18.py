import re

with open('src/workspaces/viewport/TransformGizmo.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Add pivot marker
marker = '''          <>
            <polygon points={polygonPoints} fill="transparent" stroke={brandColor} strokeWidth={strokeW} pointerEvents="none" />
            
            {/* Pivot Marker */}
            <circle cx={compW/2 + px + ax} cy={compH/2 + py + ay} r={4 * svgScale} fill="#0f0" pointerEvents="none" />
            <circle cx={compW/2 + px + ax} cy={compH/2 + py + ay} r={6 * svgScale} fill="transparent" stroke="#0f0" strokeWidth={2 * svgScale} pointerEvents="none" />'''

content = content.replace(
    '          <>\n            <polygon points={polygonPoints} fill="transparent" stroke={brandColor} strokeWidth={strokeW} pointerEvents="none" />',
    marker
)

with open('src/workspaces/viewport/TransformGizmo.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
print("Added pivot marker")
