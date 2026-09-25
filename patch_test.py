import os
with open('backend/tests/test_regression.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('cmd_eraser = AddBrushStrokeCommand(engine, [{"x":10,"y":10}], 10, [1,1,1,1], 1.0, True)', 'from backend.editor_tools.commands import EraseGeometryCommand\\n    cmd_eraser = EraseGeometryCommand(engine, [{"x":0,"y":0}], 15.0)')

with open('backend/tests/test_regression.py', 'w', encoding='utf-8') as f:
    f.write(text)
