with open('backend/routers/render.py', 'r', encoding='utf-8') as f:
    content = f.read()

search = """                transform_dict = {"x": 0, "y": 0, "scaleX": 1, "scaleY": 1,
                                  "rotation": 0, "anchorX": 0.0, "anchorY": 0.0}

            clip_data: dict = {
                "clipId": clip_id,
                "file": filepath,
                "sourceFrame": source_frame,

                "opacity": opacity,
                "blendMode": blend_mode,
                "type": clip_type,
                "transform": transform_dict,
                "effects": _serialize_effects(clip, frame),
            }"""

replacement = """                transform_dict = {"x": 0, "y": 0, "scaleX": 1, "scaleY": 1,
                                  "rotation": 0, "anchorX": 0.0, "anchorY": 0.0}

            base_w = 1920
            base_h = 1080
            if clip_type == 'image' and getattr(clip, '_skiaImage', None):
                base_w = clip._skiaImage.width()
                base_h = clip._skiaImage.height()
            elif clip_type == 'shape' and hasattr(clip, 'style'):
                base_w = float(getattr(clip.style, 'width', 200))
                base_h = float(getattr(clip.style, 'height', 120))
            elif clip_type == 'video' and getattr(clip, 'decoder', None):
                # We can't trivially get width without the actual decoder frame, but video sets width on its asset? No.
                # Actually, VideoDecoder frame has width/height.
                if hasattr(clip, '_cachedFrame') and clip._cachedFrame:
                     base_w = clip._cachedFrame.width
                     base_h = clip._cachedFrame.height

            clip_data: dict = {
                "clipId": clip_id,
                "file": filepath,
                "sourceFrame": source_frame,

                "opacity": opacity,
                "blendMode": blend_mode,
                "type": clip_type,
                "transform": transform_dict,
                "baseWidth": base_w,
                "baseHeight": base_h,
                "effects": _serialize_effects(clip, frame),
            }"""

content = content.replace(search.replace('\r\n', '\n'), replacement.replace('\r\n', '\n'))
with open('backend/routers/render.py', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
print("Patched render.py!")
