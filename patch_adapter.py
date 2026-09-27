import os

path = 'backend/routers/render.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_block = '''                transform_dict = {
                    "x": float(px), "y": float(py),
                    "scaleX": float(sx), "scaleY": float(sy),
                    "rotation": float(rot),
                    "anchorX": float(ax), "anchorY": float(ay),
                }'''

new_block = '''                # ADAPTER: Convert Canonical Transform (UI/Python) to Legacy C++ Transform
                # Since we cannot compile the C++ binary (skia.lib is missing on user machine),
                # we must adapt the new coordinate system to what the old C++ binary expects.
                # Legacy C++ centers the image at (w/2, h/2) and expects anchor as a percentage of width.
                w = float(width)
                h = float(height)
                transform_dict = {
                    "x": float(px) - w / 2.0,
                    "y": float(py) - h / 2.0,
                    "scaleX": float(sx),
                    "scaleY": float(sy),
                    "rotation": float(rot),
                    "anchorX": (w / 2.0 + float(ax)) / w,
                    "anchorY": (h / 2.0 + float(ay)) / h,
                }'''

if old_block in content:
    content = content.replace(old_block, new_block)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Patched render.py transform dict!")
else:
    print("Could not find block in render.py")
