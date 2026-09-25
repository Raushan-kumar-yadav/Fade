import os
import sys
import uuid
sys.path.insert(0, os.path.abspath('.'))

from backend.engine.engine import Engine
from backend.timeline.clips.penClip import PenClip
from backend.timeline.clips.shapeClip import ShapeStyle
from backend.timeline.tracks.videoTrack import VideoTrack
from backend.routers.image_tools import StrokeRequest, add_brush
from fastapi import Request

def main():
    engine = Engine()
    engine.newProject(width=1920, height=1080, fps=30.0)
    tl = engine.activeTimeline
    tl.addTrack(VideoTrack(name="Video 1"))
    
    # Inject engine into the image_tools router
    import backend.routers.image_tools
    backend.routers.image_tools.engine = engine
    
    # Simulate POST /editor/brush
    req = StrokeRequest(points=[{"x": 100, "y": 100}], size=15)
    res = add_brush(req)
    
    print(f"API response: {res}")
    
    clip_id = res.get("clipId")
    if not clip_id:
        print("Failed to get clipId")
        return
        
    clip, track = tl.findClip(clip_id)
    print("--------------------------------------------------")
    print("STEP 1: INSPECT CREATED CLIP")
    print(f"Clip ID: {clip.clipId}")
    print(f"Type: {type(clip).__name__}")
    print(f"Track: {track.name}, isAudio={getattr(track, 'isAudio', lambda: False)()}")
    print(f"Start: {clip.startFrame}, End: {clip.startFrame + clip.duration}")
    print(f"Transform: pos={clip.transform.position.get()}, scale={clip.transform.scale.get()}, anchor={clip.transform.anchor.get()}, opacity={clip.transform.opacity.get()}")
    
    s = clip.style
    print(f"Style:")
    print(f"  strokeColor: {s.strokeColor}")
    print(f"  strokeWidth: {s.strokeWidth}")
    print(f"  fillOpacity: {s.fillOpacity}")
    if hasattr(s, 'strokeOpacity'):
        print(f"  strokeOpacity: {s.strokeOpacity}")
    print(f"  blendMode: {s.blendMode}")
    
    print("Points:")
    print(f"  Count: {len(clip.points)}")
    for i, p in enumerate(clip.points[:3]):
        print(f"  P{i}: ({p.x}, {p.y})")
        
if __name__ == '__main__':
    main()
