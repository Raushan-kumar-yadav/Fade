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
    
    # 1. Crop
    c1 = CropProjectCommand(engine, 10, 10, 800, 600)
    engine.commandStack.execute(c1)
    
    # 2. Brush
    pts = [{"x":0,"y":0}]
    c2 = AddBrushStrokeCommand(engine, pts, 10, [1,1,1,1], 1.0, False)
    engine.commandStack.execute(c2)
    
    # 3. Eraser
    c3 = AddBrushStrokeCommand(engine, pts, 10, [1,1,1,1], 1.0, True)
    engine.commandStack.execute(c3)
    
    print("After all 3:")
    print("Undo label:", engine.commandStack.undoDescription)
    
    # Undo
    engine.commandStack.undo()
    print("After undo:")
    print("Undo label:", engine.commandStack.undoDescription)
    print("Redo label:", engine.commandStack.redoDescription)
    
    # Redo
    engine.commandStack.redo()
    print("After redo:")
    print("Undo label:", engine.commandStack.undoDescription)
    print("Redo label:", engine.commandStack.redoDescription)

if __name__ == "__main__":
    test()
