from fastapi import APIRouter
from backend.state import engine, _library, _clipTrackMap
from backend.worker.worker_bus import bus as _worker_bus
from backend.media.asset.mediaAsset import MediaAsset

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
import shutil
import json as _json


class SaveRequest(BaseModel):
    
    folderPath: str | None = None
    filepath: str | None = None


class LoadRequest(BaseModel):
    filepath: str   # may be a folder or a .fade file


# Folder structure helpers  

def _project_folder(req: SaveRequest) -> "Path":
    from pathlib import Path
    if req.folderPath:
        return Path(req.folderPath)
    # Legacy: derive folder from filepath stem
    p = Path(req.filepath)
    if p.suffix == ".fade":
        return p.parent / p.stem
    return p


def _migrate_chroma_to_project(proj_folder: "Path", asset_ids: set[str]) -> int:
     
    from pathlib import Path
    from backend.ai.VideoSemantic.indexer import (
        _col, _img_col, switch_db, get_db_path
    )
    import chromadb

    dest_path = str(proj_folder / "chroma_db")
    src_path  = get_db_path()

    if src_path != dest_path:
        
         
        dest_client = chromadb.PersistentClient(path=dest_path)
        dest_vid = dest_client.get_or_create_collection(
            name="video_segments", metadata={"hnsw:space": "cosine"}
        )
        dest_img = dest_client.get_or_create_collection(
            name="image_assets", metadata={"hnsw:space": "cosine"}
        )
        total = 0
        for aid in asset_ids:
            try:
                res = _col.get(where={"assetId": aid},
                               include=["embeddings", "documents", "metadatas"])
                if res["ids"]:
                    dest_vid.upsert(ids=res["ids"], embeddings=res["embeddings"],
                                    documents=res["documents"], metadatas=res["metadatas"])
                    total += len(res["ids"])
                    print(f"[Project] ChromaDB migrated video: {len(res['ids'])} chunks for {aid[:8]}", flush=True)
            except Exception as e:
                print(f"[Project] ChromaDB video migrate skip {aid[:8]}: {e}", flush=True)
            try:
                res2 = _img_col.get(where={"assetId": aid},
                                    include=["embeddings", "documents", "metadatas"])
                if res2["ids"]:
                    dest_img.upsert(ids=res2["ids"], embeddings=res2["embeddings"],
                                    documents=res2["documents"], metadatas=res2["metadatas"])
                    total += len(res2["ids"])
                    print(f"[Project] ChromaDB migrated image: {len(res2['ids'])} for {aid[:8]}", flush=True)
            except Exception as e:
                print(f"[Project] ChromaDB image migrate skip {aid[:8]}: {e}", flush=True)
        del dest_client    
        switch_db(dest_path)
        print(f"[Project] ChromaDB migrated scratch→project: {total} entries", flush=True)
    else:
         
        switch_db(dest_path)
         
        from backend.ai.VideoSemantic.indexer import _col as _fresh_col, _img_col as _fresh_img
        total = 0
        for aid in asset_ids:
            try:
                total += len(_fresh_col.get(where={"assetId": aid}, limit=100)["ids"])
            except Exception:
                pass
            try:
                total += len(_fresh_img.get(where={"assetId": aid}, limit=1)["ids"])
            except Exception:
                pass
        print(f"[Project] ChromaDB on project DB: {total} entries found", flush=True)

    return total


def _copy_webcomp_to_project(wc_asset, proj_folder: "Path") -> str:
     
    from pathlib import Path
    src = Path(wc_asset.folderPath)
    if not src.is_dir():
        return wc_asset.folderPath   # already missing, leave as-is

    dest_root = proj_folder / "assets" / "webcomps" / src.name
    if dest_root.resolve() == src.resolve():
        return str(src)  # already inside the project folder

    if dest_root.exists():
        shutil.rmtree(dest_root)
    shutil.copytree(src, dest_root)
    print(f"[Project] WebComp copied: {src.name} → {dest_root}", flush=True)
    return str(dest_root)


