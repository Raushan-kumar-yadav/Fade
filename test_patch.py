import os
import sys
import uuid
sys.path.insert(0, os.path.abspath('.'))

from backend.engine.engine import Engine
from backend.timeline.clips.penClip import PenClip
from backend.timeline.clips.shapeClip import ShapeStyle
from backend.timeline.tracks.videoTrack import VideoTrack
from backend.routers.image_tools import StrokeRequest, add_brush
from backend.routers.clips import updatePenPoints, PenPointsRequest
from fastapi import Request

def main():
    engine = Engine()
    engine.newProject(width=1920, height=1080, fps=30.0)
    tl = engine.activeTimeline
    tl.addTrack(VideoTrack(name="Video 1"))
    
    # Inject engine into routers
    import backend.routers.image_tools
    backend.routers.image_tools.engine = engine
    import backend.routers.clips
    
    # Mock _find_clip in clips.py
    def mock_find_clip(clip_id):
        return tl.findClip(clip_id)
    backend.routers.clips._find_clip = mock_find_clip
    
    # Simulate POST /editor/brush
    req = StrokeRequest(points=[{"x": 100, "y": 100}], size=15)
    res = add_brush(req)
    
    clip_id = res.get("clipId")
    
    # Simulate PATCH /clips/pen/{clipId}/points (with a long stroke)
    points = [{"x": 100 + i, "y": 100 + i} for i in range(10)]
    patch_req = PenPointsRequest(points=points)
    updatePenPoints(clip_id, patch_req)
    
    clip, track = tl.findClip(clip_id)
    print("Points after patch:")
    print(f"  Count: {len(clip.points)}")
    for i, p in enumerate(clip.points[:3]):
        print(f"  P{i}: ({p.x}, {p.y})")
        
if __name__ == '__main__':
    main()
