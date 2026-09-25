import os
with open('backend/tests/test_regression.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace(r'from backend.editor_tools.commands import EraseGeometryCommand\n    cmd_eraser = EraseGeometryCommand(engine, [{"x":0,"y":0}], 15.0)', 'from backend.editor_tools.commands import EraseGeometryCommand\n    cmd_eraser = EraseGeometryCommand(engine, [{"x":0,"y":0}], 15.0)')

with open('backend/tests/test_regression.py', 'w', encoding='utf-8') as f:
    f.write(text)
