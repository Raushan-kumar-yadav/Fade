import threading
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.state import engine, _exportJobs

router = APIRouter()


class ExportStartRequest(BaseModel):
    outputPath:   str
    width:        int   = 1920
    height:       int   = 1080
    fps:          float = 30.0
    codec:        str   = "auto"
    videoBitrate: str   = "8M"
    audioBitrate: str   = "192k"
    formatId:     str   = "mp4-1080"


@router.post("/export/start")
def exportStart(req: ExportStartRequest):
    from backend.encoder.encoder import ExportJob, run_export
    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(400, "No active timeline")
    job = ExportJob(req.dict())
    _exportJobs[job.jobId] = job
    threading.Thread(target=run_export, args=(job, engine.compositor, tl), daemon=True).start()
    return {"jobId": job.jobId, "total": job.total}


@router.get("/export/progress/{jobId}")
def exportProgress(jobId: str):
    job = _exportJobs.get(jobId)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job.toDict()


@router.post("/export/cancel/{jobId}")
def exportCancel(jobId: str):
    job = _exportJobs.get(jobId)
    if job is None:
        raise HTTPException(404, "Job not found")
    job.cancel()
    return {"status": "cancelled"}
