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
    crf: int   = -1          # -1 = bitrate mode; 18â€“51 = CRF mode
    preset: str   = "medium"   # ultrafast â†’ veryslow (libx264/libx265)
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


 
import uuid, time

# Lightweight in-memory job store for comp export jobs
_compExportJobs: dict[str, dict] = {}


class CompExportRequest(BaseModel):
    compId: str
    outputPath: str
    # Video settings (only used when kind=video)
    width: int = 1920
    height: int = 1080
    fps: float = 30.0
    codec: str = "auto"
    videoBitrate: str = "8M"
    crf: int = -1
    preset: str = "medium"
    audioBitrate: str = "192k"
    audioSampleRate: int = 48000
    audioChannels: int = 2


def _job_update(job: dict, **kw) -> None:
    job.update(kw)


def _export_image_comp(job: dict, comp_id: str, output_path: str) -> None:
    """Render an imageComp at its native resolution and save as PNG."""
    try:
        tl = engine.getTimeline(comp_id)
        if tl is None:
            _job_update(job, done=True, error=f"Composition {comp_id!r} not found")
            return
        if engine.compositor is None:
            _job_update(job, done=True, error="Compositor not initialised")
            return

        comp_w = int(getattr(tl, "width",  engine.compositor.width))
        comp_h = int(getattr(tl, "height", engine.compositor.height))

        _job_update(job, label=f"Rendering {comp_w}x{comp_h} full-res...", percent=50)

        # renderFullRes bypasses preview scale and never modifies live compositor state
        png_bytes = engine.compositor.renderFullRes(tl, 0, comp_w, comp_h)

        if not png_bytes:
            _job_update(job, done=True, error="Compositor returned empty frame")
            return

        with open(output_path, "wb") as f:
            f.write(png_bytes)

        _job_update(job, done=True, percent=100, path=output_path, label="Done")
        print(f"[CompExport] image saved -> {output_path} ({comp_w}x{comp_h})", flush=True)
    except Exception as exc:
        import traceback; traceback.print_exc()
        _job_update(job, done=True, error=str(exc))


def _export_pdf_comp(job: dict, comp_id: str, output_path: str) -> None:
    """
    Render every page imageComp at frame 0 at native page resolution ->
    PNG bytes -> combine into a single PDF using Pillow.
    """
    try:
        import io
        from PIL import Image

        tl = engine.getTimeline(comp_id)
        if tl is None:
            _job_update(job, done=True, error=f"PDF comp {comp_id!r} not found")
            return
        if engine.compositor is None:
            _job_update(job, done=True, error="Compositor not initialised")
            return

        page_ids: list[str] = getattr(tl, "page_ids", [])
        if not page_ids:
            _job_update(job, done=True, error="PDF comp has no pages")
            return

        _job_update(job, total=len(page_ids), done_pages=0,
                    label=f"Rendering page 1 of {len(page_ids)}...")

        # Fallback dimensions if a page has no width/height attribute
        fallback_w, fallback_h = engine.compositor.width, engine.compositor.height

        pil_images: list = []
        for i, pid in enumerate(page_ids):
            if job.get("cancelled"):
                _job_update(job, done=True, error="Cancelled")
                return

            page_tl = engine.getTimeline(pid)
            if page_tl is None:
                print(f"[CompExport] page {pid} not found - skipping", flush=True)
                continue

            # renderFullRes renders at exact native page size, no preview scale
            page_w = int(getattr(page_tl, "width",  fallback_w))
            page_h = int(getattr(page_tl, "height", fallback_h))
            png_bytes = engine.compositor.renderFullRes(page_tl, 0, page_w, page_h)
            if not png_bytes:
                print(f"[CompExport] page {pid} returned empty - skipping", flush=True)
                continue

            img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
            pil_images.append(img)
            print(f"[CompExport] page {i+1} rendered at {page_w}x{page_h}", flush=True)

            done = i + 1
            pct = int(done / len(page_ids) * 90)
            _job_update(job, done_pages=done, percent=pct,
                        label=f"Rendered page {done} of {len(page_ids)} ({page_w}x{page_h})...")

        if not pil_images:
            _job_update(job, done=True, error="All pages rendered empty")
            return

        _job_update(job, label="Writing PDF...", percent=95)
        first, rest = pil_images[0], pil_images[1:]
        first.save(output_path, "PDF", resolution=150,
                   save_all=True, append_images=rest)

        _job_update(job, done=True, percent=100, path=output_path, label="Done")
        print(f"[CompExport] PDF saved -> {output_path} ({len(pil_images)} pages)", flush=True)

    except ImportError:
        _job_update(job, done=True,
                    error="Pillow not installed. Run: pip install Pillow")
    except Exception as exc:
        import traceback; traceback.print_exc()
        _job_update(job, done=True, error=str(exc))


