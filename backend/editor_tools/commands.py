from backend.history.commandStack import Command
from backend.timeline.timeline import Timeline

class CropProjectCommand(Command):
    def __init__(self, engine, x: float, y: float, w: float, h: float):
        self.engine = engine
        self.x, self.y = x, y
        self.w, self.h = w, h
        self.old_w = 1920
        self.old_h = 1080
        self.timeline = engine.activeTimeline

    def execute(self) -> None:
        if not self.timeline: return
        self.old_w = getattr(self.timeline, 'width', 1920)
        self.old_h = getattr(self.timeline, 'height', 1080)
        self.timeline.width = self.w
        self.timeline.height = self.h
        for track in self.timeline.tracks:
            for clip in track.clips:
                clip.transform.position.setBase(
                    clip.transform.position.baseX - self.x,
                    clip.transform.position.baseY - self.y
                )
        if self.engine.compositor:
            self.engine.compositor.resize(int(self.w), int(self.h))

    def undo(self) -> None:
        if not self.timeline: return
        self.timeline.width = self.old_w
        self.timeline.height = self.old_h
        for track in self.timeline.tracks:
            for clip in track.clips:
                clip.transform.position.setBase(
                    clip.transform.position.baseX + self.x,
                    clip.transform.position.baseY + self.y
                )
        if self.engine.compositor:
            self.engine.compositor.resize(int(self.old_w), int(self.old_h))

    @property
    def description(self) -> str:
        return f"Crop Project to {self.w}x{self.h}"

class AddBrushStrokeCommand(Command):
    def __init__(self, engine, points, size, color, opacity, is_eraser=False):
        self.engine = engine
        self.points = points
        self.size = size
        self.color = color
        self.opacity = opacity
        self.is_eraser = is_eraser
        self.clip = None
        self.track = None

    def execute(self) -> None:
        from backend.timeline.clips.penClip import PenClip
        from backend.timeline.clips.shapeClip import ShapeStyle
        import uuid

        if not self.engine.activeTimeline or not self.engine.activeTimeline.tracks:
            return

        if not self.clip:
            style = ShapeStyle(shapeType="custom_path")
            style.strokeWidth = self.size
            if self.is_eraser:
                style.blendMode = "clear"
            else:
                style.strokeColor = list(self.color)
                style.fillOpacity = 0.0  # Path outline only for brush
                style.strokeOpacity = self.opacity

            self.clip = PenClip(str(uuid.uuid4()), 0, getattr(self.engine.activeTimeline, 'totalFrames', 1800), style=style)
            for p in self.points:
                self.clip.addPoint(x=p["x"], y=p["y"])

        video_tracks = [t for t in self.engine.activeTimeline.tracks if not getattr(t, 'isAudio', lambda: False)()]
        if video_tracks:
            self.track = video_tracks[-1]
            self.track.addClip(self.clip)

    def undo(self) -> None:
        if self.track and self.clip:
            self.track.removeClip(self.clip.clipId)

    @property
    def description(self) -> str:
        return "Eraser Stroke" if self.is_eraser else "Brush Stroke"

class EraseGeometryCommand(Command):
    def __init__(self, engine, eraser_points, radius):
        self.engine = engine
        self.eraser_points = eraser_points
        self.radius = float(radius)
        self.before_tracks = {}
        self.after_tracks = {}
        self.computed = False

    def execute(self) -> None:
        import copy
        import math
        if not self.engine.activeTimeline or not self.engine.activeTimeline.tracks:
            return

        if not self.computed:
            self.computed = True
            for track in self.engine.activeTimeline.tracks:
                self.before_tracks[track.name] = track.clips.copy()
                new_clips = []
                for clip in track.clips:
                    clip_type = getattr(clip, "clipType", getattr(clip, "CLIP_TYPE", ""))
                    if clip_type == "pen":
                        intersected = False
                        for v in clip.shapePath.get().vertices:
                            if not self.eraser_points: continue

                            # distance check
                            for ep in self.eraser_points:
                                ex, ey = ep.get('x', 0), ep.get('y', 0)
                                if math.hypot(v.x - ex, v.y - ey) <= self.radius:
                                    intersected = True
                                    break
                            if intersected: break

                        if not intersected:
                            new_clips.append(clip)
                    else:
                        new_clips.append(clip)
                self.after_tracks[track.name] = new_clips

        for track in self.engine.activeTimeline.tracks:
            if track.name in self.after_tracks:
                track.clips = self.after_tracks[track.name].copy()

    def undo(self) -> None:
        for track in self.engine.activeTimeline.tracks:
            if track.name in self.before_tracks:
                track.clips = self.before_tracks[track.name].copy()

    @property
    def description(self) -> str:
        return "Eraser"

class TransformClipCommand(Command):
    def __init__(self, clip_id: str, before: dict, after: dict):
        self.clip_id = clip_id
        self.before = before
        self.after = after

    @property
    def undoDescription(self) -> str:
        return "Undo Transform"

    @property
    def redoDescription(self) -> str:
        return "Redo Transform"

    def _apply(self, params: dict):
        from backend.state import engine
        tl = engine.activeTimeline
        if not tl: return
        clip = None
        for track in tl.tracks:
            for c in track.clips:
                if getattr(c, "clipId", getattr(c, "id", "")) == self.clip_id:
                    clip = c
                    break
            if clip: break
        if not clip: return

        for k, v in params.items():
            clip.applyParam(k, float(v))
            if hasattr(clip, "_lastFrame"):
                clip._lastFrame = -1

        from backend.events import notify
        notify("timeline")
        notify("render")

    def execute(self) -> None:
        self._apply(self.after)

    def undo(self) -> None:
        self._apply(self.before)

    @property
    def description(self) -> str:
        return "Transform Clip"
class BindExpressionCommand(Command):
    def __init__(self, clip_id: str, property_name: str, before_expr: str | None, after_expr: str | None):
        self.clip_id = clip_id
        self.property_name = property_name
        self.before = before_expr
        self.after = after_expr

    @property
    def undoDescription(self) -> str:
        return f"Undo bind {self.property_name}"

    @property
    def redoDescription(self) -> str:
        return f"Redo bind {self.property_name}"

    def _apply(self, expr: str | None):
        from backend.state import engine
        for tl in [engine.rootTimeline] + [c.timeline for c in getattr(engine, "comps", {}).values() if hasattr(c, "timeline")]:
            if not tl: continue
            clip, _ = tl.findClip(self.clip_id)
            if clip:
                prop_parts = self.property_name.split(".")
                obj = clip.transform
                for p in prop_parts[:-1]:
                    obj = getattr(obj, p)
                final_prop = getattr(obj, prop_parts[-1])
                final_prop.expression = expr
                return

    def execute(self):
        self._apply(self.after)

    def undo(self):
        self._apply(self.before)
