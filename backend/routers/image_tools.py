from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any
from backend.editor_tools.state import editor_state, SelectionGeometry
from backend.state import engine
from backend.history.commandStack import SetSelectionCommand
from backend.editor_tools.commands import CropProjectCommand, AddBrushStrokeCommand

router = APIRouter(prefix="/editor", tags=["editor"])

class SelectionRequest(BaseModel):
    shape_type: str
    data: dict[str, Any]

class CropRequest(BaseModel):
    x: float
    y: float
    width: float
    height: float

class StrokeRequest(BaseModel):
    points: list[dict[str, float]]
    size: float
    color: list[float] = [1.0, 1.0, 1.0, 1.0]
    opacity: float = 1.0

@router.post("/selection")
def set_selection(req: SelectionRequest):
    new_geom = SelectionGeometry(req.shape_type, req.data)
    cmd = SetSelectionCommand(editor_state, new_geom)
    engine.commandStack.execute(cmd)
    return {"status": "ok", "selection": editor_state.selection.get_selection()}

@router.get("/selection")
def get_selection():
    return {"selection": editor_state.selection.get_selection()}

@router.delete("/selection")
def clear_selection():
    cmd = SetSelectionCommand(editor_state, None)
    engine.commandStack.execute(cmd)
    return {"status": "ok", "selection": None}

@router.post("/crop")
def crop_project(req: CropRequest):
    if req.width <= 0 or req.height <= 0:
        return {"status": "error", "message": "Invalid crop dimensions"}
    cmd = CropProjectCommand(engine, req.x, req.y, req.width, req.height)
    engine.commandStack.execute(cmd)
    return {"status": "ok", "width": req.width, "height": req.height}

@router.post("/brush")
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
    return {"status": "ok"}

