import os
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.state import engine, _library
from backend.media.asset.mediaAsset import MediaAsset
from backend.worker.worker_bus import bus as _worker_bus
from backend.tools import YtdlpDownloader, ImageDownloader, GeminiImageGenerator
from backend.tools.generators.tts_generator import get_tts_generator, GEMINI_VOICES
from backend.tools.generators.video_generator import get_video_generator
from backend.config.global_config import cfg as _cfg

router = APIRouter()


class ImportRequest(BaseModel):
    filepath: str


class DownloadSearchRequest(BaseModel):
    query: str
    numVideos: int = 2


class DownloadImagesRequest(BaseModel):
    query: str
    numImages: int = 2


class GenerateImageRequest(BaseModel):
    prompt: str
    numImages: int = 1


class GenerateTTSRequest(BaseModel):
    text: str
    voice: str = ""    # Google voice name; empty  


class GenerateVideoRequest(BaseModel):
    prompt: str
    durationSeconds: int = 5
    aspectRatio: str = "16:9"


class RelinkRequest(BaseModel):
    filepath: str


def _resolve_download_dir(subdir: str = "") -> str:
    proj = engine.project
    base = proj.settings.mediaDownloadPath if (proj and proj.settings.mediaDownloadPath) else ""
    if not base:
        base = str(Path.home() / ".fade" / "downloads")
    path = os.path.join(base, subdir) if subdir else base
    os.makedirs(path, exist_ok=True)
    return path


def _queue_semantic_index(asset_id: str, filepath: str, mtype: str) -> None:
    """Queue semantic indexing for image or video assets. Non-fatal."""
    try:
        from backend.ai.VideoSemantic.indexer import get_db_path as _get_db, is_asset_indexed
        if is_asset_indexed(asset_id):
            return  # already in ChromaDB  
        if mtype == "image":
            _worker_bus.submit_index_image(asset_id, filepath, db_path=_get_db())
            print(f"[Library] ✓ index_image queued for {asset_id[:8]}", flush=True)
        elif mtype == "video":
            port = int(os.environ.get("BACKEND_PORT", 8000))
            _worker_bus.submit_index_video(asset_id, filepath, port=port, db_path=_get_db())
            print(f"[Library] ✓ index_video queued for {asset_id[:8]}", flush=True)
    except Exception as _e:
        print(f"[Library] ✗ Semantic index queue error (non-fatal): {_e}", flush=True)


def _queue_audio_transcript(asset_id: str, filepath: str) -> None:
    """Queue Whisper transcription for an audio file. Non-fatal."""
    try:
        from backend.ai.VideoSemantic.indexer import get_db_path as _get_db
        from backend.worker.transcript_status import is_done as _ts_done
        if _ts_done(asset_id):
            return  # already done 
        _worker_bus.submit_transcribe_audio(asset_id, filepath, db_path=_get_db())
        # Create an SSE job card so the library card shows  
        try:
            from backend.routers.jobs import register_asset_job as _reg
            from backend.events import notify as _notify
            import os as _os
            _reg(
                "audio_transcript",
                asset_id,
                f"Transcribing: {_os.path.basename(filepath)}",
                message="Running Whisper…",
            )
            _notify("library")   
        except Exception as _je:
            print(f"[Library]   audio_transcript job register error (non-fatal): {_je}", flush=True)
    except Exception as _e:
        print(f"[Library]  Audio transcript queue error (non-fatal): {_e}", flush=True)


