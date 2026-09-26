import re

with open('src/workspaces/viewport/TransformGizmo.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Add diagnostic overlay
diagnostic = '''      <svg 
        ref={svgRef} 
        style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 50 }} 
        viewBox="0 0 1920 1080" preserveAspectRatio="xMidYMid meet"
      >
        {/* Diagnostic Output */}
        <text x="20" y="30" fill="red" fontSize="20" fontFamily="monospace" style={{textShadow: "1px 1px 2px black"}}>
          DIAGNOSTIC:
        </text>
        <text x="20" y="55" fill="red" fontSize="16" fontFamily="monospace" style={{textShadow: "1px 1px 2px black"}}>
          FADE Origin: Center (960, 540)
        </text>
        <text x="20" y="80" fill="red" fontSize="16" fontFamily="monospace" style={{textShadow: "1px 1px 2px black"}}>
          Image BaseW/H: {imgW}x{imgH}
        </text>
        <text x="20" y="105" fill="red" fontSize="16" fontFamily="monospace" style={{textShadow: "1px 1px 2px black"}}>
          Gizmo Left (World): { ((vCorners[0].x + vCorners[3].x)/2).toFixed(1) }
        </text>
        <text x="20" y="130" fill="red" fontSize="16" fontFamily="monospace" style={{textShadow: "1px 1px 2px black"}}>
          Gizmo Center (World): { ((vCorners[0].x + vCorners[2].x)/2).toFixed(1) }
        </text>
        
        {/* RED BOX representing mathematical Actual Image Bounds */}
        <polygon points={polygonPoints} fill="transparent" stroke="red" strokeWidth={strokeW * 3} strokeDasharray="10, 5" pointerEvents="none" />'''

content = content.replace('''      <svg 
        ref={svgRef} 
        style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 50 }} 
        viewBox="0 0 1920 1080" preserveAspectRatio="xMidYMid meet"
      >''', diagnostic)

with open('src/workspaces/viewport/TransformGizmo.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
print("Applied Diagnostic Patch.")
