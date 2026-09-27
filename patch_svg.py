import os
path = 'src/workspaces/viewport/TransformGizmo.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_svg = """  const handleSvgPointerDown = (e: React.PointerEvent) => {
    const pt = designCoord(e);"""

new_svg = """  const handleSvgPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    const pt = designCoord(e);"""

content = content.replace(old_svg, new_svg)

old_svg2 = """         setDragType('move');
         setIsDragging(true);
         (e.target as Element).setPointerCapture(e.pointerId);"""

new_svg2 = """         setDragType('move');
         setIsDragging(true);
         isDraggingRef.current = true;
         (e.target as Element).setPointerCapture(e.pointerId);"""

content = content.replace(old_svg2, new_svg2)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Patched handleSvgPointerDown")
