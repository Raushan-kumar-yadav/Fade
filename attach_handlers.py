import os
path = 'src/workspaces/viewport/TransformGizmo.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace any onPointerUp with the full suite of cancellation handlers
# Note: only for elements that were calling handlePointerUp
content = content.replace(
    "onPointerUp={handlePointerUp}",
    "onPointerUp={handlePointerUp} onPointerCancel={handlePointerCancel} onLostPointerCapture={handleLostCapture}"
)

# And one for SVG:
# Wait, the SVG has:
# onPointerDown={handleSvgPointerDown}
# onPointerMove={handlePointerMove}
# onPointerUp={handlePointerUp}
# It will be replaced by the above if it just says onPointerUp={handlePointerUp}.

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Added cancel handlers to markup")