def _import_file(filepath: str) -> dict:
    """Register a file into _library, deduplicating by path. Returns asset dict."""
    _AUDIO_EXTS = {".wav", ".mp3", ".aac", ".flac", ".ogg", ".m4a"}
    for a in _library.values():
        if a.filepath == filepath:
            if a.hasAudio:
                try:
                    _worker_bus.submit_waveform(a.assetId, a.filepath)
                except Exception:
                    pass
            mtype = a.mediaType.value if hasattr(a.mediaType, 'value') else str(a.mediaType)
            if mtype == "audio" or os.path.splitext(filepath)[1].lower() in _AUDIO_EXTS:
                _queue_audio_transcript(a.assetId, a.filepath)
            return {"assetId": a.assetId, "filename": os.path.basename(a.filepath),
                    "filepath": a.filepath, "type": mtype, "hasAudio": a.hasAudio}
    assetId = str(uuid.uuid4())
    asset = MediaAsset(filepath=filepath, assetId=assetId)
    _library[assetId] = asset
    if asset.hasAudio:
        try:
            _worker_bus.submit_waveform(assetId, filepath)
        except Exception:
            pass
    mtype = asset.mediaType.value if hasattr(asset.mediaType, 'value') else str(asset.mediaType)
    print(f"[Library] Imported {os.path.basename(filepath)} → assetId={assetId[:8]} type={mtype}", flush=True)

    # Queue semantic indexing for video/image 
    if mtype == "audio" or os.path.splitext(filepath)[1].lower() in _AUDIO_EXTS:
        _queue_audio_transcript(assetId, filepath)
    else:
        _queue_semantic_index(assetId, filepath, mtype)
    return {"assetId": assetId, "filename": os.path.basename(filepath),
            "filepath": filepath, "type": mtype, "hasAudio": asset.hasAudio}


@router.get("/library/assets")
def listAssets():
    from backend.media.asset.baseAsset import MediaType
    return [
        {
            "assetId":  a.assetId,
            "filename": os.path.basename(a.filepath),
            "filepath": a.filepath,
            "type": a.mediaType.value if hasattr(a.mediaType, 'value') else str(a.mediaType),
        }
        for a in _library.values()
         
        if getattr(a, 'mediaType', None) != MediaType.webcomp
    ]


