lines = open("backend/routers/render.py").read().split("\n")
start_idx = -1
end_idx = -1
for i, line in enumerate(lines):
    if 'if clip_type == "image" and hasattr(clip, "brush_strokes") and clip.brush_strokes:' in line:
        start_idx = i
        break

if start_idx != -1:
    for i in range(start_idx, len(lines)):
        if "clips_out.append(brush_clip)" in lines[i]:
            end_idx = i
            break

if start_idx != -1 and end_idx != -1:
    replacement = """                if hasattr(clip, "brush_strokes") and clip.brush_strokes:
                    for idx, stroke in enumerate(clip.brush_strokes):
                        if clip_type == "image":
                            scale = min(1920.0 / width, 1080.0 / height)
                            offset_x = (1920.0 - width * scale) / 2.0
                            offset_y = (1080.0 - height * scale) / 2.0
                            pen_points = [
                                {
                                    "x": float(pt['x']) * scale + offset_x,
                                    "y": float(pt['y']) * scale + offset_y,
                                    "inX": 0.0, "inY": 0.0,
                                    "outX": 0.0, "outY": 0.0
                                }
                                for pt in stroke.points
                            ]
                            xform = {"x": 0.0, "y": 0.0, "scaleX": 1.0, "scaleY": 1.0, "rotation": 0.0, "anchorX": 0.0, "anchorY": 0.0}
                            stroke_width = float(stroke.size) * scale
                        else:
                            pen_points = [
                                {
                                    "x": float(pt['x']),
                                    "y": float(pt['y']),
                                    "inX": 0.0, "inY": 0.0,
                                    "outX": 0.0, "outY": 0.0
                                }
                                for pt in stroke.points
                            ]
                            xform = {
                                "x": float(ipx), "y": float(ipy),
                                "scaleX": float(isx), "scaleY": float(isy),
                                "rotation": float(irot),
                                "anchorX": float(iax), "anchorY": float(iay),
                            }
                            stroke_width = float(stroke.size)

                        brush_clip = {
                            "clipId": f"{clip_id}_brush_{idx}",
                            "file": "",
                            "sourceFrame": source_frame,
                            "opacity": opacity,
                            "blendMode": blend_mode,
                            "type": "pen",
                            "transform": xform,
                            "effects": [],
                            "penStyle": {
                                "isClosed": False,
                                "points": pen_points,
                                "fillOpacity": 0.0,
                                "strokeColor": list(stroke.color),
                                "strokeWidth": stroke_width,
                                "shadowEnabled": False,
                            }
                        }
                        clips_out.append(brush_clip)"""
    new_lines = lines[:start_idx] + replacement.split("\n") + lines[end_idx+1:]
    open("backend/routers/render.py", "w").write("\n".join(new_lines))
    print("Replaced!")
else:
    print("Not found!")
