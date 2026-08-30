 
from __future__ import annotations
import uuid
import time
import threading


from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.events import notify

router = APIRouter(tags=["jobs"])

 

MAX_JOBS = 30
_lock: threading.Lock = threading.Lock()
_jobs: dict[str, dict] = {}          
_order: list[str] = []            


def _make_job(
    job_type: str,
    label: str,
    asset_id: str | None = None,
) -> dict:
    job_id = str(uuid.uuid4())
    job = {
        "jobId": job_id,
        "type": job_type,
        "label": label,
        "status": "pending",
        "progress":  0.0,
        "message": "Queued…",
        "assetIds":  [],
         
        "assetId": asset_id,
        "error": None,
        "createdAt": time.time(),
    }
    with _lock:
        _jobs[job_id] = job
        _order.append(job_id)
         
        while len(_order) > MAX_JOBS:
            old = _order.pop(0)
            _jobs.pop(old, None)
    return job


def _update_job(job_id: str, **kwargs) -> None:
    """Update job fields and push an SSE notification."""
    with _lock:
        if job_id not in _jobs:
            return
        _jobs[job_id].update(kwargs)
        payload = dict(_jobs[job_id])
    notify("job", payload)


def _get_job(job_id: str) -> dict | None:
    with _lock:
        return dict(_jobs[job_id]) if job_id in _jobs else None


def _list_jobs() -> list[dict]:
    with _lock:
        return [dict(_jobs[jid]) for jid in reversed(_order) if jid in _jobs]


# Public helper 
 
_ASSET_JOB_KEY: dict[tuple[str, str], str] = {}  # (assetId, jobType)  


def register_asset_job(
    job_type: str,
    asset_id: str,
    label: str,
    message: str = "",
) -> str:
    """
    Create a running asset-bound job and emit an SSE notification immediately.
    Returns the jobId.
    """
    job = _make_job(job_type, label, asset_id=asset_id)
    job_id = job["jobId"]
    # Track by (assetId, jobType) 
    _ASSET_JOB_KEY[(asset_id, job_type)] = job_id
    _update_job(job_id, status="running", progress=0.0,
                message=message or label)
    return job_id


def complete_asset_job(
    asset_id: str,
    job_type: str,
    job_id: str | None = None,
    error: str | None = None,
) -> None:
    """
    Mark an asset-bound job as done (or error) and emit SSE.
    `job_id` is optional — will be looked up from (assetId, jobType) if not given.
    """
    if job_id is None:
        job_id = _ASSET_JOB_KEY.get((asset_id, job_type))
    if job_id is None:
        return
    if error:
        _update_job(job_id, status="error", progress=1.0, error=error,
                    message=f"Failed: {error[:80]}")
    else:
        _update_job(job_id, status="done", progress=1.0, message="Done")
    # Clean up lookup key
    _ASSET_JOB_KEY.pop((asset_id, job_type), None)



# Worker helpers

def _import_and_index(filepath: str) -> dict:
    """
    Import a file into the library AND fire semantic indexing + waveform —
    same as the HTTP /library/import route does, but callable from the worker
    thread so agent-downloaded media is treated identically to GUI-imported media.
    Returns the asset dict with assetId, type, etc.
    """
    from backend.routers.library import _import_file, _resolve_download_dir
    from backend.worker.worker_bus import bus as _worker_bus
    import os

    info = _import_file(filepath)
    asset_id = info["assetId"]
    asset_type = info.get("type", "")

    # Fire waveform for audio-bearing assets
    if info.get("hasAudio"):
        try:
            _worker_bus.submit_waveform(asset_id, filepath)
        except Exception:
            pass

    # Fire semantic indexing — the core that was missing for agent downloads
    if asset_type == "video":
        try:
            import os as _os
            port = int(_os.environ.get("BACKEND_PORT", 8000))
            from backend.ai.VideoSemantic.indexer import get_db_path as _get_db
            _worker_bus.submit_index_video(asset_id, filepath,
                                           port=port, db_path=_get_db())
            # Register the overlay job (direct call — same module, no circular import)
            register_asset_job("video_index", asset_id,
                               f"Indexing: {_os.path.basename(filepath)}",
                               message="Running Vision + Whisper…")
        except Exception as _e:
            print(f"[Jobs] index_video submit error (non-fatal): {_e}", flush=True)

    elif asset_type == "image":
        try:
            from backend.ai.VideoSemantic.indexer import get_db_path as _get_db
            _worker_bus.submit_index_image(asset_id, filepath, db_path=_get_db())
            import os as _os
            register_asset_job("image_index", asset_id,
                               f"Indexing: {_os.path.basename(filepath)}",
                               message="Describing image…")
        except Exception as _e:
            print(f"[Jobs] index_image submit error (non-fatal): {_e}", flush=True)

    return info


