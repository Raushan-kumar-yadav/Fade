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
            
        self.track = self.engine.activeTimeline.tracks[-1]
        
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

