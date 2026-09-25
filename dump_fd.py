import json
from backend.routers.render import _get_frame_data
from backend.state import engine
engine.newProject('t')
comp = engine.createComposition('t', 1080, 1920, 30, 300)
engine._active_comp_id = comp.timelineId

from backend.timeline.tracks.videoTrack import VideoTrack
comp.tracks.append(VideoTrack('v1'))

from backend.timeline.clips.imageClip import ImageClip, BrushStroke
ic = ImageClip('img.png', 1080, 1920)
ic.startFrame = 0
ic.duration = 100
ic.width = 1080
ic.height = 1920

bs = BrushStroke(points=[{'x': 693.3314, 'y': 132.3718}], size=10, color=(1,1,1,1))
ic.brush_strokes.append(bs)
comp.tracks[0].clips.append(ic)

fd = _get_frame_data(0)
print(json.dumps(fd, indent=2))
