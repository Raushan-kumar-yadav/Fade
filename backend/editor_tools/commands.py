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
    """
    Add a brush stroke to an ImageClip.

    Leader's model:
      - If an ImageClip is currently selected → append a BrushStroke to it.
      - If no clip is selected, or the selected clip is not an ImageClip →
        create a fresh transparent ImageClip, add it to the topmost video
        track, then append the BrushStroke to it.

    Undo removes only the last BrushStroke.  If the clip was freshly created
    by this command AND it now has no more strokes, the clip itself is removed
    from the track.
    """

    def __init__(self, engine, points, size, color, opacity, is_eraser=False):
        self.engine     = engine
        self.points     = points          # list of {"x": float, "y": float}
        self.size       = size
        self.color      = color           # RGBA list 0-1
        self.opacity    = opacity
        self.is_eraser  = is_eraser       # eraser support kept for compat

        # State set during execute() so undo() can reverse exactly this action
        self._stroke: "BrushStroke | None" = None
        self._clip              = None    # the ImageClip that received the stroke
        self._track             = None    # the track (needed for clip removal on undo)
        self._created_clip      = False   # True only if we created the clip here

        # Legacy compat: router reads cmd.clip.clipId after execute()
        self.clip = None

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _video_tracks(timeline):
        return [t for t in timeline.tracks
                if not getattr(t, 'isAudio', lambda: False)()]

    def _find_selected_image_clip(self):
        """Return (ImageClip, track) if the currently selected clip is an ImageClip."""
        import backend.state as _state
        from backend.timeline.clips.imageClip import ImageClip
        sel_id = getattr(_state, '_selected_clip_id', None)
        if not sel_id:
            return None, None
        for track in self.engine.activeTimeline.tracks:
            for c in track.clips:
                if c.clipId == sel_id and isinstance(c, ImageClip):
                    return c, track
        return None, None

    # ------------------------------------------------------------------
    # Command interface
    # ------------------------------------------------------------------

    def execute(self) -> None:
        from backend.timeline.clips.imageClip import ImageClip, BrushStroke
        import uuid

        if not self.engine.activeTimeline or not self.engine.activeTimeline.tracks:
            return

        # Reuse previously created objects on redo
        if self._stroke is not None:
            # redo path — re-attach stroke and optionally the clip
            if self._created_clip and self._clip not in self._track.clips:
                self._track.addClip(self._clip)
            self._clip.brush_strokes.append(self._stroke)
            self.clip = self._clip
            return

        # --- First execution ---

        # 1. Try to use the selected ImageClip
        img_clip, track = self._find_selected_image_clip()

        # 2. If none, create a new transparent ImageClip on the topmost video track
        if img_clip is None:
            vtracks = self._video_tracks(self.engine.activeTimeline)
            track = vtracks[-1] if vtracks else self.engine.activeTimeline.tracks[0]
            img_clip = ImageClip(
                clipId     = str(uuid.uuid4()),
                startFrame = 0,
                duration   = 150,
                assetId    = "",
                filepath   = "",
                color      = (0, 0, 0, 0),   # fully transparent — pure brush canvas
            )
            track.addClip(img_clip)
            self._created_clip = True

        # 3. Build a BrushStroke and append it to the clip
        stroke = BrushStroke(
            points  = list(self.points),
            size    = self.size,
            color   = list(self.color),
            opacity = self.opacity,
        )
        img_clip.brush_strokes.append(stroke)

        # 4. Store references for undo/redo
        self._stroke = stroke
        self._clip   = img_clip
        self._track  = track
        self.clip    = img_clip   # legacy compat

    def undo(self) -> None:
        if self._clip is None or self._stroke is None:
            return
        # Remove only this stroke
        try:
            self._clip.brush_strokes.remove(self._stroke)
        except ValueError:
            pass
        # If we created the clip and it's now empty, remove it from the track
        if self._created_clip and not self._clip.brush_strokes:
            if self._track:
                self._track.removeClip(self._clip.clipId)

    @property
    def description(self) -> str:
        return "Eraser Stroke" if self.is_eraser else "Brush Stroke"

import os
import math
import uuid
from backend.history.commandStack import Command

import math
import copy
from backend.history.commandStack import Command
from backend.timeline.clips.imageClip import BrushStroke, ImageClip

