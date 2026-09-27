import os
path = 'backend/routers/render.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_block = '''                ic_xform = {
                    "x": float(ipx), "y": float(ipy),
                    "scaleX": float(isx), "scaleY": float(isy),
                    "rotation": float(irot),
                    "anchorX": float(iax), "anchorY": float(iay),
                }'''

new_block = '''                w_inner = float(c_width)
                h_inner = float(c_height)
                ic_xform = {
                    "x": float(ipx) - w_inner / 2.0,
                    "y": float(ipy) - h_inner / 2.0,
                    "scaleX": float(isx), "scaleY": float(isy),
                    "rotation": float(irot),
                    "anchorX": (w_inner / 2.0 + float(iax)) / w_inner,
                    "anchorY": (h_inner / 2.0 + float(iay)) / h_inner,
                }'''

if old_block in content:
    content = content.replace(old_block, new_block)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Patched inner clip transform adapter")
else:
    print("Failed to find block")
