import os

path = 'backend/animation/transform.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_block = '''    def applyToCanvas(self, canvas) -> None:
        \"\"\"Apply transform directly to a Skia canvas.\"\"\"
        import skia
        tx, ty = self.position.get()
        sx, sy = self.scale.get()
        deg = self.rotation.get()
        ax, ay = self.anchor.get()

        # CRITICAL FIX: Rotate around the center by default!
        # FADE's Python renderer draws into 1920x1080.
        cx = 1920 * 0.5 + ax
        cy = 1080 * 0.5 + ay
        canvas.translate(tx + cx, ty + cy)
        canvas.rotate(deg)
        canvas.scale(sx, sy)
        canvas.translate(-cx, -cy)
        canvas.translate(-ax, -ay)'''

new_block = '''    def applyToCanvas(self, canvas) -> None:
        \"\"\"Apply transform directly to a Skia canvas.\"\"\"
        import skia
        tx, ty = self.position.get()
        sx, sy = self.scale.get()
        deg = self.rotation.get()
        ax, ay = self.anchor.get()

        canvas.translate(tx, ty)
        canvas.translate(ax, ay)
        canvas.rotate(deg)
        canvas.scale(sx, sy)
        canvas.translate(-ax, -ay)'''

if old_block in content:
    content = content.replace(old_block, new_block)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Patched transform.py")
else:
    print("Could not find block in transform.py")
