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

class EraseGeometryCommand(Command):
    def __init__(self, engine, eraser_points, radius):
        self.engine = engine
        self.eraser_points = eraser_points
        self.radius = radius
        self.track = None
        
        self.removed_clips = []
        self.added_clips = []
        self.computed = False

    def execute(self) -> None:
        from backend.timeline.clips.penClip import PenClip
        
        if not self.engine.activeTimeline or not self.engine.activeTimeline.tracks:
            return
            
        video_tracks = [t for t in self.engine.activeTimeline.tracks if not getattr(t, 'isAudio', lambda: False)()]
        self.track = video_tracks[-1] if video_tracks else self.engine.activeTimeline.tracks[0]
        
        if not self.computed:
            self.computed = True
            
            clips_to_remove = []
            new_clips = []
            
            for clip in self.track.clips:
                if isinstance(clip, PenClip):
                    chunks = []
                    current_chunk = []
                    
                    for v in clip.points:
                        erased = False
                        for ep in self.eraser_points:
                            dist = math.hypot(v.x - ep.get("x", 0), v.y - ep.get("y", 0))
                            if dist <= self.radius:
                                erased = True
                                break
                                
                        if erased:
                            if current_chunk:
                                chunks.append(current_chunk)
                                current_chunk = []
                        else:
                            current_chunk.append(v)
                            
                    if current_chunk:
                        chunks.append(current_chunk)
                        
                    # If points were removed, split the clip
                    total_remaining_points = sum(len(c) for c in chunks)
                    if len(chunks) != 1 or total_remaining_points != len(clip.points):
                        clips_to_remove.append(clip)
                        for chunk in chunks:
                            if not chunk: continue
                            new_clip = PenClip(str(uuid.uuid4()), clip.startFrame, clip.duration, style=clip.style)
                            new_clip.transform = clip.transform
                            for v in chunk:
                                new_clip.addPoint(v.x, v.y, v.inX, v.inY, v.outX, v.outY)
                            new_clips.append(new_clip)
                            
            self.removed_clips = clips_to_remove
            self.added_clips = new_clips
            
        for c in self.removed_clips:
            self.track.removeClip(c.clipId)
        for c in self.added_clips:
            self.track.addClip(c)

    def undo(self) -> None:
        if not self.track: return
        for c in self.added_clips:
            self.track.removeClip(c.clipId)
        for c in self.removed_clips:
            self.track.addClip(c)

    @property
    def description(self) -> str:
        return "Erase Geometry"