#   Save  

@router.post("/project/save")
def saveProject(req: SaveRequest):
    from pathlib import Path
    from backend.media.asset.webCompAsset import WebCompAsset
    from backend.media.asset.baseAsset import MediaType

    if engine is None or engine.project is None:
        raise HTTPException(503, "No active project")

    proj_folder = _project_folder(req)
    proj_folder.mkdir(parents=True, exist_ok=True)
    anchor_path = proj_folder / "project.fade"

    tl = engine.activeTimeline
    proj_dict = engine.project.toDict()
    if tl is not None:
        proj_dict["timeline"] = tl.toDict()

    #   Regular media assets 
    media_assets = {
        asset_id: asset.filepath
        for asset_id, asset in _library.items()
        if getattr(asset, "filepath", None) and os.path.exists(asset.filepath)
        and getattr(asset, "mediaType", None) != MediaType.webcomp
    }
    proj_dict["assets"] = media_assets

    # ── Safety guard: don't overwrite a real project with empty in-memory state ──
    # This prevents the crash-restart-save race where the backend restarts with
    # no project loaded (0 clips, 0 media) and then Ctrl+S overwrites good data.
    clip_count_now = 0
    if tl:
        for track in tl.tracks:
            clip_count_now += len(track.clips)
    if clip_count_now == 0 and len(media_assets) == 0 and anchor_path.exists():
        try:
            import json as _json_check
            existing = _json_check.loads(anchor_path.read_text(encoding="utf-8"))
            existing_clips = sum(len(t.get("clips", [])) for t in existing.get("timeline", {}).get("tracks", []))
            existing_media = len(existing.get("assets", {}))
            if existing_clips > 0 or existing_media > 0:
                print(
                    f"[Project] ⚠ Save blocked — backend has empty state "
                    f"but disk has {existing_clips} clips / {existing_media} assets. "
                    f"Reload the project first.",
                    flush=True,
                )
                raise HTTPException(
                    409,
                    f"Save blocked: backend state is empty (0 clips, 0 assets) "
                    f"but '{anchor_path.name}' on disk has {existing_clips} clips "
                    f"and {existing_media} assets. Reload the project first to avoid data loss."
                )
        except HTTPException:
            raise
        except Exception:
            pass  # Can't read disk — allow save


    
    audio_dest = proj_folder / "assets" / "audio"
    _AUDIO_EXTS = {".wav", ".mp3", ".aac", ".flac", ".ogg", ".m4a"}
    for asset_id, src_path in list(media_assets.items()):
        src = Path(src_path)
        if src.suffix.lower() not in _AUDIO_EXTS:
            continue
        try:
            src_resolved = src.resolve()
            proj_resolved = proj_folder.resolve()
            # Only copy if outside the project folder
            src_resolved.relative_to(proj_resolved)
        except ValueError:
            # File is outside the project — copy it in
            audio_dest.mkdir(parents=True, exist_ok=True)
            dest = audio_dest / src.name
            if not dest.exists() or dest.stat().st_size != src.stat().st_size:
                shutil.copy2(src, dest)
                print(f"[Project] Audio copied: {src.name} → assets/audio/", flush=True)
            new_path = str(dest)
            media_assets[asset_id] = new_path
            # Update in-memory  
            if asset_id in _library:
                _library[asset_id].filepath = new_path

    proj_dict["assets"] = media_assets   

    #   WebComp assets 
    wc_dicts = []
    for asset in _library.values():
        if getattr(asset, "mediaType", None) != MediaType.webcomp:
            continue
        new_folder = _copy_webcomp_to_project(asset, proj_folder)
        d = asset.toDict()
        d["folderPath"] = new_folder
        wc_dicts.append(d)
    proj_dict["webcompAssets"] = wc_dicts

    #   Settings  
    proj_dict["mediaDownloadPath"] = getattr(
        getattr(engine.project, "settings", None), "mediaDownloadPath", ""
    ) or ""
    proj_dict["projectFolder"] = str(proj_folder)

    #   ChromaDB  
    all_asset_ids = set(media_assets.keys()) | {d.get("assetId", "") for d in wc_dicts}
    from backend.worker.worker_bus import bus as _bus
    if _bus.is_indexing_active():
        # Sandbox subprocess has exclusive write access to project ChromaDB right now.
        # Reading/healing from the main process concurrently causes a Rust HNSW
        # segfault → backend.exe exits with code 1. Skip safely and use last count.
        chroma_chunks = proj_dict.get("chromaDbChunks", 0)
        print(f"[Project] ChromaDB access deferred (indexing active) — cached count: {chroma_chunks}", flush=True)
    else:
        chroma_chunks = _migrate_chroma_to_project(proj_folder, all_asset_ids)
    proj_dict["chromaDbBundled"] = True
    proj_dict["chromaDbChunks"] = chroma_chunks

    # Verify clip  
    clip_count = 0
    effect_count = 0
    if tl:
        for track in tl.tracks:
            clip_count += len(track.clips)
            for clip in track.clips:
                effect_count += len(getattr(clip, "effects", []))  # BaseClip.effects

    anchor_path.write_text(_json.dumps(proj_dict, indent=2), encoding="utf-8")
    engine.project.filePath = str(anchor_path)
    engine.project.isDirty = False

    print(
        f"[Project] ✓ Saved → {anchor_path}\n"
        f"  Clips: {clip_count}  Effects: {effect_count}  "
        f"Media: {len(media_assets)}  WebComps: {len(wc_dicts)}  "
        f"ChromaDB chunks: {chroma_chunks}",
        flush=True,
    )
    return {
        "status": "ok",
        "filepath": str(anchor_path),
        "folderPath": str(proj_folder),
        "clips": clip_count,
        "effects": effect_count,
        "mediaAssets": len(media_assets),
        "webcomps": len(wc_dicts),
        "chromaDbChunks": chroma_chunks,
    }


