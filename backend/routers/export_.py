from __future__ import annotations
import threading
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.state import engine, _exportJobs

router = APIRouter()


 
class ExportStartRequest(BaseModel):
    outputPath: str
    width: int   = 1920
    height: int   = 1080
    fps: float = 30.0
    codec: str   = "auto"      # auto | h264_nvenc | h264_qsv | libx264 | libx265
    videoBitrate: str   = "8M"
    crf: int   = -1          # -1 = bitrate mode; 18–51 = CRF mode
    preset: str   = "medium"   # ultrafast → veryslow (libx264/libx265)
    audioBitrate: str   = "192k"
    audioSampleRate:  int   = 48000
    audioChannels: int   = 2
    formatId: str   = "mp4-1080"
    transparentBg:    bool  = False       # future: WebM alpha export


 
@router.post("/export/start")
def exportStart(req: ExportStartRequest):
    from backend.encoder.encoder import ExportJob, run_export
    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(400, "No active timeline")
    job = ExportJob(req.dict())
    _exportJobs[job.jobId] = job
    threading.Thread(
        target=run_export,
        args=(job, engine.compositor, tl),
        daemon=True,
    ).start()
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


 
@router.get("/export/webcomp-clips")
def getWebCompClips():
    """
    Return all WebCompClip instances in the active timeline.
    Electron calls this before the C++ export loop so it knows which
    webcomp instances to pre-render and push via pushWebCompFrame().
    """
    from backend.timeline.clips.webComp import WebCompClip
    tl = engine.activeTimeline
    clips = []
    if tl:
        for track in tl.tracks:
            if getattr(track, "muted", False):
                continue
            for clip in track.clips:
                if isinstance(clip, WebCompClip):
                    clips.append({
                        "webcompId": clip.webcompId,
                        "clipId": clip.clipId,
                        "startFrame":  clip.startFrame,
                        "endFrame": clip.endFrame,
                        "mediaOffset": clip.mediaOffset,
                    })
    return {"clips": clips}


class WebCompFramePushRequest(BaseModel):
    webcompId:  str
    frame: int
    rgbaBase64: str   # base64-encoded RGBA bytes  
    width: int
    height: int


@router.post("/export/webcomp-push-frame")
def webcompPushFrame(req: WebCompFramePushRequest):
     
    import base64
    from backend.state import _webcompExportCache
    raw = base64.b64decode(req.rgbaBase64)
    _webcompExportCache[(req.webcompId, req.frame)] = {
        "rgba":   raw,
        "width":  req.width,
        "height": req.height,
    }
    return {"ok": True}


@router.delete("/export/webcomp-cache")
def clearWebcompCache():
    """Called by Electron after export completes to free memory."""
    from backend.state import _webcompExportCache
    _webcompExportCache.clear()
    return {"ok": True}
