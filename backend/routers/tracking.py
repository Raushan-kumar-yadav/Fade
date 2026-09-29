from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.state import engine
from backend.events import notify
from backend.tracking.tracker import run_tracking
from backend.history.commandStack import CommandStack
from backend.editor_tools.commands import BindExpressionCommand

router = APIRouter(tags=["tracking"])

class TrackRequest(BaseModel):
    clip_id: str
    start_frame: int
    end_frame: int
    property: str
    x: float
    y: float
    width: float
    height: float

class BindTrackingRequest(BaseModel):
    clip_id: str
    property_name: str
    expression: str | None


def _find_clip(clip_id: str):
    tls = []
    if engine and engine.rootTimeline:
        tls.append(engine.rootTimeline)
    if engine:
        for comp in getattr(engine, "comps", {}).values():
            if hasattr(comp, "timeline") and comp.timeline:
                tls.append(comp.timeline)
    for tl in tls:
        clip, track = tl.findClip(clip_id)
        if clip:
            return clip, tl
    return None, None


@router.post("/tracking/track")
def start_tracking(req: TrackRequest):
    clip, tl = _find_clip(req.clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
        
    if not hasattr(clip, "filepath") or not clip.filepath:
        raise HTTPException(status_code=400, detail="Clip has no filepath")

    try:
        # Initial bounding box for tracking
        initial_bbox = (req.x, req.y, req.width, req.height)
        
        # Run tracker
        fps = getattr(tl, "fps", 30.0)
        frames_data = run_tracking(clip.filepath, fps, req.start_frame, req.end_frame, initial_bbox)
        
        # Store tracking data
        clip.trackingData = {
            "startFrame": req.start_frame,
            "endFrame": req.end_frame,
            "property": req.property,
            "frames": frames_data
        }
        
        notify("tracking", {
            "type": "TRACKING_DONE",
            "clipId": req.clip_id,
            "success": True
        })
        
        return {"success": True, "frames_tracked": len(frames_data)}
    except Exception as e:
        print(f"[Tracking] Error: {e}")
        notify("tracking", {
            "type": "TRACKING_DONE",
            "clipId": req.clip_id,
            "success": False,
            "error": str(e)
        })
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tracking/bind")
def bind_tracking(req: BindTrackingRequest):
    clip, tl = _find_clip(req.clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
        
    prop_parts = req.property_name.split(".")
    obj = clip.transform
    for p in prop_parts[:-1]:
        if not hasattr(obj, p):
            raise HTTPException(status_code=400, detail=f"Property {req.property_name} not found")
        obj = getattr(obj, p)
        
    if not hasattr(obj, prop_parts[-1]):
        raise HTTPException(status_code=400, detail=f"Property {req.property_name} not found")
        
    final_prop = getattr(obj, prop_parts[-1])
    before_expr = getattr(final_prop, "expression", None)
    
    cmd = BindExpressionCommand(req.clip_id, req.property_name, before_expr, req.expression)
    if engine:
        engine.commandStack.execute(cmd)
    else:
        cmd.execute()
        
    notify("timeline")
    return {"success": True}