#   Load  

@router.post("/project/load")
def loadProject(req: LoadRequest):
    from pathlib import Path
    from backend.timeline.timeline import Timeline
    from backend.media.asset.webCompAsset import WebCompAsset

    given = Path(req.filepath)

    # Accept either a folder  
    if given.is_dir():
        anchor_path = given / "project.fade"
    else:
        anchor_path = given

    if not anchor_path.exists():
        raise HTTPException(404, f"Project file not found: {anchor_path}")

    data = _json.loads(anchor_path.read_text(encoding="utf-8"))
    proj_folder = Path(data.get("projectFolder", str(anchor_path.parent)))

    proj = engine.loadProject(str(anchor_path))
    proj.filePath = str(anchor_path)

    tl_data = data.get("timeline")
    if tl_data:
        
        _AUDIO_EXTS = (".wav", ".mp3", ".aac", ".flac", ".ogg", ".m4a")
        scrubbed = 0
        for track_d in tl_data.get("tracks", []):
            if track_d.get("type") != "video":
                continue
            clean_clips = []
            for clip_d in track_d.get("clips", []):
                clip_type = clip_d.get("type") or clip_d.get("clipType", "")
                fp = clip_d.get("filepath", "")
                if clip_type == "video" and fp.lower().endswith(_AUDIO_EXTS):
                    scrubbed += 1
                    print(f"[Project] Scrubbed ghost video clip on audio file: {os.path.basename(fp)}", flush=True)
                    continue
                clean_clips.append(clip_d)
            track_d["clips"] = clean_clips
        if scrubbed:
            print(f"[Project] Removed {scrubbed} ghost video clip(s) pointing to audio files.", flush=True)

        tl = Timeline.fromDict(tl_data)
        for ti, track in enumerate(tl.tracks):
            for clip in track.clips:
                # Wire decoder scheduler for video clips
                if hasattr(clip, "setScheduler") and engine.scheduler:
                    clip.setScheduler(engine.scheduler, proj.fps if proj else 30.0)
                # Register the clip asset  
                if hasattr(clip, "assetId") and clip.assetId and engine.scheduler:
                    asset = None  
                    _clipTrackMap[clip.clipId] = ti
        proj.timelines = [tl]
    else:
        tl = engine.activeTimeline

    saved_dl_path = data.get("mediaDownloadPath", "")
    if saved_dl_path and hasattr(proj, "settings") and proj.settings is not None:
        proj.settings.mediaDownloadPath = saved_dl_path

    #   Point ChromaDB at project-local DB  
    proj_chroma = proj_folder / "chroma_db"
    if data.get("chromaDbBundled") and proj_chroma.is_dir():
        try:
            from backend.ai.VideoSemantic.indexer import switch_db
            switch_db(str(proj_chroma))
            print(f"[Project] ChromaDB switched to project DB: {proj_chroma}", flush=True)
        except Exception as e:
            print(f"[Project] ChromaDB switch failed (non-fatal): {e}", flush=True)

    _library.clear()
    missing: list[str] = []
    offline_assets: list[dict] = []

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

    #   Restore regular media assets  
    for asset_id, filepath in data.get("assets", {}).items():
        _register(asset_id, filepath)

    #   Restore WebComp assets 
    wc_restored = 0
    wc_offline = 0
    for wc_data in data.get("webcompAssets", []):
        asset_id = wc_data.get("assetId", "")
        folder = wc_data.get("folderPath", "")
        if not asset_id:
            continue
        if asset_id in _library:
            continue

        
        if folder and not os.path.isdir(folder):
            # Try relative to project folder
            rel = proj_folder / "assets" / "webcomps" / Path(folder).name
            if rel.is_dir():
                folder = str(rel)
                wc_data = dict(wc_data)
                wc_data["folderPath"] = folder

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
        asset._loadMeta()
        _library[asset_id] = asset
        wc_restored += 1
        print(f"[Project] WebComp restored: {asset.name} ({asset_id[-8:]})", flush=True)

    # Scan timeline for any unlisted clips  
    if tl:
        for track in tl.tracks:
            for clip in track.clips:
                if getattr(clip, "webcompId", None):
                    continue
                aid = getattr(clip, "assetId", "")
                fp = getattr(clip, "filepath", "")
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

    #   Wire decoder scheduler  
    if tl and engine.scheduler:
        for track in tl.tracks:
            for clip in track.clips:
                aid = getattr(clip, "assetId", "")
                if aid and aid in _library:
                    try:
                        engine.scheduler.registerClip(clip.clipId, _library[aid])
                    except Exception as e:
                        print(f"[Project] scheduler.registerClip failed for {aid[:8]}: {e}", flush=True)

    #   Check and submit 
    try:
        from backend.ai.VideoSemantic.indexer import is_asset_indexed, get_db_path
        from backend.media.asset.baseAsset import MediaType
        port    = int(os.environ.get("BACKEND_PORT", 8000))
        db_path = get_db_path()   # project DB 
        indexed_count = 0
        queued_count  = 0
        for aid, asset in list(_library.items()):
            mt = getattr(asset, "mediaType", None)
            if mt == MediaType.webcomp:
                continue
            fp = getattr(asset, "filepath", "")
            if not fp or not os.path.exists(fp):
                continue
            if is_asset_indexed(aid):
                indexed_count += 1
                print(f"[Project] ✓ Already indexed: {aid[:8]} ({os.path.basename(fp)})", flush=True)
            else:
                if mt == MediaType.image:
                    _worker_bus.submit_index_image(aid, fp, db_path=db_path)
                    print(f"[Project] ↑ Queued image index: {aid[:8]} ({os.path.basename(fp)})", flush=True)
                    queued_count += 1
                elif mt == MediaType.audio or os.path.splitext(fp)[1].lower() in {".wav", ".mp3", ".aac", ".flac", ".ogg", ".m4a"}:
                    # Audio-only file  
                    from backend.worker.transcript_status import is_done as _ts_done
                    if not _ts_done(aid):
                        _worker_bus.submit_transcribe_audio(aid, fp, db_path=db_path)
                        print(f"[Project] ↑ Queued audio transcript: {aid[:8]} ({os.path.basename(fp)})", flush=True)
                        queued_count += 1
                    else:
                        indexed_count += 1
                        print(f"[Project] ✓ Already transcribed: {aid[:8]} ({os.path.basename(fp)})", flush=True)
                else:
                    _worker_bus.submit_index_video(aid, fp, port=port, db_path=db_path)
                    print(f"[Project] ↑ Queued video index: {aid[:8]} ({os.path.basename(fp)})", flush=True)
                    queued_count += 1
        print(f"[Project] Semantic index: {indexed_count} already indexed, {queued_count} queued", flush=True)
    except Exception as _ie:
        print(f"[Project] Semantic index check failed (non-fatal): {_ie}", flush=True)

    #   Count clips + effects
    clip_count = sum(len(t.clips) for t in tl.tracks) if tl else 0
    effect_count = sum(
        len(getattr(c, "effects", []))
        for t in tl.tracks for c in t.clips
    ) if tl else 0

    for fp in missing:
        print(f"[Project] WARNING: asset file missing: {fp}", flush=True)
    if offline_assets:
        print(f"[Project] {len(offline_assets)} asset(s) offline: "
              + ", ".join(a["filename_hint"] for a in offline_assets), flush=True)

    print(
        f"[Project] ✓ Loaded ← {anchor_path}\n"
        f"  Clips: {clip_count}  Effects: {effect_count}  "
        f"Media: {len(_library) - wc_restored}  WebComps: {wc_restored}  "
        f"Offline: {len(offline_assets)}",
        flush=True,
    )

    # Notify frontend  
    try:
        from backend.events import notify
        notify("project")
    except Exception:
        pass

    return {
        "status": "ok",
        "project": proj.toDict(),
        "timeline": tl.toDict() if tl else {},
        "missing_assets": offline_assets,
        "clips": clip_count,
        "effects": effect_count,
        "chromaDbBundled": data.get("chromaDbBundled", False),
    }


