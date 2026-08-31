 
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
_cancelled_jobs: set[str] = set()  # job_ids cancelled by user mid-run


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
 
_ASSET_JOB_KEY: dict[tuple[str, str], str] = {}   


def register_asset_job(
    job_type: str,
    asset_id: str,
    label: str,
    message: str = "",
) -> str:
     
    job = _make_job(job_type, label, asset_id=asset_id)
    job_id = job["jobId"]
    # Track by  
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
     
    from backend.routers.library import _import_file
    from backend.worker.worker_bus import bus as _worker_bus
    import os

    info = _import_file(filepath)
    asset_id = info["assetId"]
    asset_type = info.get("type", "")

     
    if info.get("hasAudio"):
        try:
            _worker_bus.submit_waveform(asset_id, filepath)
        except Exception:
            pass

     
    try:
        import os as _os
        if asset_type == "video":
            register_asset_job("video_index", asset_id,
                               f"Indexing: {_os.path.basename(filepath)}",
                               message="Running Vision + Whisper…")
        elif asset_type == "image":
            register_asset_job("image_index", asset_id,
                               f"Indexing: {_os.path.basename(filepath)}",
                               message="Describing image…")
         
    except Exception as _e:
        print(f"[Jobs] register overlay job error (non-fatal): {_e}", flush=True)

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
                    message=(
                        f"{label_pfx}Ready ✓ — Auto-indexing started "
                        "(Vision+Whisper). Tap ✕ on the card to stop it."
                    ),
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
                    message=(
                        f"{label_pfx}Ready ✓ — Auto-indexing started. "
                        "Tap ✕ on the card to stop it."
                    ),
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
    from backend.config.global_config import cfg as _cfg
    from backend.routers.library import _resolve_download_dir
    from backend.events import notify as _notify

    provider = _cfg.get("generators.image_provider", "google")
    gen_dir = _resolve_download_dir(subdir="generations")

    # Dispatch to the right generator  
    if provider == "comfyui":
        from backend.tools.generators.comfyui_generator import ComfyUIImageGenerator
        base_url = _cfg.get("generators.comfyui_url",   "http://127.0.0.1:8188")
        model_name  = _cfg.get("generators.comfyui_model", "v1-5-pruned-emaonly.safetensors")
        comfyui_path = _cfg.get("generators.comfyui_path", "")
        width = int(_cfg.get("generators.comfyui_width",  512))
        height = int(_cfg.get("generators.comfyui_height", 512))
        steps = int(_cfg.get("generators.comfyui_steps",  20))
        cfg_scale = float(_cfg.get("generators.comfyui_cfg",  7.0))

        _update_job(job_id, status="running", progress=0.05,
                    message=f"{'Starting' if comfyui_path else 'Connecting to'} ComfyUI — {model_name}…")
        try:
            generator = ComfyUIImageGenerator(base_url=base_url)
            results = generator.generate(
                prompt=prompt,
                output_dir=gen_dir,
                model_name=model_name,
                width=width, height=height,
                steps=steps, cfg=cfg_scale,
                num_images=num_images,
                comfyui_path=comfyui_path,
            )
        except ConnectionError as exc:
            _update_job(job_id, status="error", message="ComfyUI not running", error=str(exc))
            return
        except Exception as exc:
            _update_job(job_id, status="error", message="ComfyUI generation failed", error=str(exc))
            return

    elif provider == "stability":
        from backend.tools.generators.stability_generator import StabilityImageGenerator
        stab_model = _cfg.get("generators.stability_model",  "core")
        stab_style = _cfg.get("generators.stability_style",  "")
        stab_width = int(_cfg.get("generators.stability_width",  1024))
        stab_height = int(_cfg.get("generators.stability_height", 1024))
        _update_job(job_id, status="running", progress=0.1,
                    message=f"Generating with Stability AI ({stab_model})…")
        try:
            results = StabilityImageGenerator().generate(
                prompt=prompt,
                output_dir=gen_dir,
                num_images=num_images,
                model=stab_model,
                width=stab_width,
                height=stab_height,
                style_preset=stab_style,
            )
        except PermissionError as exc:
            _update_job(job_id, status="error", message="Stability AI: auth/credits error", error=str(exc))
            return
        except Exception as exc:
            _update_job(job_id, status="error", message="Stability AI generation failed", error=str(exc))
            return

    elif provider == "local":

        # Ollama 
        _update_job(job_id, status="running", progress=0.05,
                    message="Local image gen not implemented yet — falling back to Gemini…")
        from backend.tools import GeminiImageGenerator
        try:
            results = GeminiImageGenerator().generate(prompt=prompt, num_images=num_images, output_dir=gen_dir)
        except Exception as exc:
            _update_job(job_id, status="error", message="Generation failed", error=str(exc))
            return

    else:  # "google" or any unknown value
        from backend.tools import GeminiImageGenerator
        _update_job(job_id, status="running", progress=0.1,
                    message="Generating with Gemini Imagen…")
        try:
            results = GeminiImageGenerator().generate(prompt=prompt, num_images=num_images, output_dir=gen_dir)
        except Exception as exc:
            _update_job(job_id, status="error", message="Gemini generation failed", error=str(exc))
            return

    # Import results into library  
    try:
        asset_ids = []
        for i, r in enumerate(results):
            _update_job(job_id,
                        progress=0.8 + 0.2 * (i + 1) / max(len(results), 1),
                        message=f"Importing result {i + 1}/{len(results)}…")
            info = _import_and_index(r["filepath"])
            asset_ids.append(info["assetId"])

        _update_job(job_id, status="done", progress=1.0,
                    message=f"Generated {len(asset_ids)} image(s)",
                    assetIds=asset_ids)
        _notify("library")

        try:
            from backend.ai.agent_jobs import on_job_done as _aj
            for aid in asset_ids:
                _aj(job_id, {"assetId": aid, "type": "image_generate"})
        except Exception:
            pass

    except Exception as exc:
        _update_job(job_id, status="error", message="Import failed", error=str(exc))