@router.get("/library/assets/rich")
def listAssetsRich():
    """Rich library dump for the AI agent.

    Returns every asset (video, image, audio, webcomp) enriched with:
      - durationFrames / durationSec / fps / width / height / hasAudio
      - indexStatus  (done | running | not_started | error)
      - transcriptStatus (done | running | not_started)
      - sceneChunks  [{start_s, end_s, text}]  — if indexed (video/image)
      - imageDescription str                    — if indexed (image)
      - transcript   [{start, end, text}]       — if Whisper done (audio/video)

    Also appends all compositions (nested timelines) as entries with type='comp'.
    """
    from backend.media.asset.baseAsset import MediaType
    from backend.worker import transcript_status as _ts
    from backend.routers.jobs import _ASSET_JOB_KEY, _jobs, _lock as _job_lock

    # ── helpers ──────────────────────────────────────────────────────────────
    def _index_status(asset_id: str) -> str:
        status = _worker_bus.get_index_status(asset_id)
        if not status:
            # Check ChromaDB directly
            try:
                from backend.ai.VideoSemantic.indexer import is_asset_indexed
                return "done" if is_asset_indexed(asset_id) else "not_started"
            except Exception:
                return "not_started"
        return status.get("status", "not_started")

    def _transcript_status(asset_id: str) -> str:
        if _ts.is_done(asset_id):
            return "done"
        job_id = _ASSET_JOB_KEY.get((asset_id, "audio_transcript"))
        if job_id:
            with _job_lock:
                job = _jobs.get(job_id)
            if job and job.get("status") in ("running", "pending"):
                return "running"
        return "not_started"

    def _scene_chunks(asset_id: str, mtype: str) -> list:
        if mtype not in ("video", "image"):
            return []
        try:
            from backend.ai.VideoSemantic.indexer import _col, _img_col
            if mtype == "video" and _col:
                res = _col.get(
                    where={"assetId": asset_id},
                    include=["documents", "metadatas"],
                    limit=500,
                )
                chunks = []
                for doc, meta in zip(res["documents"], res["metadatas"]):
                    if doc and doc.strip():
                        chunks.append({
                            "start_s": round(float(meta.get("start_sec", 0)), 2),
                            "end_s":   round(float(meta.get("end_sec",   0)), 2),
                            "text":    doc.strip(),
                        })
                chunks.sort(key=lambda c: c["start_s"])
                return chunks
        except Exception:
            pass
        return []

    def _image_description(asset_id: str) -> str:
        try:
            from backend.ai.VideoSemantic.indexer import _img_col
            if _img_col:
                res = _img_col.get(where={"assetId": asset_id}, include=["documents"])
                if res["documents"]:
                    return res["documents"][0]
        except Exception:
            pass
        return ""

    def _transcript_segments(asset_id: str, filepath: str, mtype: str) -> list:
        """Return cached Whisper transcript from ChromaDB if already indexed."""
        if mtype not in ("video", "audio"):
            return []
        if not _ts.is_done(asset_id):
            return []
        try:
            from backend.ai.VideoSemantic.indexer import get_segments_for_asset
            segs = get_segments_for_asset(asset_id)
             
            return [{"start": s["start_s"], "end": s["end_s"], "text": s["text"]} for s in segs]
        except Exception:
            return []

    # Build asset list  
    results = []
    fps_proj = float(engine.project.fps) if engine.project else 30.0

    for a in _library.values():
        mtype_raw = getattr(a, 'mediaType', None)
        mtype = mtype_raw.value if hasattr(mtype_raw, 'value') else str(mtype_raw)

        # Duration
        dur_frames = getattr(a, 'durationFrames', 0) or 0
        asset_fps = getattr(a, 'fps', 0.0) or fps_proj
        dur_sec = round(dur_frames / asset_fps, 3) if asset_fps and dur_frames else 0.0

        idx_status = _index_status(a.assetId)
        tx_status  = _transcript_status(a.assetId)

        entry = {
            "assetId": a.assetId,
            "filename": os.path.basename(a.filepath),
            "filepath": a.filepath,
            "type": mtype,
            "durationFrames":  dur_frames,
            "durationSec": dur_sec,
            "fps": round(asset_fps, 3),
            "width": getattr(a, 'width',    0),
            "height": getattr(a, 'height',   0),
            "hasAudio": bool(getattr(a, 'hasAudio', False)),
            "indexStatus": idx_status,
            "transcriptStatus": tx_status,
        }

        # Enrich with indexed content
        if mtype == "video":
            entry["sceneChunks"] = _scene_chunks(a.assetId, "video")
            entry["transcript"]  = _transcript_segments(a.assetId, a.filepath, "video")
        elif mtype == "image":
            entry["imageDescription"] = _image_description(a.assetId)
        elif mtype == "audio":
            entry["transcript"] = _transcript_segments(a.assetId, a.filepath, "audio")

        results.append(entry)

    # Append compositions  
    if engine.project:
        root_id = engine.project.timelines[0].timelineId if engine.project.timelines else ""
        proj_w = engine.project.width
        proj_h = engine.project.height
        for tl in engine.project.timelines:
            if tl.timelineId == root_id:
                continue   
            results.append({
                "assetId": tl.timelineId,
                "filename": tl.name,
                "filepath": "",
                "type": "comp",
                "durationFrames": getattr(tl, "totalFrames", 0),
                "durationSec": round(getattr(tl, "totalFrames", 0) / fps_proj, 3),
                "fps": float(getattr(tl, "fps", fps_proj)),
                "width": getattr(tl, "width",  proj_w),
                "height": getattr(tl, "height", proj_h),
                "hasAudio": False,
                "indexStatus": "not_started",
                "transcriptStatus": "not_started",
                "trackCount": len(tl.tracks),
                "clipCount": sum(len(t.clips) for t in tl.tracks),
            })

    return results




