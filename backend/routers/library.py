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


def _import_file(filepath: str) -> dict:
    """Register a file into _library, deduplicating by path. Returns asset dict."""
    for a in _library.values():
        if a.filepath == filepath:
            if a.hasAudio:
                try:
                    _worker_bus.submit_waveform(a.assetId, a.filepath)
                except Exception:
                    pass
            mtype = a.mediaType.value if hasattr(a.mediaType, 'value') else str(a.mediaType)
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


@router.post("/library/import")
def importAsset(req: ImportRequest):
    if not os.path.exists(req.filepath):
        raise HTTPException(404, f"File not found: {req.filepath}")
    result = _import_file(req.filepath)
    from backend.events import notify; notify("library")

    if result.get("type") == "video":
        fname = os.path.basename(req.filepath)
        print(f"[Library] Queueing VideoSemantic index for {result['assetId'][:8]} ({fname})", flush=True)
        try:
            port = int(os.environ.get("BACKEND_PORT", 8000))
            from backend.ai.VideoSemantic.indexer import get_db_path as _get_db
            _worker_bus.submit_index_video(result["assetId"], req.filepath,
                                           port=port, db_path=_get_db())
            print(f"[Library] ✓ index_video submitted to worker bus", flush=True)
            
            try:
                from backend.routers.jobs import register_asset_job as _rj
                _rj("video_index", result["assetId"],
                    f"Indexing: {fname}",
                    message="Running Vision + Whisper…")
            except Exception:
                pass
        except Exception as _e:
            print(f"[Library] ✗ VideoSemantic submit error (non-fatal): {_e}", flush=True)

    elif result.get("type") == "image":
        fname = os.path.basename(req.filepath)
        print(f"[Library] Queueing ImageSemantic index for {result['assetId'][:8]} ({fname})", flush=True)
        try:
            from backend.ai.VideoSemantic.indexer import get_db_path as _get_db
            _worker_bus.submit_index_image(result["assetId"], req.filepath, db_path=_get_db())
            print(f"[Library] ✓ index_image submitted to worker bus", flush=True)
            try:
                from backend.routers.jobs import register_asset_job as _rj
                _rj("image_index", result["assetId"],
                    f"Indexing: {fname}",
                    message="Describing image…")
            except Exception:
                pass
        except Exception as _e:
            print(f"[Library] ✗ ImageSemantic submit error (non-fatal): {_e}", flush=True)

    else:
        print(f"[Library] Skipping index — type={result.get('type')} ({os.path.basename(req.filepath)})", flush=True)

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
            # Ollama image gen (experimental)
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
    """
    Generate speech audio from text.
    Provider (google/local) is read from settings/generators.
    Returns the imported audio asset.
    """
    provider = _cfg.get("generators.tts_provider", "google")
    ollama_url = _cfg.get("generators.ollama_url", "http://localhost:11434")
    local_model = _cfg.get("generators.tts_local_model", "kokoro")
    voice = req.voice or _cfg.get("generators.tts_google_voice", "Kore")

    gen_dir = _resolve_download_dir(subdir="tts")
    generator = get_tts_generator(provider=provider, ollama_url=ollama_url)

    try:
        if provider == "local":
            result = generator.generate(text=req.text, output_dir=gen_dir, model=local_model)
        else:
            result = generator.generate(text=req.text, output_dir=gen_dir, voice=voice)

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
        raise HTTPException(status_code=500, detail={"error": "tts_failed", "message": str(e)})

    info = _import_file(result["filepath"])
    from backend.events import notify; notify("library")
    return {"assetId": info["assetId"], "filename": info["filename"], "title": result["title"]}


#   Video Generation  

@router.post("/media/generate-video")
def generate_video_endpoint(req: GenerateVideoRequest):
    """
    Generate a video from a text prompt.
    Provider (google/local) is read from settings/generators.
    Returns the imported video asset.
    """
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
    """Return available Gemini TTS voices."""
    return {"voices": GEMINI_VOICES}
