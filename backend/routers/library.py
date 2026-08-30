import os
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.state import engine, _library
from backend.media.asset.mediaAsset import MediaAsset
from backend.worker.worker_bus import bus as _worker_bus
from backend.tools import YtdlpDownloader, ImageDownloader, GeminiImageGenerator

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
            return {"assetId": a.assetId, "filename": os.path.basename(a.filepath),
                    "filepath": a.filepath, "type": a.mediaType, "hasAudio": a.hasAudio}
    assetId = str(uuid.uuid4())
    asset = MediaAsset(filepath=filepath, assetId=assetId)
    _library[assetId] = asset
    if asset.hasAudio:
        try:
            _worker_bus.submit_waveform(assetId, filepath)
        except Exception:
            pass
    return {"assetId": assetId, "filename": os.path.basename(filepath),
            "filepath": filepath, "type": asset.mediaType, "hasAudio": asset.hasAudio}


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
        try:
            port = int(os.environ.get("BACKEND_PORT", 8000))
            _worker_bus.submit_index_video(result["assetId"], req.filepath, port=port)
        except Exception as _e:
            print(f"[Library] VideoSemantic submit error (non-fatal): {_e}", flush=True)

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
    generator = GeminiImageGenerator()
    gen_dir = _resolve_download_dir(subdir="generations")
    results = generator.generate(prompt=req.prompt, num_images=req.numImages, output_dir=gen_dir)
    imported = []
    for r in results:
        info = _import_file(r["filepath"])
        imported.append({"assetId": info["assetId"], "filename": info["filename"], "title": r["title"]})
    from backend.events import notify; notify("library")
    return {"assets": imported}