@router.post("/library/import")
def importAsset(req: ImportRequest):
    if not os.path.exists(req.filepath):
        raise HTTPException(404, f"File not found: {req.filepath}")
    result = _import_file(req.filepath)
    from backend.events import notify; notify("library")

    
    fname = os.path.basename(req.filepath)
    mtype = result.get("type", "")
    if mtype == "video":
        try:
            from backend.routers.jobs import register_asset_job as _rj
            _rj("video_index", result["assetId"], f"Indexing: {fname}",
                message="Running Vision + Whisper…")
        except Exception:
            pass
    elif mtype == "image":
        try:
            from backend.routers.jobs import register_asset_job as _rj
            _rj("image_index", result["assetId"], f"Indexing: {fname}",
                message="Describing image…")
        except Exception:
            pass

    return result

    # Register job progress overlay for audio
    if result.get("type") == "audio" or os.path.splitext(req.filepath)[1].lower() in {".wav",".mp3",".aac",".flac",".ogg",".m4a"}:
        try:
            from backend.routers.jobs import register_asset_job as _rj
            fname = os.path.basename(req.filepath)
            _rj("audio_transcript", result["assetId"], f"Transcribing: {fname}",
                message="Running Whisper…")
        except Exception:
            pass

    return result


@router.delete("/library/assets/{assetId}")
def deleteAsset(assetId: str):
    _library.pop(assetId, None)
    from backend.events import notify; notify("library")
    
    try:
        from backend.ai.VideoSemantic.indexer import delete_video_index
        from backend.worker.index_cache import remove as _remove_index
        delete_video_index(assetId)
        _remove_index(assetId)
    except Exception:
        pass


@router.get("/library/index-status/{assetId}")
def getIndexStatus(assetId: str):
    """Check VideoSemantic indexing progress for an asset."""
    status = _worker_bus.get_index_status(assetId)
    if not status:
        return {"assetId": assetId, "status": "not_started"}
    return {"assetId": assetId, **status}


@router.post("/library/cancel-index/{assetId}")
def cancelIndex(assetId: str):
    """Stop/cancel an active or queued indexing job for a specific asset.
    Safe to call even if no job is running — it is idempotent.
    The sandbox worker will stop at the next frame-extraction checkpoint."""
    _worker_bus.cancel_index(assetId)
    return {"assetId": assetId, "status": "cancelled", "message": "Indexing cancelled"}


@router.get("/library/transcript-status/{assetId}")
def getTranscriptStatus(assetId: str):
     
    from backend.worker.transcript_status import is_done as _ts_done
    from backend.routers.jobs import _ASSET_JOB_KEY, _jobs, _lock
    if _ts_done(assetId):
        return {"assetId": assetId, "status": "done"}
    # Check if there's an active job for this asset
    job_id = _ASSET_JOB_KEY.get((assetId, "audio_transcript"))
    if job_id:
        with _lock:
            job = _jobs.get(job_id)
        if job and job.get("status") in ("running", "pending"):
            return {"assetId": assetId, "status": "running"}
    return {"assetId": assetId, "status": "not_started"}


@router.post("/library/relink/{assetId}")
def relinkAsset(assetId: str, req: RelinkRequest):
    if not os.path.exists(req.filepath):
        raise HTTPException(404, f"File not found: {req.filepath}")
    asset = MediaAsset(filepath=req.filepath, assetId=assetId)
    _library[assetId] = asset
    if asset.hasAudio:
        try:
            _worker_bus.submit_waveform(assetId, req.filepath)
        except Exception:
            pass
    print(f"[Library] Relinked {assetId[:8]}... -> {req.filepath}", flush=True)
    from backend.events import notify; notify("library")
    return {"assetId": assetId, "filepath": req.filepath,
            "filename": os.path.basename(req.filepath), "hasAudio": asset.hasAudio}


@router.post("/media/download-search")
def download_search(req: DownloadSearchRequest):
    downloader = YtdlpDownloader()
    proj = engine.project
    fps  = float(proj.fps) if proj else 30.0
    downloads_dir = _resolve_download_dir()
    results = downloader.search_and_download(
        query=req.query, num_videos=req.numVideos, output_dir=downloads_dir, fps=fps,
    )
    imported = []
    for r in results:
        info = _import_file(r["filepath"])
        imported.append({
            "assetId": info["assetId"],
            "filename": info["filename"],
            "title": r["title"],
            "durationFrames": int(r["duration_sec"] * fps),
        })
    from backend.events import notify; notify("library")
    return {"assets": imported}


