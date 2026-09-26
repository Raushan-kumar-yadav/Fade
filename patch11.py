import re

with open('backend/animation/transform.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_code = '''        canvas.translate(tx + ax, ty + ay)
        canvas.rotate(deg)
        canvas.scale(sx, sy)'''

new_code = '''        # CRITICAL FIX: Rotate around the center by default!
        # FADE's Python renderer draws into 1920x1080.
        cx = 1920 * 0.5 + ax
        cy = 1080 * 0.5 + ay
        canvas.translate(tx + cx, ty + cy)
        canvas.rotate(deg)
        canvas.scale(sx, sy)
        canvas.translate(-cx, -cy)'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open('backend/animation/transform.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Patched transform.py applyToCanvas")
else:
    print("Could not find applyToCanvas in transform.py")

# Also fix getModelMatrix in the same file!
old_mat = '''        return [
            [sx * cosA,  -sx * sinA,  tx],
            [sy * sinA,   sy * cosA,  ty],
            [0.0, 0.0, 1.0],
        ]'''

new_mat = '''        cx = 1920 * 0.5
        cy = 1080 * 0.5
        # M = Translate(tx + cx, ty + cy) * Rotate(deg) * Scale(sx, sy) * Translate(-cx, -cy)
        # Simplified:
        # X = sx * cosA * (x - cx) - sy * sinA * (y - cy) + tx + cx
        # Y = sx * sinA * (x - cx) + sy * cosA * (y - cy) + ty + cy
        m00 = sx * cosA
        m01 = -sy * sinA
        m10 = sx * sinA
        m11 = sy * cosA
        m02 = tx + cx - m00 * cx - m01 * cy
        m12 = ty + cy - m10 * cx - m11 * cy
        
        return [
            [m00, m01, m02],
            [m10, m11, m12],
            [0.0, 0.0, 1.0],
        ]'''

if old_mat in content:
    content = content.replace(old_mat, new_mat)
    with open('backend/animation/transform.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Patched transform.py getModelMatrix")
