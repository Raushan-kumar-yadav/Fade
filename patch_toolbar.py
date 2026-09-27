import os

path = 'src/workspaces/viewport/TransformGizmo.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('const toolbarHeight = 60 * svgScale;', 'const toolbarHeight = 72 * svgScale;')
content = content.replace('const toolbarWidth = 240 * svgScale;', 'const toolbarWidth = 280 * svgScale;')

old_ty = '''    let ty = minY - toolbarHeight - (16 * svgScale);
    if (ty < 0) {
        ty = maxY + (16 * svgScale);
        if (ty + toolbarHeight > 1080) {
            ty = Math.max(0, minY + (16 * svgScale)); // clamp inside if massive
        }
    }'''

new_ty = '''    // Ensure toolbar stays in safe zone
    const SAFE_TOP = 80 * svgScale;
    const SAFE_BOTTOM = 1080 - 80 * svgScale;
    
    let ty = minY - toolbarHeight - (20 * svgScale);
    if (ty < SAFE_TOP) {
        ty = Math.min(SAFE_BOTTOM - toolbarHeight, maxY + (20 * svgScale));
        if (ty >= SAFE_BOTTOM - toolbarHeight - 10) {
            ty = Math.max(SAFE_TOP, minY + (20 * svgScale)); // clamp inside
        }
    }'''

content = content.replace(old_ty, new_ty)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Patched toolbar positioning")