@router.post("/media/download-images")
def download_images(req: DownloadImagesRequest):
    downloader = ImageDownloader()
    downloads_dir = _resolve_download_dir()
    results = downloader.search_and_download(query=req.query, num_images=req.numImages, output_dir=downloads_dir)
    imported = []
    for r in results:
        info = _import_file(r["filepath"])
        imported.append({"assetId": info["assetId"], "filename": info["filename"], "title": r["title"]})
    from backend.events import notify; notify("library")
    return {"assets": imported}


@router.post("/media/generate-image")
def generate_image_endpoint(req: GenerateImageRequest):
    from fastapi import HTTPException
    provider = _cfg.get("generators.image_provider", "google")
    gen_dir = _resolve_download_dir(subdir="generations")

    try:
        if provider == "comfyui":
            from backend.tools.generators.comfyui_generator import ComfyUIImageGenerator
            comfyui_url = _cfg.get("generators.comfyui_url",    "http://127.0.0.1:8188")
            comfyui_model = _cfg.get("generators.comfyui_model",  "v1-5-pruned-emaonly.safetensors")
            comfyui_w  = _cfg.get("generators.comfyui_width",  512)
            comfyui_h = _cfg.get("generators.comfyui_height", 512)
            comfyui_steps = _cfg.get("generators.comfyui_steps",  20)
            comfyui_cfg   = _cfg.get("generators.comfyui_cfg",    7.0)
            gen = ComfyUIImageGenerator(base_url=comfyui_url)
            results = gen.generate(
                prompt=req.prompt,
                output_dir=gen_dir,
                model_name=comfyui_model,
                width=comfyui_w,
                height=comfyui_h,
                steps=comfyui_steps,
                cfg=comfyui_cfg,
                num_images=req.numImages,
            )

        elif provider == "local":
            # Ollama image gen  
            from backend.tools.generators.tts_generator import LocalTTSGenerator
            raise RuntimeError(
                "Ollama image generation is not yet stable.\n"
                "Please use ComfyUI for local image generation."
            )

        else:
            # Default: Google Gemini
            results = GeminiImageGenerator().generate(
                prompt=req.prompt, num_images=req.numImages, output_dir=gen_dir
            )

    except ConnectionError as e:
        raise HTTPException(status_code=503, detail={
            "error": "comfyui_unavailable",
            "message": str(e),
            "action": "Start ComfyUI: python main.py --listen 127.0.0.1 --port 8188",
        })
    except PermissionError as e:
        raise HTTPException(status_code=402, detail={
            "error": "quota_exceeded",
            "message": str(e),
            "action": "Enable billing at https://aistudio.google.com",
        })
    except EnvironmentError as e:
        raise HTTPException(status_code=503, detail={"error": "config_error", "message": str(e)})
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail={"error": "generation_failed", "message": str(e)})

    if not results:
        raise HTTPException(status_code=500, detail={
            "error": "no_images",
            "message": f"No images returned by {provider} generator. Check server logs.",
        })

    imported = []
    for r in results:
        info = _import_file(r["filepath"])
        imported.append({"assetId": info["assetId"], "filename": info["filename"], "title": r["title"]})
    from backend.events import notify; notify("library")
    return {"assets": imported}


#   TTS Generation  