def _run_video_download(parent_job_id: str, query: str, num_videos: int,
                        video_index: int, total: int) -> None:
    """
    Worker for ONE video download. Each video gets its own job card.
    parent_job_id is the job created by the endpoint — we reuse it for the first
    video and create child jobs for subsequent ones.
    """
    from backend.tools import YtdlpDownloader
    from backend.routers.library import _resolve_download_dir
    from backend.state import engine
    from backend.events import notify as _notify

    label_pfx = f"[{video_index+1}/{total}] " if total > 1 else ""
    _update_job(parent_job_id, status="running", progress=0.0,
                message=f"{label_pfx}Searching: {query}…")
    try:
        downloader = YtdlpDownloader()
        proj = engine.project
        fps = float(proj.fps) if proj else 30.0
        downloads_dir = _resolve_download_dir()

        # Download exactly 1 video
        results = downloader.search_and_download(
            query=query, num_videos=1,
            output_dir=downloads_dir, fps=fps,
        )
        if not results:
            _update_job(parent_job_id, status="error",
                        message="No results found", error="No results found")
            return

        r = results[0]
        _update_job(parent_job_id, progress=0.7,
                    message=f"{label_pfx}Importing: {r.get('title', '')[:40]}…")
        info = _import_and_index(r["filepath"])
        asset_id = info["assetId"]

        _update_job(parent_job_id, status="done", progress=1.0,
                    message=f"{label_pfx}Ready: {r.get('title', '')[:40]}",
                    assetIds=[asset_id])
        _notify("library")
        # Notify agent if it scheduled this job
        try:
            from backend.ai.agent_jobs import on_job_done as _aj
            _aj(parent_job_id, {"assetId": asset_id, "type": "video_download",
                                "title": r.get("title", "")})
        except Exception:
            pass

    except Exception as exc:
        _update_job(parent_job_id, status="error", message="Failed", error=str(exc))


def _run_image_download(parent_job_id: str, query: str,
                        img_index: int, total: int) -> None:
    """Worker for ONE image download."""
    from backend.tools import ImageDownloader
    from backend.routers.library import _resolve_download_dir
    from backend.events import notify as _notify

    label_pfx = f"[{img_index+1}/{total}] " if total > 1 else ""
    _update_job(parent_job_id, status="running", progress=0.0,
                message=f"{label_pfx}Searching: {query}…")
    try:
        downloader = ImageDownloader()
        downloads_dir = _resolve_download_dir()
        results = downloader.search_and_download(
            query=query, num_images=1, output_dir=downloads_dir,
        )
        if not results:
            _update_job(parent_job_id, status="error",
                        message="No results", error="No results found")
            return

        r = results[0]
        _update_job(parent_job_id, progress=0.7,
                    message=f"{label_pfx}Importing image…")
        info = _import_and_index(r["filepath"])
        asset_id = info["assetId"]

        _update_job(parent_job_id, status="done", progress=1.0,
                    message=f"{label_pfx}Ready",
                    assetIds=[asset_id])
        _notify("library")
        # Notify agent if it scheduled this job
        try:
            from backend.ai.agent_jobs import on_job_done as _aj
            _aj(parent_job_id, {"assetId": asset_id, "type": "image_download"})
        except Exception:
            pass

    except Exception as exc:
        _update_job(parent_job_id, status="error", message="Failed", error=str(exc))


