import os
import re

path = 'backend/routers/render.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_block = '''            t = clip.transform
            try:
                px, py = t.position.get()
                sx, sy = t.scale.get()
                rot = t.rotation.get()
                ax, ay = t.anchor.get()
                transform_dict = {
                    "x": float(px), "y": float(py),
                    "scaleX": float(sx), "scaleY": float(sy),
                    "rotation": float(rot),
                    "anchorX": float(ax), "anchorY": float(ay),
                }
            except Exception:
                transform_dict = {"x": 0, "y": 0, "scaleX": 1, "scaleY": 1,
                                  "rotation": 0, "anchorX": 0.0, "anchorY": 0.0}'''

new_block = '''            t = clip.transform
            try:
                px, py = t.position.get()
                sx, sy = t.scale.get()
                rot = t.rotation.get()
                ax, ay = t.anchor.get()
                
                # Native image pivot compatibility
                anchor_x = float(ax)
                anchor_y = float(ay)
                if clip_type in ('image', 'video'):
                    anchor_x = (width / 2.0 + anchor_x) / float(width)
                    anchor_y = (height / 2.0 + anchor_y) / float(height)

                transform_dict = {
                    "x": float(px), "y": float(py),
                    "scaleX": float(sx), "scaleY": float(sy),
                    "rotation": float(rot),
                    "anchorX": anchor_x, "anchorY": anchor_y,
                }
            except Exception:
                transform_dict = {"x": 0, "y": 0, "scaleX": 1, "scaleY": 1,
                                  "rotation": 0, "anchorX": 0.0, "anchorY": 0.0}'''

content = content.replace(old_block, new_block)

# Let's double check if there's another loop (e.g. for inner_clip in a composition).
old_block_2 = '''                t = inner_clip.transform
                try:
                    px, py = t.position.get()
                    sx, sy = t.scale.get()
                    rot = t.rotation.get()
                    ax, ay = t.anchor.get()
                    inner_transform = {
                        "x": float(px), "y": float(py),
                        "scaleX": float(sx), "scaleY": float(sy),
                        "rotation": float(rot),
                        "anchorX": float(ax), "anchorY": float(ay),
                    }
                except Exception:
                    inner_transform = {"x": 0, "y": 0, "scaleX": 1, "scaleY": 1,
                                       "rotation": 0, "anchorX": 0.0, "anchorY": 0.0}'''

new_block_2 = '''                t = inner_clip.transform
                try:
                    px, py = t.position.get()
                    sx, sy = t.scale.get()
                    rot = t.rotation.get()
                    ax, ay = t.anchor.get()
                    
                    anchor_x = float(ax)
                    anchor_y = float(ay)
                    if inner_type in ('image', 'video'):
                        anchor_x = (width / 2.0 + anchor_x) / float(width)
                        anchor_y = (height / 2.0 + anchor_y) / float(height)

                    inner_transform = {
                        "x": float(px), "y": float(py),
                        "scaleX": float(sx), "scaleY": float(sy),
                        "rotation": float(rot),
                        "anchorX": anchor_x, "anchorY": anchor_y,
                    }
                except Exception:
                    inner_transform = {"x": 0, "y": 0, "scaleX": 1, "scaleY": 1,
                                       "rotation": 0, "anchorX": 0.0, "anchorY": 0.0}'''

content = content.replace(old_block_2, new_block_2)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Patched render.py with anchors!")