def _run_tts_generate(job_id: str, text: str, voice: str, speed: float) -> None:
    """Background worker: synthesise TTS with Kokoro and import into library."""
    from backend.config.global_config import cfg as _cfg
    from backend.routers.library import _resolve_download_dir, _import_file
    from backend.worker.worker_bus import bus as _worker_bus
    from backend.events import notify as _notify

    provider = _cfg.get("generators.tts_provider", "kokoro")
    short_text = text[:60] + ("…" if len(text) > 60 else "")

    _update_job(job_id, status="running", progress=0.05,
                message=f"Loading Kokoro model…")
    try:
        from backend.tools.generators.tts_generator import get_tts_generator
        gen_dir  = _resolve_download_dir(subdir="tts")
        generator = get_tts_generator(provider=provider)

        _update_job(job_id, progress=0.20, message=f"Synthesising: \"{short_text}\"…")

         
        if is_job_cancelled(job_id):
            return   

        kokoro_voice = voice or _cfg.get("generators.tts_kokoro_voice", "af_heart")
        result = generator.generate(
            text=text,
            output_dir=gen_dir,
            voice=kokoro_voice,
            speed=speed,
        )

         
        if is_job_cancelled(job_id):
            return   

        _update_job(job_id, progress=0.80, message="Importing audio…")
        info = _import_file(result["filepath"])
        asset_id = info["assetId"]

        # Submit waveform generation  
        try:
            _worker_bus.submit_waveform(asset_id, result["filepath"])
        except Exception:
            pass

        dur = result.get("duration_s", 0)
        _update_job(job_id, status="done", progress=1.0,
                    message=f"Ready — {dur:.1f}s | {kokoro_voice}",
                    assetIds=[asset_id])
        _notify("library")

        # Wake up waiting agent
        try:
            from backend.ai.agent_jobs import on_job_done as _aj
            _aj(job_id, {"assetId": asset_id, "type": "tts_generate",
                         "voice": kokoro_voice, "duration_s": dur,
                         "filename": info["filename"]})
        except Exception:
            pass

    except Exception as exc:
        if not is_job_cancelled(job_id):  # don't overwrite cancelled status
            _update_job(job_id, status="error", progress=1.0,
                        message="TTS failed", error=str(exc))


def _start(fn, *args) -> None:
     
    job_id = args[0] if args else None

    def _safe_run():
        try:
            fn(*args)
        except Exception as exc:
            import traceback
            print(f"[Jobs] Unhandled thread error in {fn.__name__}: {exc}", flush=True)
            traceback.print_exc()
            if job_id:
                try:
                    _update_job(job_id, status="error",
                                message="Failed", error=str(exc))
                except Exception:
                    pass

    t = threading.Thread(target=_safe_run, daemon=True, name=fn.__name__)
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

class TTSGenerateRequest(BaseModel):
    text: str
    voice: str = "af_heart"
    speed: float = 1.0


#   Routes  

@router.post("/jobs/video-download")
def start_video_download(req: VideoDownloadRequest):
     
    num = max(1, min(req.numVideos, 5))
    job_ids = []
    for i in range(num):
        label = f"Downloading [{i+1}/{num}]: {req.query}"
        job = _make_job("video_download", label)
        notify("job", job)   # push placeholder card to UI
        _start(_run_video_download, job["jobId"], req.query, 1, i, num)
        job_ids.append(job["jobId"])
    # Return first jobId  
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


@router.post("/jobs/tts-generate")
def start_tts_generate(req: TTSGenerateRequest):
    """Start an async Kokoro TTS job. Returns jobId immediately; synthesises in background.
    Poll GET /jobs/{jobId} or watch SSE job events for status + assetId."""
    short_text = req.text[:60] + ("…" if len(req.text) > 60 else "")
    label = f"TTS [{req.voice}]: {short_text}"
    job = _make_job("tts_generate", label)
    notify("job", job)    
    _start(_run_tts_generate, job["jobId"], req.text, req.voice, req.speed)
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


@router.post("/jobs/{jobId}/cancel")
def cancel_job_by_id(jobId: str):
     
    job = _get_job(jobId)
    if job is None:
        raise HTTPException(404, f"Job '{jobId}' not found")
    status = job.get("status", "")
    if status in ("done", "error", "cancelled"):
        return {"jobId": jobId, "status": status, "message": "Job already finished."}
    _cancelled_jobs.add(jobId)
    _update_job(jobId, status="cancelled", progress=job.get("progress", 0.0),
                message="Cancelled by user", error="Cancelled by user")
    return {"jobId": jobId, "status": "cancelled", "message": "Cancellation requested."}


def is_job_cancelled(job_id: str) -> bool:
    """Check if a job has been user-cancelled. Call from background worker threads."""
    return job_id in _cancelled_jobs


@router.delete("/jobs/clear-stuck")
def clear_stuck_jobs(older_than_s: int = 30):
     
    import time
    now = time.time()
    cleared = 0
    with _lock:
        for job in _jobs.values():
            if job.get("status") in ("pending", "running"):
                age = now - job.get("createdAt", now)
                if age >= older_than_s:
                    job["status"] = "error"
                    job["message"] = "Timed out (worker crashed)"
                    job["error"] = "Worker thread crashed or timed out"
                    notify("job", dict(job))
                    cleared += 1
    return {"cleared": cleared}