# Performance Settings  

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


# AI Indexing Settings    

from backend.config.global_config import cfg as _cfg

class AiSettingsPayload(BaseModel):
    visionModel: str | None = None
    frameInterval: float | None = None
    whisperBackend: str | None = None
    whisperModel: str | None = None
    maxConcurrentIndex: int | None = None
    indexProvider: str | None = None      # 'ollama' | 'gemini'
    indexGeminiModel: str | None = None   # e.g. 'gemini-1.5-flash'


def _get_ai_settings() -> dict:
    available: list[str] = []
    try:
        import ollama
        available = [m.model for m in ollama.list().models]
    except Exception:
        pass

    from backend.worker.worker_bus import bus as _bus
    queue_info = _bus.get_index_queue_info()

    return {
        "visionModel": _cfg.get("ai.vision_model", "moondream:latest"),
        "frameInterval": _cfg.get("ai.frame_interval", 4.0),
        "whisperBackend": _cfg.get("ai.whisper_backend", "faster"),
        "whisperModel": _cfg.get("ai.whisper_model", "small"),
        "maxConcurrentIndex": _cfg.get("ai.max_concurrent_index", 2),
        "availableModels": available,
        "indexQueue": queue_info,
        "indexProvider": _cfg.get("ai.index_provider", "ollama"),
        "indexGeminiModel": _cfg.get("ai.index_gemini_model", "gemini-1.5-flash"),
    }


