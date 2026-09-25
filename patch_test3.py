import os
with open('backend/tests/test_image_tools.py', 'r', encoding='utf-8') as f:
    text = f.read()

target = '''    # Test Eraser
    cmd_eraser = AddBrushStrokeCommand(eng, pts, 20.0, [1,1,1,1], 1.0, is_eraser=True)
    eng.commandStack.execute(cmd_eraser)
    
    assert len(t.tracks[0].clips) == 2
    eraser_clip = t.tracks[0].clips[-1]
    assert eraser_clip.style.blendMode == "clear"'''

replacement = '''    # Test Eraser
    from backend.editor_tools.commands import EraseGeometryCommand
    cmd_eraser = EraseGeometryCommand(eng, pts, 20.0)
    eng.commandStack.execute(cmd_eraser)
    
    # It should have deleted the intersecting clip!
    assert len(t.tracks[0].clips) == 0'''

text = text.replace(target, replacement)
with open('backend/tests/test_image_tools.py', 'w', encoding='utf-8') as f:
    f.write(text)
