import os

path = 'backend/timeline/clips/imageClip.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_block = '''        if self._skiaImage is not None:
            try:
                dst = skia.Rect.MakeXYWH(0, 0, 1920, 1080)
                opts = skia.SamplingOptions(skia.FilterMode.kLinear)
                canvas.drawImageRect(self._skiaImage, dst, opts, paint)
            except Exception as e:'''

new_block = '''        if self._skiaImage is not None:
            try:
                # FADE CANONICAL MODEL: Draw centered around (0,0) in local space
                imgW = self._skiaImage.width()
                imgH = self._skiaImage.height()
                scale = min(1920.0 / imgW, 1080.0 / imgH) if imgW > 0 and imgH > 0 else 1.0
                drawW = imgW * scale
                drawH = imgH * scale
                dst = skia.Rect.MakeXYWH(-drawW/2, -drawH/2, drawW, drawH)
                
                opts = skia.SamplingOptions(skia.FilterMode.kLinear)
                canvas.drawImageRect(self._skiaImage, dst, opts, paint)
            except Exception as e:'''

if old_block in content:
    content = content.replace(old_block, new_block)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Patched imageClip.py")
else:
    print("Could not find block in imageClip.py")
