import os
path = 'backend/timeline/clips/videoClip.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_block = '''                # Scale to fit inside canvas preserving aspect ratio
                scale = min(cw / iw, ch / ih) if iw > 0 and ih > 0 else 1.0
                drawW = iw * scale
                drawH = ih * scale

                # Center it
                px = (cw - drawW) * 0.5
                py = (ch - drawH) * 0.5

                dst = skia.Rect.MakeXYWH(px, py, drawW, drawH)
                opts = skia.SamplingOptions(skia.FilterMode.kLinear)
                canvas.drawImageRect(image, dst, opts, paint)'''

new_block = '''                # FADE CANONICAL MODEL: Draw centered around (0,0) in local space
                scale = min(cw / iw, ch / ih) if iw > 0 and ih > 0 else 1.0
                drawW = iw * scale
                drawH = ih * scale

                dst = skia.Rect.MakeXYWH(-drawW/2, -drawH/2, drawW, drawH)
                opts = skia.SamplingOptions(skia.FilterMode.kLinear)
                canvas.drawImageRect(image, dst, opts, paint)'''

if old_block in content:
    content = content.replace(old_block, new_block)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Patched videoClip.py")
else:
    print("Could not find block in videoClip.py")
