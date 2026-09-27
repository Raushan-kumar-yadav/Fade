import os
path = 'backend/routers/render.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_block = '''                w_inner = float(c_width)
                h_inner = float(c_height)
                ic_xform = {
                    "x": float(ipx) - w_inner / 2.0,
                    "y": float(ipy) - h_inner / 2.0,
                    "scaleX": float(isx), "scaleY": float(isy),
                    "rotation": float(irot),
                    "anchorX": (w_inner / 2.0 + float(iax)) / w_inner,
                    "anchorY": (h_inner / 2.0 + float(iay)) / h_inner,
                }'''

new_block = '''                w_inner = float(c_width)
                h_inner = float(c_height)
                ic_legacy_anchorX = (w_inner / 2.0 + float(iax)) / w_inner if ic_type in ('image', 'video', 'adjustment') else float(iax)
                ic_legacy_anchorY = (h_inner / 2.0 + float(iay)) / h_inner if ic_type in ('image', 'video', 'adjustment') else float(iay)

                ic_xform = {
                    "x": float(ipx) - w_inner / 2.0,
                    "y": float(ipy) - h_inner / 2.0,
                    "scaleX": float(isx), "scaleY": float(isy),
                    "rotation": float(irot),
                    "anchorX": ic_legacy_anchorX,
                    "anchorY": ic_legacy_anchorY,
                }'''

if old_block in content:
    content = content.replace(old_block, new_block)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Patched conditional anchor logic for inner clips")
else:
    print("Could not find inner clip block")
