 
from __future__ import annotations
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from backend.tracking import jobs as _jobs
from backend.tracking import service as _svc

router = APIRouter(prefix="/tracking", tags=["tracking"])


#   Request models  

class StartTrackRequest(BaseModel):
    clip_id: str
    video_path: str
    from_frame: int = 0
    to_frame: int = -1
    detection_mode:  str = "face"       # face | person | text | image | manual
    initial_bbox: Optional[list] = None   # [x, y, w, h] pixels
    text_pattern: str = "email|phone"
    template_path: Optional[str] = None   # local path to reference image
    label: str = ""
    fps: float = 30.0
    comp_w: int = 1920
    comp_h: int = 1080


class LinkTrackRequest(BaseModel):
    track_id:     str
    target_clip_id: str
    properties:   list[str] = ["pos_x", "pos_y"]
    offset_x: float = 0.0
    offset_y: float = 0.0
    scale_factor: float = 1.0


#   Routes  

@router.post("/start")
def start_tracking(req: StartTrackRequest):
     
    if req.detection_mode == "manual" and not req.initial_bbox:
        raise HTTPException(400, "initial_bbox required for manual mode")
    if req.detection_mode == "image" and not req.template_path:
        raise HTTPException(400, "template_path required for image mode")
    if req.template_path and not os.path.exists(req.template_path):
        raise HTTPException(400, f"template_path not found: {req.template_path}")

    job_id = _svc.start_track_job(
        clip_id=req.clip_id,
        video_path=req.video_path,
        from_frame=req.from_frame,
        to_frame=req.to_frame,
        detection_mode=req.detection_mode,
        initial_bbox=req.initial_bbox,
        text_pattern=req.text_pattern,
        template_path=req.template_path,
        label=req.label or req.detection_mode,
        fps=req.fps,
        comp_w=req.comp_w,
        comp_h=req.comp_h,
    )
    return {"ok": True, "job_id": job_id}


@router.get("/progress/{job_id}")
def get_progress(job_id: str):
    """Poll tracking job progress."""
    job = _jobs.get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id!r} not found")
    return job


@router.post("/cancel/{job_id}")
def cancel_tracking(job_id: str):
    ok = _jobs.cancel_job(job_id)
    return {"ok": ok}


@router.get("/tracks/{clip_id}")
def list_tracks(clip_id: str):
    """List all completed tracks for a clip."""
    return {"tracks": _svc.list_tracks_for_clip(clip_id)}


@router.get("/track/{track_id}")
def get_track(track_id: str):
    """Get full track data including per-frame positions."""
    data = _svc.get_track(track_id)
    if data is None:
        raise HTTPException(404, f"Track {track_id!r} not found")
    return data


@router.delete("/track/{track_id}")
def delete_track(track_id: str):
    ok = _svc.delete_track(track_id)
    return {"ok": ok}


@router.get("/frame/{track_id}/{frame}")
def get_frame(track_id: str, frame: int):
    """
    Get interpolated tracking data at a specific frame.
    Used by the expression evaluator at render time.
    """
    data = _svc.get_track(track_id)
    if data is None:
        raise HTTPException(404, f"Track {track_id!r} not found")
    return {
        "frame": frame,
        "cx": _svc.interpolate_at(track_id, frame, "cx"),
        "cy": _svc.interpolate_at(track_id, frame, "cy"),
        "w": _svc.interpolate_at(track_id, frame, "w"),
        "h": _svc.interpolate_at(track_id, frame, "h"),
        "confidence": _svc.interpolate_at(track_id, frame, "confidence"),
    }


@router.get("/jobs")
def list_jobs():
    """List all tracking jobs (running + completed)."""
    return {"jobs": _jobs.list_jobs()}