@router.get("/settings/ai")
def getAiSettings():
    return _get_ai_settings()


@router.post("/settings/ai")
def postAiSettings(payload: AiSettingsPayload):
    if payload.visionModel is not None:
        _cfg.set("ai.vision_model", payload.visionModel.strip())
    if payload.frameInterval is not None:
        _cfg.set("ai.frame_interval", max(1.0, min(30.0, payload.frameInterval)))
    if payload.whisperBackend is not None and payload.whisperBackend in ("faster", "openai"):
        _cfg.set("ai.whisper_backend", payload.whisperBackend)
        from backend.ai import whisper_tool as _wt
        _wt._model_cache.clear()
    if payload.whisperModel is not None:
        _cfg.set("ai.whisper_model", payload.whisperModel.strip())
    if payload.maxConcurrentIndex is not None:
        val = max(1, min(10, payload.maxConcurrentIndex))
        _cfg.set("ai.max_concurrent_index", val)
        from backend.worker.worker_bus import bus as _bus
        _bus.set_max_concurrent_index(val)
    if payload.indexProvider is not None and payload.indexProvider in ("ollama", "gemini"):
        _cfg.set("ai.index_provider", payload.indexProvider)
    if payload.indexGeminiModel is not None:
        _cfg.set("ai.index_gemini_model", payload.indexGeminiModel.strip())
    return _get_ai_settings()
