import os
path = 'src/workspaces/viewport/TransformGizmo.tsx'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.read().split('\n')

for i in range(len(lines)-1, -1, -1):
    if "Rotate" in lines[i] and "button" in lines[i+1]:
        # remove the bad inserted block
        del lines[i-11:i+2]
        break

insert_idx = -1
for i, line in enumerate(lines):
    if "background: '#e5e7eb'" in line:
        insert_idx = i + 1
        break

if insert_idx != -1:
    button_str = """          <button 
            onPointerDown={(e) => {
              handlePointerDown(e, 'rotate');
            }}
            style={{ 
              background: 'transparent', color: '#000000', border: 'none', cursor: 'ew-resize', 
              fontSize: `${18 * svgScale}px`, fontWeight: '600', padding: `${10 * svgScale}px ${16 * svgScale}px`, 
              borderRadius: `${20 * svgScale}px`, transition: 'all 0.15s ease' 
            }}
            onMouseEnter={(e) => e.currentTarget.style.background = '#f3f4f6'}
            onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
          >
            Rotate
          </button>"""

    lines.insert(insert_idx, button_str)
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print("Fixed Rotate button")
else:
    print("Could not find insertion point")
