import os
import tempfile
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from backend.state import engine, _library
from backend.worker.worker_bus import bus as _worker_bus

router = APIRouter()

_audio_cache_dir = os.path.join(tempfile.gettempdir(), "fade_audio_cache")
os.makedirs(_audio_cache_dir, exist_ok=True)


@router.get("/assets/{assetId}/waveform")
def getWaveform(assetId: str, bins: int = 200):
    asset = _library.get(assetId)
    if asset is None:
        raise HTTPException(404, f"Asset {assetId!r} not found")
    from backend.worker import waveform_cache
    cached = waveform_cache.get(assetId)
    if cached:
        if cached["status"] == "done":
            return {"assetId": assetId, "status": "done",
                    "bins": cached["bins"], "peaks": cached["peaks"]}
        if cached["status"] == "pending":
            return JSONResponse({"assetId": assetId, "status": "pending"}, status_code=202)
        if cached["status"] == "error":
            return JSONResponse({"assetId": assetId, "status": "error",
                                 "message": cached.get("message", "")}, status_code=500)
    _worker_bus.submit_waveform(assetId, asset.filepath, bins)
    return JSONResponse({"assetId": assetId, "status": "pending"}, status_code=202)


@router.get("/worker/status")
def workerStatus():
    return {"alive": _worker_bus.is_alive(), "queueDepth": _worker_bus.queue_depth()}


@router.get("/worker/jobs")
def workerJobs():
    from backend.worker import waveform_cache as _wc
    jobs = []
    for asset_id, entry in list(_wc._cache.items()):
        asset = _library.get(asset_id)
        label  = asset.filename if asset else asset_id[:12]
        status = entry.get("status", "pending")
        jobs.append({"id": asset_id, "type": "waveform", "label": label,
                     "status": status, "message": entry.get("message", "")})
    order = {"pending": 0, "running": 1, "error": 2, "done": 3}
    jobs.sort(key=lambda j: order.get(j["status"], 9))
    return jobs


@router.get("/assets/{assetId}/stream")
def streamAsset(assetId: str):
    asset = _library.get(assetId)
    if asset is None:
        raise HTTPException(404, f"Asset {assetId!r} not found")
    path = asset.filepath
    if not os.path.exists(path):
        raise HTTPException(404, "File not found on disk")
    ext = os.path.splitext(path)[1].lower()
    mime_map = {
        ".mp3": "audio/mpeg", ".wav": "audio/wav", ".aac": "audio/aac",
        ".flac": "audio/flac", ".ogg": "audio/ogg", ".m4a": "audio/mp4",
        ".mp4": "video/mp4", ".mov": "video/quicktime", ".avi": "video/x-msvideo",
    }
    return FileResponse(path, media_type=mime_map.get(ext, "application/octet-stream"),
                        headers={"Accept-Ranges": "bytes", "Cache-Control": "no-cache"})


@router.get("/assets/{assetId}/audio-stream")
def audioStream(assetId: str):
    import av
    asset = _library.get(assetId)
    if asset is None:
        raise HTTPException(404, f"Asset {assetId!r} not found")
    path = asset.filepath
    if not os.path.exists(path):
        raise HTTPException(404, "File not found on disk")
    ext = os.path.splitext(path)[1].lower()
    audio_exts = {".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a"}
    if ext in audio_exts:
        mime_map = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".aac": "audio/aac",
                    ".flac": "audio/flac", ".ogg": "audio/ogg", ".m4a": "audio/mp4"}
        return FileResponse(path, media_type=mime_map.get(ext, "audio/mpeg"),
                            headers={"Accept-Ranges": "bytes", "Cache-Control": "public, max-age=3600"})
    cache_path = os.path.join(_audio_cache_dir, f"{assetId}.wav")
    if not os.path.exists(cache_path):
        try:
            in_container  = av.open(path)
            audio_stream  = next((s for s in in_container.streams if s.type == 'audio'), None)
            if audio_stream is None:
                in_container.close()
                raise HTTPException(404, "No audio stream found in file")
            out_container = av.open(cache_path, 'w')
            out_stream    = out_container.add_stream('pcm_s16le', rate=audio_stream.sample_rate)
            for packet in in_container.demux(audio_stream):
                for frame in packet.decode():
                    frame.pts = None
                    for out_packet in out_stream.encode(frame):
                        out_container.mux(out_packet)
            for out_packet in out_stream.encode(None):
                out_container.mux(out_packet)
            out_container.close()
            in_container.close()
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Audio extraction error: {e}")
    return FileResponse(cache_path, media_type="audio/wav",
                        headers={"Accept-Ranges": "bytes", "Cache-Control": "public, max-age=3600"})


@router.get("/timeline/audio-clips")
def listAudioClips():
    # Always scan rootTimeline — addClip writes there, not activeTimeline
    tl = engine.rootTimeline or engine.activeTimeline
    if tl is None:
        return {"clips": []}
    result = []

    def _collect_audio(timeline, frame_offset: int = 0):
        for track in timeline.tracks:
            for clip in track.clips:
                clip_type = getattr(clip, "CLIP_TYPE", getattr(clip, "clipType", "video"))
                if clip_type == "comp":
                    comp_id = getattr(clip, "compId", None)
                    if comp_id:
                        inner_tl = engine.getTimeline(comp_id)
                        if inner_tl:
                            _collect_audio(inner_tl, frame_offset + clip.startFrame)
                    continue
                asset_id = getattr(clip, "assetId", None) or ""
                if not asset_id:
                    continue
                asset = _library.get(asset_id)
                if asset is None:
                    continue
                # Include pure audio clips (AudioClip) OR video clips that have audio
                clip_is_audio = clip_type == "audio"
                if not clip_is_audio and not asset.hasAudio:
                    continue
                result.append({
                    "clipId":      clip.clipId,
                    "assetId":     asset_id,
                    "startFrame":  frame_offset + clip.startFrame,
                    "duration":    clip.duration,
                    "mediaOffset": getattr(clip, "mediaOffset", 0),
                    "volume":      getattr(clip, "volume", 1.0),
                    "streamUrl":   f"/assets/{asset_id}/audio-stream",
                })

    _collect_audio(tl)
    return {"clips": result}


@router.get("/fonts")
def listFonts():
    try:
        import skia
        fm = skia.FontMgr()
        families = [fm.getFamilyName(i) for i in range(fm.countFamilies())]
        return {"fonts": sorted(set(families))}
    except Exception as e:
        return {"fonts": [], "error": str(e)}
