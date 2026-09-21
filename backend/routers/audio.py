import os
import tempfile
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse, Response
from backend.state import engine, _library
from backend.worker.worker_bus import bus as _worker_bus

router = APIRouter()

_CHUNK = 1 << 20  # 1 MB chunks


def _stream_file(path: str, media_type: str, request: Request):
    """
    Range-aware chunked file streaming.
    Avoids FileResponse's os.stat() → full-read mismatch on Windows
    (causes RuntimeError: Response content longer than Content-Length).
    """
    file_size = os.path.getsize(path)
    range_header = request.headers.get("range", "")

    if range_header.startswith("bytes="):
        # Parse first range only
        try:
            start_str, end_str = range_header[6:].split("-", 1)
            start = int(start_str) if start_str else 0
            end   = int(end_str)   if end_str   else file_size - 1
        except Exception:
            start, end = 0, file_size - 1
        start = max(0, min(start, file_size - 1))
        end   = max(start, min(end, file_size - 1))
        length = end - start + 1

        def _iter_range():
            remaining = length
            with open(path, "rb") as f:
                f.seek(start)
                while remaining > 0:
                    chunk = f.read(min(_CHUNK, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            _iter_range(),
            status_code=206,
            media_type=media_type,
            headers={
                "Content-Range":  f"bytes {start}-{end}/{file_size}",
                "Content-Length": str(length),
                "Accept-Ranges":  "bytes",
                "Cache-Control":  "no-cache",
            },
        )

    # Full file
    def _iter_full():
        with open(path, "rb") as f:
            while True:
                chunk = f.read(_CHUNK)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        _iter_full(),
        media_type=media_type,
        headers={
            "Content-Length": str(file_size),
            "Accept-Ranges":  "bytes",
            "Cache-Control":  "no-cache",
        },
    )

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
def streamAsset(assetId: str, request: Request):
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
    # Use chunked streaming — FileResponse relies on os.stat() for Content-Length
    # then reads the entire file; on Windows, OS buffering can make actual bytes
    # read differ from st_size for large files → RuntimeError in uvicorn.
    return _stream_file(path, mime_map.get(ext, "application/octet-stream"), request)


@router.get("/assets/{assetId}/audio-stream")
def audioStream(assetId: str, request: Request):
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
        return _stream_file(path, mime_map.get(ext, "audio/mpeg"), request)
    cache_path = os.path.join(_audio_cache_dir, f"{assetId}.wav")
    if not os.path.exists(cache_path):
        # Write to .tmp first then rename atomically — prevents Content-Length
        # mismatch if another request reads the cache file while it's being written.
        tmp_path = cache_path + ".tmp"
        try:
            in_container  = av.open(path)
            audio_stream  = next((s for s in in_container.streams if s.type == 'audio'), None)
            if audio_stream is None:
                in_container.close()
                raise HTTPException(404, "No audio stream found in file")
            out_container = av.open(tmp_path, 'w')
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
            os.replace(tmp_path, cache_path)  # atomic — file appears complete or not at all
        except HTTPException:
            raise
        except Exception as e:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise HTTPException(500, f"Audio extraction error: {e}")
    return _stream_file(cache_path, "audio/wav", request)


@router.get("/assets/{assetId}/audio-stream/{clipId}")
def audioStreamForClip(assetId: str, clipId: str, request: Request):
    """Clip-scoped alias for audioStream.
    
    Having a unique URL per clip (rather than per asset) prevents the browser
    audio engine from treating two clips that share the same source file as
    the same buffer node — which caused audio to play from the wrong clip.
    """
    return audioStream(assetId, request)


@router.get("/timeline/audio-clips")
def listAudioClips():
    # Always scan rootTimeline  
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
                # Include pure audio clips  
                clip_is_audio = clip_type == "audio"
                if not clip_is_audio and not asset.hasAudio:
                    continue
                result.append({
                    "clipId": clip.clipId,
                    "assetId": asset_id,
                    "filePath": asset.filepath,
                    "startFrame":  frame_offset + clip.startFrame,
                    "duration": clip.duration,
                    "mediaOffset": getattr(clip, "mediaOffset", 0),
                    "volume": getattr(clip, "volume", 1.0),
                    # Use clip-scoped URL so audio engine never confuses two clips
                    # that share the same underlying asset.
                    "streamUrl":   f"/assets/{asset_id}/audio-stream/{clip.clipId}",
                })

    _collect_audio(tl)
    fps = getattr(tl, 'fps', 30.0)
    return {"clips": result, "fps": fps}


@router.get("/fonts")
def listFonts():
    try:
        import skia
        fm = skia.FontMgr()
        families = [fm.getFamilyName(i) for i in range(fm.countFamilies())]
        return {"fonts": sorted(set(families))}
    except Exception as e:
        return {"fonts": [], "error": str(e)}