@router.post("/media/generate-tts")
def generate_tts_endpoint(req: GenerateTTSRequest):
     
    provider = _cfg.get("generators.tts_provider", "google")
    ollama_url = _cfg.get("generators.ollama_url", "http://localhost:11434")
    local_model = _cfg.get("generators.tts_local_model", "kokoro")
    speed = float(_cfg.get("generators.tts_kokoro_speed", 1.0))

    gen_dir = _resolve_download_dir(subdir="tts")
    generator = get_tts_generator(provider=provider, ollama_url=ollama_url)

    try:
        if provider == "kokoro":
            # voice default 
            kokoro_voice = req.voice or _cfg.get("generators.tts_kokoro_voice", "af_heart")
            result = generator.generate(
                text=req.text, output_dir=gen_dir,
                voice=kokoro_voice, speed=speed,
            )
        elif provider == "local":
            result = generator.generate(text=req.text, output_dir=gen_dir, model=local_model)
        else:
            # Google Gemini
            google_voice = req.voice or _cfg.get("generators.tts_google_voice", "Kore")
            result = generator.generate(text=req.text, output_dir=gen_dir, voice=google_voice)

    except PermissionError as e:
        raise HTTPException(status_code=402, detail={
            "error": "quota_exceeded",
            "message": str(e),
            "action": "Enable billing at https://aistudio.google.com",
        })
    except ImportError as e:
        raise HTTPException(status_code=503, detail={
            "error": "kokoro_not_installed",
            "message": str(e),
            "action": "Run: pip install kokoro soundfile (Windows: also install espeak-ng)",
        })
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail={
            "error": "ollama_unavailable",
            "message": str(e),
            "action": "Start Ollama with: ollama serve",
        })
    except EnvironmentError as e:
        raise HTTPException(status_code=503, detail={"error": "config_error", "message": str(e)})
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail={"error": "tts_failed", "message": str(e)})

    info = _import_file(result["filepath"])
    from backend.events import notify; notify("library")
    return {
        "assetId": info["assetId"],
        "filename": info["filename"],
        "title": result["title"],
        "voice": result.get("voice", ""),
        "duration_s": result.get("duration_s", 0),
    }


#   Video Generation  

@router.post("/media/generate-video")
def generate_video_endpoint(req: GenerateVideoRequest):
     
    provider = _cfg.get("generators.video_provider", "google")
    ollama_url = _cfg.get("generators.ollama_url", "http://localhost:11434")
    local_model = _cfg.get("generators.video_local_model", "wan2.1")

    gen_dir = _resolve_download_dir(subdir="generations/video")
    generator = get_video_generator(provider=provider, ollama_url=ollama_url)

    try:
        if provider == "local":
            result = generator.generate(
                prompt=req.prompt,
                output_dir=gen_dir,
                model=local_model,
                duration_seconds=req.durationSeconds,
            )
        else:
            result = generator.generate(
                prompt=req.prompt,
                output_dir=gen_dir,
                duration_seconds=req.durationSeconds,
                aspect_ratio=req.aspectRatio,
            )

    except PermissionError as e:
        raise HTTPException(status_code=402, detail={
            "error": "quota_exceeded",
            "message": str(e),
            "action": "Enable billing at https://aistudio.google.com",
        })
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail={
            "error": "ollama_unavailable",
            "message": str(e),
            "action": "Start Ollama with: ollama serve",
        })
    except EnvironmentError as e:
        raise HTTPException(status_code=503, detail={"error": "config_error", "message": str(e)})
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail={"error": "video_failed", "message": str(e)})

    info = _import_file(result["filepath"])
    from backend.events import notify; notify("library")
    return {"assetId": info["assetId"], "filename": info["filename"], "title": result["title"]}


 



@router.get("/media/tts-voices")
def get_tts_voices():
    """Return available TTS voices for both Gemini and Kokoro providers."""
    from backend.tools.generators.tts_generator import KOKORO_VOICES
    provider = _cfg.get("generators.tts_provider", "google")
    return {
        "provider": provider,
        "voices": GEMINI_VOICES,       # Gemini voices  
        "gemini_voices": GEMINI_VOICES,
        "kokoro_voices": KOKORO_VOICES,
        "default_voice": "af_heart" if provider == "kokoro" else "Kore",
    }
