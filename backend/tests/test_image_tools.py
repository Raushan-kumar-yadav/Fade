import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from backend.state import engine
from backend.editor_tools.state import editor_state
from backend.history.commandStack import CommandStack
from backend.routers.image_tools import CropRequest, StrokeRequest, SelectionRequest
from backend.editor_tools.commands import CropProjectCommand, AddBrushStrokeCommand
from backend.timeline.timeline import Timeline
from backend.timeline.tracks.videoTrack import VideoTrack
from backend.timeline.clips.videoClip import VideoClip
import uuid

def setup_engine():
    engine.commandStack = CommandStack()
    engine.newProject(name="Test Project", width=1920, height=1080)
    # Add a track
    t = engine.activeTimeline
    track = VideoTrack(name="V1")
    t.addTrack(track)
    return engine

def test_selection():
    eng = setup_engine()
    from backend.history.commandStack import SetSelectionCommand
    from backend.editor_tools.state import SelectionGeometry
    
    # Test valid selection
    geom = SelectionGeometry("rect", {"x": 10, "y": 10, "w": 100, "h": 100})
    cmd = SetSelectionCommand(editor_state, geom)
    eng.commandStack.execute(cmd)
    
    sel = editor_state.selection.get_selection()
    assert sel["shape_type"] == "rect"
    assert sel["data"]["w"] == 100
    
    # Test undo
    eng.commandStack.undo()
    assert editor_state.selection.get_selection() is None

def test_crop():
    eng = setup_engine()
    # Crop to 500x500 at x=100, y=100
    cmd = CropProjectCommand(eng, 100, 100, 500, 500)
    eng.commandStack.execute(cmd)
    
    t = eng.activeTimeline
    assert t.width == 500
    assert t.height == 500
    
    # Undo
    eng.commandStack.undo()
    assert t.width == 1920
    assert t.height == 1080

def test_brush_eraser():
    eng = setup_engine()
    
    # Test Brush
    pts = [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 10.0}]
    cmd_brush = AddBrushStrokeCommand(eng, pts, 10.0, [1,0,0,1], 1.0, is_eraser=False)
    eng.commandStack.execute(cmd_brush)
    
    t = eng.activeTimeline
    assert len(t.tracks[0].clips) == 1
    brush_clip = t.tracks[0].clips[-1]
    assert brush_clip.clipType == "pen"
    assert brush_clip.style.strokeColor == [1, 0, 0, 1]
    
    # Test Eraser
    from backend.editor_tools.commands import EraseGeometryCommand
    cmd_eraser = EraseGeometryCommand(eng, pts, 20.0)
    eng.commandStack.execute(cmd_eraser)
    
    # It should have deleted the intersecting clip!
    assert len(t.tracks[0].clips) == 0
    
    # Test Undo
    eng.commandStack.undo() # Undo eraser
    assert len(t.tracks[0].clips) == 1
    eng.commandStack.undo() # Undo brush
    assert len(t.tracks[0].clips) == 0

if __name__ == "__main__":
    print("Running selection tests...")
    test_selection()
    print("Running crop tests...")
    test_crop()
    print("Running brush/eraser tests...")
    test_brush_eraser()
    print("All tests passed!")
