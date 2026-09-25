import os
import json
from backend.state import engine
from backend.editor_tools.commands import AddBrushStrokeCommand
from backend.routers.render import _get_frame_data

engine.newProject("Test", "C:\\temp")
# Create composition
compId = engine.createComposition("TestComp", 1080, 1920, 30, 300)
engine.project.activeCompId = compId
comp = engine.activeTimeline
from backend.timeline.tracks.videoTrack import VideoTrack
track = VideoTrack("v1")
comp.tracks.append(track)

# Add brush stroke
points = [{"x": 540, "y": 960}, {"x": 550, "y": 970}]
cmd = AddBrushStrokeCommand(engine, points, 10, [1.0, 1.0, 1.0, 1.0], 1.0)
engine.commandStack.execute(cmd)

clip = comp.tracks[0].clips[0]
print("Clip type:", getattr(clip, "clipType", "image"))
print("Brush strokes:", len(getattr(clip, "brush_strokes", [])))

fd = _get_frame_data(3)
print("\nClips out:")
for c in fd.get("clips", []):
    print(c["clipId"], c["type"])
    if c["type"] == "pen":
        print("  PenStyle points:", len(c["penStyle"]["points"]))
        print("  First point:", c["penStyle"]["points"][0])
        if "error" in c["clipId"]:
            print("  Error:", c.get("textStyle"))
