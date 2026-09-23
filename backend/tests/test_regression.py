import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from backend.state import engine
from backend.history.commandStack import CommandStack
from backend.editor_tools.commands import CropProjectCommand, AddBrushStrokeCommand
from backend.timeline.tracks.videoTrack import VideoTrack

def test():
    engine.commandStack = CommandStack()
    engine.newProject(name="Test", width=1920, height=1080)
    engine.activeTimeline.addTrack(VideoTrack(name="V1"))
    
    cmd_crop = CropProjectCommand(engine, 0, 0, 800, 600)
    engine.commandStack.execute(cmd_crop)
    
    cmd_brush = AddBrushStrokeCommand(engine, [{"x":0,"y":0}], 10, [1,1,1,1], 1.0, False)
    engine.commandStack.execute(cmd_brush)
    
    engine.commandStack.undo()
    engine.commandStack.redo()

def test_eraser():
    engine.commandStack = CommandStack()
    engine.newProject(name="Test2", width=1920, height=1080)
    engine.activeTimeline.addTrack(VideoTrack(name="V1"))
    
    cmd_brush = AddBrushStrokeCommand(engine, [{"x":0,"y":0}], 10, [1,1,1,1], 1.0, False)
    engine.commandStack.execute(cmd_brush)
    
    cmd_eraser = AddBrushStrokeCommand(engine, [{"x":10,"y":10}], 10, [1,1,1,1], 1.0, True)
    engine.commandStack.execute(cmd_eraser)
    
    print("After Eraser:")
    print("undoLabel:", engine.commandStack.undoDescription)
    
    desc = engine.commandStack.undo()
    print("After Undo Eraser:")
    print("undone:", desc)
    print("undoLabel:", engine.commandStack.undoDescription)
    print("redoLabel:", engine.commandStack.redoDescription)

if __name__ == '__main__':
    test()
    test_eraser()
