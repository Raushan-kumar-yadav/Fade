with open("backend/editor_tools/commands.py", "r") as f:
    text = f.read()

import re

# Find EraseGeometryCommand and replace
pattern = re.compile(r'class EraseGeometryCommand\(Command\).*', re.DOTALL)
replacement = """class EraseGeometryCommand(Command):
    def __init__(self, engine, eraser_points, radius):
        self.engine = engine
        self.eraser_points = eraser_points
        self.radius = float(radius)
        self.in_progress = False
        
        self.before_state = {}
        self.after_state = {}
        self.computed = False

    def execute(self) -> None:
        import copy
        if not self.engine.activeTimeline or not self.engine.activeTimeline.tracks:
            return
            
        if not self.computed:
            self.computed = True
            for track in self.engine.activeTimeline.tracks:
                for clip in track.clips:
                    if hasattr(clip, 'brush_strokes') and clip.brush_strokes:
                        self.before_state[clip.clipId] = copy.deepcopy(clip.brush_strokes)
                        new_strokes = []
                        
                        clip_type = getattr(clip, "clipType", getattr(clip, "CLIP_TYPE", ""))
                        if clip_type == "image":
                            clip_eraser_points = self.eraser_points
                            clip_radius = self.radius
                        else:
                            from backend.editor_tools.transform_utils import comp_to_local, get_inverse_transform
                            px, py, sx, sy, rot, ax, ay = get_inverse_transform(clip.transform)
                            clip_eraser_points = [comp_to_local(p, px, py, sx, sy, rot, ax, ay) for p in self.eraser_points]
                            avg_scale = (abs(sx) + abs(sy)) / 2.0
                            if avg_scale == 0: avg_scale = 1.0
                            clip_radius = self.radius / avg_scale
                            
                        for stroke in clip.brush_strokes:
                            new_strokes.extend(erase_stroke(stroke, clip_eraser_points, clip_radius))
                        self.after_state[clip.clipId] = new_strokes
                        
        for track in self.engine.activeTimeline.tracks:
            for clip in track.clips:
                if clip.clipId in self.after_state:
                    clip.brush_strokes = copy.deepcopy(self.after_state[clip.clipId])
                    
    def undo(self) -> None:
        import copy
        for track in self.engine.activeTimeline.tracks:
            for clip in track.clips:
                if clip.clipId in self.before_state:
                    clip.brush_strokes = copy.deepcopy(self.before_state[clip.clipId])

    @property
    def description(self) -> str:
        return "Eraser"
"""
new_text = pattern.sub(replacement, text)
with open("backend/editor_tools/commands.py", "w") as f:
    f.write(new_text)
