import os
with open('backend/routers/image_tools.py', 'r', encoding='utf-8') as f:
    text = f.read()

target = '''@router.post("/brush")
def add_brush(req: StrokeRequest):
    if not req.points:
        return {"status": "error", "message": "No points provided"}
    cmd = AddBrushStrokeCommand(engine, req.points, req.size, req.color, req.opacity, is_eraser=False)
    engine.commandStack.execute(cmd)
    return {"status": "ok"}

@router.post("/eraser")
def add_eraser(req: StrokeRequest):
    if not req.points:
        return {"status": "error", "message": "No points provided"}
    cmd = AddBrushStrokeCommand(engine, req.points, req.size, req.color, req.opacity, is_eraser=True)
    engine.commandStack.execute(cmd)
    return {"status": "ok"}'''

replacement = '''@router.post("/brush")
def add_brush(req: StrokeRequest):
    if not req.points:
        return {"status": "error", "message": "No points provided"}
    cmd = AddBrushStrokeCommand(engine, req.points, req.size, req.color, req.opacity, is_eraser=False)
    engine.commandStack.execute(cmd)
    return {"status": "ok", "clipId": cmd.clip.clipId if cmd.clip else None}

@router.post("/eraser")
def add_eraser(req: StrokeRequest):
    if not req.points:
        return {"status": "error", "message": "No points provided"}
    from backend.editor_tools.commands import EraseGeometryCommand
    cmd = EraseGeometryCommand(engine, req.points, req.size)
    engine.commandStack.execute(cmd)
    return {"status": "ok"}'''

text = text.replace(target, replacement)
with open('backend/routers/image_tools.py', 'w', encoding='utf-8') as f:
    f.write(text)
