import re
with open("backend/editor_tools/commands.py", "r") as f:
    text = f.read()

# AddBrushStrokeCommand
text = text.replace(
    '            from backend.editor_tools.transform_utils import comp_to_local\n            points_to_save = [comp_to_local(p, clip.transform) for p in self.points]',
    '            from backend.editor_tools.transform_utils import comp_to_local, get_inverse_transform\n            px, py, sx, sy, rot, ax, ay = get_inverse_transform(clip.transform)\n            points_to_save = [comp_to_local(p, px, py, sx, sy, rot, ax, ay) for p in self.points]'
)

# EraseGeometryCommand
text = text.replace(
    '                            clip_eraser_points = [comp_to_local(p, clip.transform) for p in self.eraser_points]',
    '                            from backend.editor_tools.transform_utils import comp_to_local, get_inverse_transform\n                            px, py, sx, sy, rot, ax, ay = get_inverse_transform(clip.transform)\n                            clip_eraser_points = [comp_to_local(p, px, py, sx, sy, rot, ax, ay) for p in self.eraser_points]'
)

with open("backend/editor_tools/commands.py", "w") as f:
    f.write(text)