def _export_video_comp(job: dict, comp_id: str, req: "CompExportRequest") -> None:
    """Export a videoComp using the existing encoder pipeline."""
    try:
        from backend.encoder.encoder import ExportJob, run_export
        tl = engine.getTimeline(comp_id)
        if tl is None:
            _job_update(job, done=True, error=f"Composition {comp_id!r} not found")
            return
        if engine.compositor is None:
            _job_update(job, done=True, error="Compositor not initialised")
            return

        params = {
            "outputPath": req.outputPath,
            "width": req.width, "height": req.height, "fps": req.fps,
            "codec": req.codec, "videoBitrate": req.videoBitrate,
            "crf": req.crf, "preset": req.preset,
            "audioBitrate": req.audioBitrate,
            "audioSampleRate": req.audioSampleRate,
            "audioChannels": req.audioChannels,
            "formatId": "mp4-1080",
        }
        enc_job = ExportJob(params)
        _exportJobs[enc_job.jobId] = enc_job

        def _mirror():
            while not enc_job.done:
                time.sleep(0.25)
                d = enc_job.toDict()
                _job_update(job,
                            percent=d.get("percent", 0),
                            label=f"Encoding... frame {d.get('frame',0)}/{d.get('total',0)}",
                            done=d.get("done", False),
                            error=d.get("error"),
                            path=d.get("path"))
                if job.get("cancelled"):
                    enc_job.cancel()
                    break

        threading.Thread(target=_mirror, daemon=True).start()
        run_export(enc_job, engine.compositor, tl)

    except Exception as exc:
        import traceback; traceback.print_exc()
        _job_update(job, done=True, error=str(exc))


@router.post("/export/comp")
def exportComp(req: CompExportRequest):
    """
    Export a specific composition by compId.
    Auto-detects kind (image / video / pdf) and routes accordingly.
    Returns {jobId, kind} immediately; poll /export/comp/progress/{jobId}.
    """
    if engine.project is None:
        raise HTTPException(400, "No active project")

    tl = engine.getTimeline(req.compId)
    if tl is None:
        raise HTTPException(404, f"Composition {req.compId!r} not found")

    kind = getattr(tl, "kind", "video")
    job_id = str(uuid.uuid4())
    job: dict = {
        "jobId": job_id,
        "compId": req.compId,
        "kind": kind,
        "done": False,
        "cancelled": False,
        "error": None,
        "path": None,
        "percent": 0,
        "label": "Starting...",
        "done_pages": 0,
        "total": 1,
    }
    _compExportJobs[job_id] = job

    if kind == "image":
        out = req.outputPath
        if not out.lower().endswith(".png"):
            out = (out.rsplit(".", 1)[0] if "." in out else out) + ".png"
        threading.Thread(target=_export_image_comp, args=(job, req.compId, out), daemon=True).start()

    elif kind == "pdf":
        out = req.outputPath
        if not out.lower().endswith(".pdf"):
            out = (out.rsplit(".", 1)[0] if "." in out else out) + ".pdf"
        threading.Thread(target=_export_pdf_comp, args=(job, req.compId, out), daemon=True).start()

    else:  # video / root
        threading.Thread(target=_export_video_comp, args=(job, req.compId, req), daemon=True).start()

    return {"jobId": job_id, "kind": kind}


@router.get("/export/comp/progress/{jobId}")
def exportCompProgress(jobId: str):
    job = _compExportJobs.get(jobId)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


@router.post("/export/comp/cancel/{jobId}")
def exportCompCancel(jobId: str):
    job = _compExportJobs.get(jobId)
    if job is None:
        raise HTTPException(404, "Job not found")
    job["cancelled"] = True
    return {"status": "cancelled"}
