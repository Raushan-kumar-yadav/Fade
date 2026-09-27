import os
path = 'backend/timeline/clips/videoClip.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_block = '''                # Scale to fit inside canvas preserving aspect ratio
                scale = min(cw / iw, ch / ih)
                dw = iw * scale
                dh = ih * scale
                dx = (cw - dw) / 2.0   # centre horizontally
                dy = (ch - dh) / 2.0   # centre vertically

                dst  = skia.Rect.MakeXYWH(dx, dy, dw, dh)
                opts = skia.SamplingOptions(skia.FilterMode.kLinear)
                canvas.drawImageRect(image, dst, opts, paint)'''

new_block = '''                # FADE CANONICAL MODEL: Draw centered around (0,0) in local space
                scale = min(cw / iw, ch / ih)
                dw = iw * scale
                dh = ih * scale
                dst  = skia.Rect.MakeXYWH(-dw/2, -dh/2, dw, dh)
                opts = skia.SamplingOptions(skia.FilterMode.kLinear)
                canvas.drawImageRect(image, dst, opts, paint)'''

if old_block in content:
    content = content.replace(old_block, new_block)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Patched videoClip.py")
else:
    print("Could not find block in videoClip.py")
