from fastapi import APIRouter
from backend.state import engine

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/project")
def getProject():
    if engine.project is None:
        return {"error": "No active project"}
    return engine.project.toDict()


@router.post("/project/new")
def newProject(name: str = "Untitled Project",
               width: int = 1920, height: int = 1080,
               fps: float = 30.0, mediaDownloadPath: str = ""):
    from backend.timeline.tracks.videoTrack import VideoTrack
    from backend.timeline.tracks.audioTrack import AudioTrack
    
    engine.newProject(name=name, width=width, height=height, fps=fps)
    
    # Initialize with default tracks
    tl = engine.activeTimeline
    if tl:
        for track_name in ["Video 1", "Video 2", "Video 3"]:
            tl.addTrack(VideoTrack(track_name))
        tl.addTrack(AudioTrack("Audio 1"))
        
    if mediaDownloadPath:
        engine.project.settings.mediaDownloadPath = mediaDownloadPath
    return {"status": "ok", "project": engine.project.toDict()}


from pydantic import BaseModel
from fastapi import HTTPException
import os
import json as _json
from backend.state import _library
from backend.worker.worker_bus import bus as _worker_bus
from backend.media.asset.mediaAsset import MediaAsset


class SaveRequest(BaseModel):
    filepath: str


class LoadRequest(BaseModel):
    filepath: str


@router.post("/project/save")
def saveProject(req: SaveRequest):
    from pathlib import Path
    from backend.media.asset.webCompAsset import WebCompAsset
    from backend.media.asset.baseAsset import MediaType
    if engine is None or engine.project is None:
        raise HTTPException(503, "No active project")
    tl = engine.activeTimeline
    proj_dict = engine.project.toDict()
    if tl is not None:
        proj_dict["timeline"] = tl.toDict()

    #   Regular media assets (video / audio / image)  
    proj_dict["assets"] = {
        asset_id: asset.filepath
        for asset_id, asset in _library.items()
        if getattr(asset, "filepath", None) and os.path.exists(asset.filepath)
    }

    #   WebComp assets    
    # Saved as full dicts  
    proj_dict["webcompAssets"] = [
        asset.toDict()
        for asset in _library.values()
        if getattr(asset, "mediaType", None) == MediaType.webcomp
    ]

    # Persist the project-level media download path
    proj_dict["mediaDownloadPath"] = getattr(
        getattr(engine.project, "settings", None), "mediaDownloadPath", ""
    ) or ""

    path = Path(req.filepath)
    if not path.suffix:
        path = path.with_suffix(".fade")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json.dumps(proj_dict, indent=2), encoding="utf-8")
    engine.project.filePath = str(path)
    engine.project.isDirty  = False
    wc_count = len(proj_dict["webcompAssets"])
    print(f"[Project] Saved -> {path}  ({len(proj_dict['assets'])} media, {wc_count} webcomp assets)", flush=True)
    return {"status": "ok", "filepath": str(path)}