# Generator Settings  

class GeneratorSettingsPayload(BaseModel):
    # Image
    imageProvider: str | None = None  # "google" | "comfyui" | "local" | "stability"
    imageLocalModel:  str | None = None
    # ComfyUI
    comfyuiUrl: str | None = None
    comfyuiPath: str | None = None
    comfyuiModel: str | None = None
    comfyuiWidth: int | None = None
    comfyuiHeight: int | None = None
    comfyuiSteps: int | None = None
    comfyuiCfg: float | None = None
    # Stability AI
    stabilityModel: str | None = None  # "core" | "ultra" | "sd3"
    stabilityStyle: str | None = None  # "" | "photographic" | "anime" | ...
    stabilityWidth: int | None = None
    stabilityHeight: int | None = None
    # TTS
    ttsProvider: str | None = None
    ttsGoogleVoice: str | None = None
    ttsLocalModel: str | None = None
    ttsKokoroVoice: str | None = None
    # Video
    videoProvider: str | None = None
    videoLocalModel:  str | None = None
    # Ollama
    ollamaUrl: str | None = None


def _get_ollama_models() -> list[str]:
    """Return installed Ollama models, or [] if Ollama not running."""
    try:
        import ollama
        return [m.model for m in ollama.list().models]
    except Exception:
        try:
            import requests
            r = requests.get("http://localhost:11434/api/tags", timeout=2)
            if r.ok:
                return [m["name"] for m in r.json().get("models", [])]
        except Exception:
            pass
    return []


def _get_comfyui_models(base_url: str) -> list[str]:
    """Return checkpoint models installed in ComfyUI, or [] if not running."""
    try:
        import requests
        r = requests.get(f"{base_url.rstrip('/')}/models/checkpoints", timeout=2)
        if r.ok:
            return r.json() or []
    except Exception:
        pass
    return []


def _get_comfyui_status(base_url: str) -> bool:
    """True if ComfyUI server is responding."""
    try:
        import requests
        r = requests.get(f"{base_url.rstrip('/')}/system_stats", timeout=2)
        return r.ok
    except Exception:
        return False