def _run_image_generate(job_id: str, prompt: str, num_images: int) -> None:
    from backend.tools import GeminiImageGenerator
    from backend.routers.library import _resolve_download_dir
    from backend.events import notify as _notify

    _update_job(job_id, status="running", progress=0.1,
                message="Generating with Gemini…")
    try:
        generator = GeminiImageGenerator()
        gen_dir = _resolve_download_dir(subdir="generations")
        results = generator.generate(
            prompt=prompt, num_images=num_images, output_dir=gen_dir,
        )
        asset_ids = []
        for i, r in enumerate(results):
            _update_job(job_id,
                        progress=0.8 + 0.2 * (i + 1) / max(num_images, 1),
                        message=f"Importing result {i + 1}/{len(results)}…")
            info = _import_and_index(r["filepath"])
            asset_ids.append(info["assetId"])

        _update_job(job_id, status="done", progress=1.0,
                    message=f"Generated {len(asset_ids)} image(s)",
                    assetIds=asset_ids)
        _notify("library")
        # Notify agent if it scheduled this job
        try:
            from backend.ai.agent_jobs import on_job_done as _aj
            for aid in asset_ids:
                _aj(job_id, {"assetId": aid, "type": "image_generate"})
        except Exception:
            pass

    except Exception as exc:
        _update_job(job_id, status="error", message="Failed", error=str(exc))


def _start(fn, *args) -> None:
    t = threading.Thread(target=fn, args=args, daemon=True)
    t.start()


#   Request models  

class VideoDownloadRequest(BaseModel):
    query: str
    numVideos: int = 2

class ImageDownloadRequest(BaseModel):
    query: str
    numImages: int = 2

class ImageGenerateRequest(BaseModel):
    prompt: str
    numImages: int = 1


#   Routes  

@router.post("/jobs/video-download")
def start_video_download(req: VideoDownloadRequest):
    """Start async YouTube video download jobs — ONE job card per video.
    Returns list of jobIds immediately so the UI shows N placeholder cards."""
    num = max(1, min(req.numVideos, 5))
    job_ids = []
    for i in range(num):
        label = f"Downloading [{i+1}/{num}]: {req.query}"
        job = _make_job("video_download", label)
        notify("job", job)   # push placeholder card to UI
        _start(_run_video_download, job["jobId"], req.query, i, num)
        job_ids.append(job["jobId"])
    # Return first jobId for backward-compat; caller can poll any
    return {"jobId": job_ids[0], "jobIds": job_ids,
            "label": f"Downloading {num} video(s): {req.query}",
            "status": "pending"}


@router.post("/jobs/image-download")
def start_image_download(req: ImageDownloadRequest):
    """Start async image download jobs — ONE job card per image."""
    num = max(1, min(req.numImages, 10))
    job_ids = []
    for i in range(num):
        label = f"Image [{i+1}/{num}]: {req.query}"
        job = _make_job("image_download", label)
        notify("job", job)
        _start(_run_image_download, job["jobId"], req.query, i, num)
        job_ids.append(job["jobId"])
    return {"jobId": job_ids[0], "jobIds": job_ids,
            "label": f"Downloading {num} image(s): {req.query}",
            "status": "pending"}


@router.post("/jobs/image-generate")
def start_image_generate(req: ImageGenerateRequest):
    """Start an async Gemini image generation job. Returns immediately with jobId."""
    num = max(1, min(req.numImages, 4))
    short_prompt = req.prompt[:60] + ("…" if len(req.prompt) > 60 else "")
    label = f"Generating: {short_prompt}"
    job = _make_job("image_generate", label)
    notify("job", job)
    _start(_run_image_generate, job["jobId"], req.prompt, num)
    return {"jobId": job["jobId"], "label": label, "status": "pending"}


@router.get("/jobs/")
def list_jobs(active_only: bool = False):
    """Return recent media jobs (newest first).
    Pass ?active_only=true to get only pending/running jobs."""
    jobs = _list_jobs()
    if active_only:
        jobs = [j for j in jobs if j["status"] in ("pending", "running")]
    return {"jobs": jobs}


@router.get("/jobs/{jobId}")
def get_job(jobId: str):
    """Return status of a single job."""
    job = _get_job(jobId)
    if job is None:
        raise HTTPException(404, f"Job '{jobId}' not found")
    return job
