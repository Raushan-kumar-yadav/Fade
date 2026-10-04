"""
routers/bg_remove_.py — REST endpoints for background removal.

POST  /bg-remove/image           — sync image removal
POST  /bg-remove/video           — async video removal (returns job_id)
GET   /bg-remove/status/{job_id} — poll job progress
POST  /bg-remove/cancel/{job_id} — cancel video job
GET   /bg-remove/jobs            — list all jobs
GET   /bg-remove/models          — list available models
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/bg-remove", tags=["bg-remove"])


# ── Request models ─────────────────────────────────────────────────────────────

class ImageRemoveRequest(BaseModel):
    input_path: str
    model: str = "u2net"        # u2net | u2netp | isnet | silueta
    output_path: str | None = None


class VideoRemoveRequest(BaseModel):
    input_path: str
    model: str = "u2netp"
    output_format: str = "webm"   # webm (alpha) | mp4 (green)
    workers: int = 4


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/models")
def list_models():
    """List available background removal models."""
    from backend.bg_remove.service import MODELS
    return {
        "models": [
            {"key": "u2net",    "name": "U²-Net",         "size": "180MB", "quality": "high",      "speed": "medium", "best_for": "general images"},
            {"key": "u2netp",   "name": "U²-Net Light",   "size": "4MB",   "quality": "good",      "speed": "fast",   "best_for": "video frames"},
            {"key": "isnet",    "name": "IS-Net",          "size": "180MB", "quality": "excellent", "speed": "medium", "best_for": "fine detail, hair"},
            {"key": "silueta",  "name": "Silueta",         "size": "43MB",  "quality": "good",      "speed": "fast",   "best_for": "portraits"},
        ]
    }


@router.post("/image")
def remove_image_bg(req: ImageRemoveRequest):
    """Remove background from a single image (synchronous)."""
    from backend.bg_remove.service import remove_background_image, MODELS
    import pathlib

    if req.model not in MODELS:
        raise HTTPException(400, f"Unknown model '{req.model}'. Choose from: {list(MODELS)}")

    if not pathlib.Path(req.input_path).exists():
        raise HTTPException(404, f"Input file not found: {req.input_path}")

    try:
        output = remove_background_image(
            input_path=req.input_path,
            model_key=req.model,
            output_path=req.output_path,
        )
        return {
            "ok": True,
            "output_path": output,
            "model": req.model,
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/video")
def remove_video_bg(req: VideoRemoveRequest):
    """Start async background removal job for a video. Returns job_id."""
    from backend.bg_remove.service import start_video_job, MODELS
    import pathlib

    if req.model not in MODELS:
        raise HTTPException(400, f"Unknown model '{req.model}'. Choose from: {list(MODELS)}")

    if not pathlib.Path(req.input_path).exists():
        raise HTTPException(404, f"Video not found: {req.input_path}")

    if req.output_format not in ("webm", "mp4"):
        raise HTTPException(400, "output_format must be 'webm' or 'mp4'")

    if not (1 <= req.workers <= 16):
        raise HTTPException(400, "workers must be between 1 and 16")

    job_id = start_video_job(
        input_path=req.input_path,
        model_key=req.model,
        output_format=req.output_format,
        workers=req.workers,
    )
    return {
        "ok": True,
        "job_id": job_id,
        "message": f"Background removal started (model={req.model}, format={req.output_format})",
        "poll_url": f"/bg-remove/status/{job_id}",
    }


@router.get("/status/{job_id}")
def get_job_status(job_id: str):
    """Get background removal job status and progress."""
    from backend.bg_remove.service import get_job
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    return job


@router.post("/cancel/{job_id}")
def cancel_job(job_id: str):
    """Cancel a running background removal job."""
    from backend.bg_remove.service import get_job, cancel_job as _cancel
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    if job["status"] in ("done", "failed", "cancelled"):
        raise HTTPException(400, f"Job is already {job['status']}")
    _cancel(job_id)
    return {"ok": True, "job_id": job_id, "message": "Cancellation requested"}


@router.get("/jobs")
def list_all_jobs():
    """List all background removal jobs."""
    from backend.bg_remove.service import list_jobs
    jobs = list_jobs()
    jobs.sort(key=lambda j: j.get("created_at", 0), reverse=True)
    return {"jobs": jobs, "total": len(jobs)}
