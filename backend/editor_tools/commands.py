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
        
        # Add stroke to the topmost track
        self.track = self.engine.activeTimeline.tracks[-1]
        self.track.addClip(self.clip)

    def undo(self) -> None:
        if self.track and self.clip:
            self.track.removeClip(self.clip.clipId)

    @property
    def description(self) -> str:
        return "Eraser Stroke" if self.is_eraser else "Brush Stroke"
