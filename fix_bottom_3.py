import os
path = 'src/workspaces/viewport/TransformGizmo.tsx'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.read().split('\n')

for i in range(len(lines)-1, -1, -1):
    if "{mode === 'crop' ? 'Done' : 'Crop'}" in lines[i]:
        crop_end_idx = i + 3
        break

new_bottom = """            <div style={{ width: `${2 * svgScale}px`, height: `${32 * svgScale}px`, background: '#e5e7eb' }} />
            <button 
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
            </button>
          </div>
        </foreignObject>
      </svg>
    );
}"""

lines = lines[:crop_end_idx] + new_bottom.split('\n')

with open(path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print("Fixed bottom of file properly 2")