def distance_point_to_segment(p, a, b):
    vx = b[0] - a[0]
    vy = b[1] - a[1]
    wx = p[0] - a[0]
    wy = p[1] - a[1]
    
    c1 = wx * vx + wy * vy
    if c1 <= 0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
        
    c2 = vx * vx + vy * vy
    if c2 <= c1:
        return math.hypot(p[0] - b[0], p[1] - b[1])
        
    b_val = c1 / c2
    px = a[0] + b_val * vx
    py = a[1] + b_val * vy
    return math.hypot(p[0] - px, p[1] - py)

def is_point_erased(px, py, eraser_points, radius):
    if not eraser_points: return False
    if len(eraser_points) == 1:
        ex = eraser_points[0].get('x', 0)
        ey = eraser_points[0].get('y', 0)
        return math.hypot(px - ex, py - ey) <= radius
        
    for i in range(len(eraser_points) - 1):
        a = (eraser_points[i].get('x', 0), eraser_points[i].get('y', 0))
        b = (eraser_points[i+1].get('x', 0), eraser_points[i+1].get('y', 0))
        if distance_point_to_segment((px, py), a, b) <= radius:
            return True
    return False

def douglas_peucker(points, epsilon):
    if len(points) < 3:
        return points
    dmax = 0
    index = 0
    end = len(points) - 1
    for i in range(1, end):
        d = distance_point_to_segment(points[i], points[0], points[end])
        if d > dmax:
            index = i
            dmax = d
    if dmax > epsilon:
        rec_results1 = douglas_peucker(points[:index+1], epsilon)
        rec_results2 = douglas_peucker(points[index:], epsilon)
        return rec_results1[:-1] + rec_results2
    else:
        return [points[0], points[end]]

def erase_stroke(stroke, eraser_points, radius):
    if not stroke.points:
        return []
        
    new_strokes = []
    current_points = []
    
    def flush():
        if len(current_points) >= 2:
            simplified = douglas_peucker(current_points, 1.0)
            new_stroke = BrushStroke(
                points=[{"x": p[0], "y": p[1]} for p in simplified],
                size=stroke.size,
                color=stroke.color,
                opacity=stroke.opacity,
            )
            if hasattr(stroke, 'blur'):
                new_stroke.blur = stroke.blur
            new_strokes.append(new_stroke)
        current_points.clear()

    sampled = []
    MAX_STEP = max(2.0, radius / 4.0)
    
    for i in range(len(stroke.points) - 1):
        p1 = stroke.points[i]
        p2 = stroke.points[i+1]
        x1, y1 = p1.get('x', 0), p1.get('y', 0)
        x2, y2 = p2.get('x', 0), p2.get('y', 0)
        
        dist = math.hypot(x2 - x1, y2 - y1)
        steps = max(1, int(math.ceil(dist / MAX_STEP)))
        
        for step in range(steps):
            t = step / steps
            x = x1 + (x2 - x1) * t
            y = y1 + (y2 - y1) * t
            sampled.append((x, y))
            
    last_pt = stroke.points[-1]
    sampled.append((last_pt.get('x', 0), last_pt.get('y', 0)))
    
    for pt in sampled:
        if is_point_erased(pt[0], pt[1], eraser_points, radius):
            flush()
        else:
            current_points.append(pt)
            
    flush()
    return new_strokes

class EraseGeometryCommand(Command):
    def __init__(self, engine, eraser_points, radius):
        self.engine = engine
        self.eraser_points = eraser_points
        self.radius = float(radius)
        self.in_progress = False
        
        self.before_state = {}
        self.after_state = {}
        self.computed = False

    def execute(self) -> None:
        if not self.engine.activeTimeline or not self.engine.activeTimeline.tracks:
            return
            
        if not self.computed:
            self.computed = True
            for track in self.engine.activeTimeline.tracks:
                for clip in track.clips:
                    if isinstance(clip, ImageClip) and hasattr(clip, 'brush_strokes') and clip.brush_strokes:
                        self.before_state[clip.clipId] = copy.deepcopy(clip.brush_strokes)
                        new_strokes = []
                        for stroke in clip.brush_strokes:
                            new_strokes.extend(erase_stroke(stroke, self.eraser_points, self.radius))
                        self.after_state[clip.clipId] = new_strokes
                        
        for track in self.engine.activeTimeline.tracks:
            for clip in track.clips:
                if clip.clipId in self.after_state:
                    clip.brush_strokes = copy.deepcopy(self.after_state[clip.clipId])
                    
    def undo(self) -> None:
        for track in self.engine.activeTimeline.tracks:
            for clip in track.clips:
                if clip.clipId in self.before_state:
                    clip.brush_strokes = copy.deepcopy(self.before_state[clip.clipId])

    @property
    def description(self) -> str:
        return "Eraser"