def _get_generator_settings() -> dict:
    comfyui_url = _cfg.get("generators.comfyui_url", "http://127.0.0.1:8188")
    return {
        "imageProvider": _cfg.get("generators.image_provider", "google"),
        "imageLocalModel": _cfg.get("generators.image_local_model", "gemma3:4b"),
        # ComfyUI
        "comfyuiUrl": comfyui_url,
        "comfyuiPath": _cfg.get("generators.comfyui_path", ""),
        "comfyuiModel": _cfg.get("generators.comfyui_model", "v1-5-pruned-emaonly.safetensors"),
        "comfyuiWidth": _cfg.get("generators.comfyui_width", 512),
        "comfyuiHeight": _cfg.get("generators.comfyui_height", 512),
        "comfyuiSteps": _cfg.get("generators.comfyui_steps", 20),
        "comfyuiCfg": _cfg.get("generators.comfyui_cfg", 7.0),
        "comfyuiRunning": _get_comfyui_status(comfyui_url),
        "comfyuiModels": _get_comfyui_models(comfyui_url),
        # Stability AI
        "stabilityModel": _cfg.get("generators.stability_model", "core"),
        "stabilityStyle": _cfg.get("generators.stability_style", ""),
        "stabilityWidth": _cfg.get("generators.stability_width", 1024),
        "stabilityHeight": _cfg.get("generators.stability_height", 1024),
        # TTS
        "ttsProvider": _cfg.get("generators.tts_provider", "google"),
        "ttsGoogleVoice": _cfg.get("generators.tts_google_voice", "Kore"),
        "ttsLocalModel": _cfg.get("generators.tts_local_model", "kokoro"),
        "ttsKokoroVoice": _cfg.get("generators.tts_kokoro_voice", "af_heart"),
        # Video
        "videoProvider": _cfg.get("generators.video_provider", "google"),
        "videoLocalModel":  _cfg.get("generators.video_local_model", "wan2.1"),
        # Ollama
        "ollamaUrl": _cfg.get("generators.ollama_url", "http://localhost:11434"),
        "ollamaModels": _get_ollama_models(),
    }


@router.get("/settings/generators")
def getGeneratorSettings():
    return _get_generator_settings()


@router.post("/settings/generators")
def postGeneratorSettings(payload: GeneratorSettingsPayload):
    if payload.imageProvider in ("google", "comfyui", "local", "stability"):
        _cfg.set("generators.image_provider", payload.imageProvider)
    if payload.imageLocalModel is not None:
        _cfg.set("generators.image_local_model", payload.imageLocalModel.strip())
    # ComfyUI
    if payload.comfyuiUrl is not None:
        _cfg.set("generators.comfyui_url", payload.comfyuiUrl.strip())
    if payload.comfyuiPath is not None:
        _cfg.set("generators.comfyui_path", payload.comfyuiPath.strip())
    if payload.comfyuiModel is not None:
        _cfg.set("generators.comfyui_model", payload.comfyuiModel.strip())
    if payload.comfyuiWidth is not None:
        _cfg.set("generators.comfyui_width", max(256, min(2048, payload.comfyuiWidth)))
    if payload.comfyuiHeight is not None:
        _cfg.set("generators.comfyui_height", max(256, min(2048, payload.comfyuiHeight)))
    if payload.comfyuiSteps is not None:
        _cfg.set("generators.comfyui_steps", max(1, min(150, payload.comfyuiSteps)))
    if payload.comfyuiCfg is not None:
        _cfg.set("generators.comfyui_cfg", max(1.0, min(20.0, payload.comfyuiCfg)))
    # Stability AI
    if payload.stabilityModel in ("core", "ultra", "sd3"):
        _cfg.set("generators.stability_model", payload.stabilityModel)
    if payload.stabilityStyle is not None:
        _cfg.set("generators.stability_style", payload.stabilityStyle.strip())
    if payload.stabilityWidth is not None:
        _cfg.set("generators.stability_width", max(256, min(2048, payload.stabilityWidth)))
    if payload.stabilityHeight is not None:
        _cfg.set("generators.stability_height", max(256, min(2048, payload.stabilityHeight)))
    # TTS
    if payload.ttsProvider in ("google", "local", "kokoro"):
        _cfg.set("generators.tts_provider", payload.ttsProvider)
    if payload.ttsGoogleVoice is not None:
        _cfg.set("generators.tts_google_voice", payload.ttsGoogleVoice.strip())
    if payload.ttsLocalModel is not None:
        _cfg.set("generators.tts_local_model", payload.ttsLocalModel.strip())
    if payload.ttsKokoroVoice is not None:
        _cfg.set("generators.tts_kokoro_voice", payload.ttsKokoroVoice.strip())
    # Video
    if payload.videoProvider in ("google", "local"):
        _cfg.set("generators.video_provider", payload.videoProvider)
    if payload.videoLocalModel is not None:
        _cfg.set("generators.video_local_model", payload.videoLocalModel.strip())
    # Ollama
    if payload.ollamaUrl is not None:
        _cfg.set("generators.ollama_url", payload.ollamaUrl.strip())
    return _get_generator_settings()


