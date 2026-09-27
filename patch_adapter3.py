import os
path = 'backend/routers/render.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_block = '''                w = float(width)
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

new_block = '''                w = float(width)
                h = float(height)
                
                # Image/Video use proportional anchors in legacy C++, Shapes use pixel anchors
                legacy_anchorX = (w / 2.0 + float(ax)) / w if clip_type in ('image', 'video', 'adjustment') else float(ax)
                legacy_anchorY = (h / 2.0 + float(ay)) / h if clip_type in ('image', 'video', 'adjustment') else float(ay)

                transform_dict = {
                    "x": float(px) - w / 2.0,
                    "y": float(py) - h / 2.0,
                    "scaleX": float(sx),
                    "scaleY": float(sy),
                    "rotation": float(rot),
                    "anchorX": legacy_anchorX,
                    "anchorY": legacy_anchorY,
                }'''

if old_block in content:
    content = content.replace(old_block, new_block)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Patched conditional anchor logic")
else:
    print("Could not find block")
