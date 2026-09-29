from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.state import engine, _library
from backend.events import notify
from backend.tracking.tracker import run_tracking
from backend.history.commandStack import CommandStack
from backend.editor_tools.commands import BindExpressionCommand
from backend.routers.jobs import _make_job, _update_job, _start, is_job_cancelled
import uuid

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

def _run_tracking_job(job_id: str, filepath: str, fps: float, start_asset_frame: int, end_asset_frame: int, initial_bbox: tuple, asset_id: str):
    _update_job(job_id, status="running", progress=0.01, message="Initializing Tracker...")

    total_frames = max(1, end_asset_frame - start_asset_frame + 1)

    def on_progress(f: int, end_f: int) -> bool:
        if is_job_cancelled(job_id):
            return False
        processed = f - start_asset_frame
        prog = processed / total_frames
        _update_job(job_id, progress=prog, message=f"Tracking frame {processed}/{total_frames}...")
        return True

    try:
        frames_data = run_tracking(filepath, fps, start_asset_frame, end_asset_frame, initial_bbox, progress_callback=on_progress)

        if is_job_cancelled(job_id):
            return

        # Store against asset
        asset = _library.get(asset_id)
        if asset:
            tracking_id = f"track_{str(uuid.uuid4())[:8]}"
            if not hasattr(asset, "trackingResults"):
                asset.trackingResults = {}
            asset.trackingResults[tracking_id] = {
                "id": tracking_id,
                "startFrame": start_asset_frame,
                "endFrame": end_asset_frame,
                "frames": frames_data
            }

            _update_job(job_id, status="done", progress=1.0, message="Tracking Complete!", result={"tracking_id": tracking_id})
            notify("timeline")
        else:
            _update_job(job_id, status="error", progress=1.0, message="Asset not found after tracking")

    except Exception as e:
        print(f"[Tracking] Error in background thread: {e}")
        if not is_job_cancelled(job_id):
            _update_job(job_id, status="error", message="Tracking failed", error=str(e))

@router.post("/tracking/track")
def start_tracking(req: TrackRequest):
    clip, tl = _find_clip(req.clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    if not hasattr(clip, "filepath") or not clip.filepath:
        raise HTTPException(status_code=400, detail="Clip has no filepath")

    if not hasattr(clip, "assetId") or not clip.assetId:
        raise HTTPException(status_code=400, detail="Clip is not linked to an asset")

    # Map to asset frames
    start_asset_frame = clip.sourceFrame(req.start_frame) if hasattr(clip, "sourceFrame") else req.start_frame
    end_asset_frame = clip.sourceFrame(req.end_frame) if hasattr(clip, "sourceFrame") else req.end_frame

    initial_bbox = (req.x, req.y, req.width, req.height)
    fps = getattr(tl, "fps", 30.0)

    label = f"Tracking Object ({start_asset_frame} to {end_asset_frame})"
    job = _make_job("tracking", label, clip.assetId)
    notify("job", job)

    _start(_run_tracking_job, job["jobId"], clip.filepath, fps, start_asset_frame, end_asset_frame, initial_bbox, clip.assetId)

    return {"success": True, "jobId": job["jobId"], "label": label, "status": "pending"}

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


@router.get("/tracking/asset/{asset_id}")
def get_asset_tracking(asset_id: str):
    asset = _library.get(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return getattr(asset, "trackingResults", {})