@router.post("/project/load")
def loadProject(req: LoadRequest):
    from pathlib import Path
    from backend.timeline.timeline import Timeline
    from backend.media.asset.webCompAsset import WebCompAsset
    path = Path(req.filepath)
    if not path.exists():
        raise HTTPException(404, f"Project file not found: {path}")
    data = _json.loads(path.read_text(encoding="utf-8"))
    proj = engine.loadProject(str(path))
    proj.filePath = str(path)
    tl_data = data.get("timeline")
    if tl_data:
        tl = Timeline.fromDict(tl_data)
        for track in tl.tracks:
            for clip in track.clips:
                if hasattr(clip, "setScheduler") and engine.scheduler:
                    clip.setScheduler(engine.scheduler, proj.fps)
        proj.timelines = [tl]
    else:
        tl = engine.activeTimeline

    # Restore project-level download path
    saved_dl_path = data.get("mediaDownloadPath", "")
    if saved_dl_path and hasattr(proj, "settings") and proj.settings is not None:
        proj.settings.mediaDownloadPath = saved_dl_path

    _library.clear()
    missing: list[str] = []
    offline_assets: list[dict] = []

    # Restore regular media assets  
    def _register(asset_id: str, filepath: str) -> bool:
        if not asset_id or not filepath or asset_id in _library:
            return False
        if not os.path.exists(filepath):
            missing.append(filepath)
            return False
        asset = MediaAsset(filepath=filepath, assetId=asset_id)
        _library[asset_id] = asset
        if asset.hasAudio:
            try:
                _worker_bus.submit_waveform(asset_id, filepath)
            except Exception:
                pass
        return True

    for asset_id, filepath in data.get("assets", {}).items():
        _register(asset_id, filepath)

    # Restore WebComp assets  
    wc_restored = 0
    wc_offline  = 0
    for wc_data in data.get("webcompAssets", []):
        asset_id   = wc_data.get("assetId", "")
        folder     = wc_data.get("folderPath", "")
        if not asset_id:
            continue
        if asset_id in _library:
            continue   
        if not os.path.isdir(folder):
            print(f"[Project] WARNING: WebComp folder missing: {folder}", flush=True)
            wc_offline += 1
            offline_assets.append({
                "assetId": asset_id,
                "clipId": "",
                "filename_hint": wc_data.get("name", asset_id[:12]),
            })
            continue
        asset = WebCompAsset.fromDict(wc_data)
        asset._loadMeta()   # refresh params  
        _library[asset_id] = asset
        wc_restored += 1
        print(f"[Project] WebComp restored: {asset.name} ({asset_id[-8:]})", flush=True)

    #   Scan timeline for any media clips not caught above  
    if tl:
        for track in tl.tracks:
            for clip in track.clips:
                # Skip webcomp clips 
                if getattr(clip, "webcompId", None):
                    continue
                aid = getattr(clip, "assetId", "")
                fp  = getattr(clip, "filepath", "")
                if not aid:
                    continue
                registered = _register(aid, fp)
                if not registered and aid not in _library:
                    import pathlib
                    hint = pathlib.Path(fp).name if fp else aid[:12]
                    offline_assets.append({
                        "assetId": aid,
                        "clipId": getattr(clip, "clipId", ""),
                        "filename_hint": hint,
                    })

    for fp in missing:
        print(f"[Project] WARNING: asset file missing: {fp}", flush=True)
    if offline_assets:
        print(f"[Project] {len(offline_assets)} asset(s) offline: "
              + ", ".join(a['filename_hint'] for a in offline_assets), flush=True)
    print(f"[Project] Loaded <- {path}  "
          f"({len(_library) - wc_restored} media + {wc_restored} webcomp restored, "
          f"{len(offline_assets)} offline)", flush=True)
    return {
        "status": "ok",
        "project": proj.toDict(),
        "timeline": tl.toDict() if tl else {},
        "missing_assets": offline_assets,
    }


class SettingsPayload(BaseModel):
    cacheMaxMB: int | None = None
    previewScale: float | None = None
    jpegQuality: int | None = None
    prefetchRadius: int | None = None
    batchSize: int | None = None
    decoderMode: str | None = None


def _get_settings() -> dict:
    import backend.compositor.compositor as _comp
    from backend.media.scheduler.decodeScheduler import DecodeScheduler
    from backend.media.cache.frameCache import FrameCache
    from backend.media.decoder.videoDecoder import _DECODER_MODE
    cache_mb = round(engine.scheduler._frameCache._maxBytes / (1024**2)) if engine.scheduler else 512
    scale = engine.getPreviewScale()
    quality = getattr(engine.compositor, '_jpegQuality', 85) if engine.compositor else 85
    return {
        "cacheMaxMB": cache_mb,
        "cacheUsedMB": round(engine.scheduler._frameCache.usedMB, 1) if engine.scheduler else 0,
        "cacheFrames": engine.scheduler._frameCache.entryCount if engine.scheduler else 0,
        "cacheMaxFrames": FrameCache.MAX_FRAMES,
        "previewScale": scale,
        "jpegQuality": quality,
        "prefetchRadius": _comp.PREFETCH_RADIUS,
        "batchSize": DecodeScheduler.BATCH_SIZE,
        "decoderMode": _DECODER_MODE,
        "hwMode": __import__('backend.media.decoder.ffmpegDecoder', fromlist=['_HwProbe'])._HwProbe._result or "pending",
    }


@router.get("/settings")
def getSettings():
    return _get_settings()


@router.post("/settings")
def postSettings(payload: SettingsPayload):
    import backend.compositor.compositor as _comp
    from backend.media.scheduler.decodeScheduler import DecodeScheduler
    if payload.cacheMaxMB is not None:
        mb = max(64, min(4096, payload.cacheMaxMB))
        if engine.scheduler:
            engine.scheduler._frameCache._maxBytes = mb * 1024 * 1024
    if payload.previewScale is not None:
        engine.setPreviewScale(payload.previewScale)
        from backend.media.decoder.ffmpegDecoder import _HwProbe
        _HwProbe.reset()
    if payload.jpegQuality is not None:
        q = max(1, min(100, payload.jpegQuality))
        if engine.compositor:
            engine.compositor._jpegQuality = q
    if payload.prefetchRadius is not None:
        _comp.PREFETCH_RADIUS = max(10, min(240, payload.prefetchRadius))
    if payload.batchSize is not None:
        DecodeScheduler.BATCH_SIZE = max(10, min(120, payload.batchSize))
    if payload.decoderMode is not None and payload.decoderMode in ("auto", "pyav", "ffmpeg"):
        import backend.media.decoder.videoDecoder as _vd
        _vd._DECODER_MODE = payload.decoderMode
    return _get_settings()