# ── API Keys / .env Settings ──────────────────────────────────────────────

import os as _os
import sys as _sys
from pathlib import Path as _Path

def _resolve_env_file() -> _Path:
    """
    Resolve the .env file path for both dev and packaged (PyInstaller) mode.
    - Dev:       <repo_root>/.env  (next to package.json)
    - Packaged:  FADE_RESOURCES_PATH env var set by Electron main.ts
                 → typically %APPDATA%/Fade/.env
    """
    resources_path = _os.environ.get('FADE_RESOURCES_PATH', '')
    if resources_path:
        p = _Path(resources_path) / '.env'
        # Ensure the parent dir exists (first run)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    # Dev fallback: climb up from this file to repo root
    return _Path(__file__).resolve().parents[2] / '.env'

_ENV_FILE = _resolve_env_file()

# Only these keys can be read/written from the GUI
_ALLOWED_ENV_KEYS = [
    "FADE_AI_PROVIDER",
    "FADE_AI_MODEL",
    "GOOGLE_API_KEY",
    "OPENAI_API_KEY",
    "GROQ_API_KEY",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "TABI_API_KEY",
    "TABI_BASE_URL",
    "TOKENROUTER_API_KEY",
    "TOKENROUTER_BASE_URL",
    "OPENROUTER_API_KEY",
    "OPENROUTER_BASE_URL",
    "STABILITY_API_KEY",
    "YOUTUBE_CLIENT_ID",
    "YOUTUBE_CLIENT_SECRET",
    "OLLAMA_HOST",
    "LLAMACPP_BASE_URL",
]


def _read_env_file() -> dict[str, str]:
    """Parse the .env file into a dict (preserves comments as-is)."""
    result: dict[str, str] = {}
    if not _ENV_FILE.exists():
        return result
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            key, _, val = stripped.partition("=")
            result[key.strip()] = val.strip()
    return result


def _write_env_file(updates: dict[str, str]) -> None:
    """Update .env file with new values, preserving comments and order."""
    lines: list[str] = []
    if _ENV_FILE.exists():
        lines = _ENV_FILE.read_text(encoding="utf-8").splitlines()

    updated_keys: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                updated_keys.add(key)
                continue
        new_lines.append(line)

    # Add any new keys not already in the file
    for key, val in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={val}")

    _ENV_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    # Also update os.environ so changes take effect immediately
    for key, val in updates.items():
        _os.environ[key] = val


def _mask_key(val: str) -> str:
    """Show only last 4 chars: sk-****abcd"""
    if not val or len(val) <= 4:
        return val
    return val[:3] + "…" + val[-4:]


@router.get("/settings/env")
def getEnvSettings():
    env_data = _read_env_file()
    result: dict[str, dict] = {}
    for key in _ALLOWED_ENV_KEYS:
        raw = env_data.get(key, _os.environ.get(key, ""))
        is_secret = "KEY" in key or "SECRET" in key
        result[key] = {
            "value": raw,
            "masked": _mask_key(raw) if is_secret else raw,
            "isSecret": is_secret,
        }
    return result


class EnvUpdatePayload(BaseModel):
    updates: dict[str, str]


@router.post("/settings/env")
def postEnvSettings(payload: EnvUpdatePayload):
    # Only allow whitelisted keys
    safe_updates = {k: v for k, v in payload.updates.items() if k in _ALLOWED_ENV_KEYS}
    if safe_updates:
        _write_env_file(safe_updates)
        print(f"[Settings] Updated .env keys: {list(safe_updates.keys())}", flush=True)
    return getEnvSettings()
