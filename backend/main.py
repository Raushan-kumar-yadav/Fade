from __future__ import annotations
import os
import faulthandler

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS",  "1")

# Dump C-level stack trace on segfault / access violation
faulthandler.enable()

import asyncio
import socket
import uuid
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from backend.engine.engine import Engine
from backend.media.asset.mediaAsset import MediaAsset
from backend.timeline.tracks.videoTrack import VideoTrack
from backend.timeline.tracks.audioTrack import AudioTrack
from backend.timeline.clips.videoClip import VideoClip
from backend.history.commandStack import (
    MoveClipCommand, TrimClipCommand, SplitClipCommand,
    RemoveClipCommand,
)

engine = Engine()

# In-memory asset library:  assetId → MediaAsset
_library: dict[str, MediaAsset] = {}

# In-memory clip→track index map  (clipId → trackIndex)
_clipTrackMap: dict[str, int] = {}

#   Lifespan  

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create default project + seed tracks, then start preview loop."""
    engine.newProject()

    tl = engine.activeTimeline
    if tl:
        for name in ["Video 1", "Video 2", "Video 3"]:
            tl.addTrack(VideoTrack(name))
        tl.addTrack(AudioTrack("Audio 1"))

    asyncio.create_task(engine.startPreviewLoop())
    yield
    # Shutdown: nothing to clean up for now


#   FastAPI app  
app = FastAPI(title="Fade Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


#   Health / Project  

@app.get("/health")
def health():
    return {"status": "ok"}


#   Settings  

class SettingsPayload(BaseModel):
    cacheMaxMB:      int   | None = None   # Frame cache budget in MB
    previewScale:    float | None = None   # Decode resolution 0.125–1.0
    jpegQuality:     int   | None = None   # JPEG encode quality 1–100
    prefetchRadius:  int   | None = None   # Frames to pre-decode ahead
    batchSize:       int   | None = None   # Frames decoded per worker wakeup
    decoderMode:     str   | None = None   # "auto" | "pyav" | "ffmpeg"


def _get_settings() -> dict:
    import backend.compositor.compositor as _comp
    from backend.media.scheduler.decodeScheduler import DecodeScheduler
    from backend.media.cache.frameCache import FrameCache
    from backend.media.decoder.videoDecoder import _DECODER_MODE

    cache_mb   = round(engine.scheduler._frameCache._maxBytes / (1024**2)) if engine.scheduler else 512
    scale      = engine.getPreviewScale()
    quality    = getattr(engine.compositor, '_jpegQuality', 85) if engine.compositor else 85
    return {
        "cacheMaxMB":     cache_mb,
        "cacheUsedMB":    round(engine.scheduler._frameCache.usedMB, 1) if engine.scheduler else 0,
        "cacheFrames":    engine.scheduler._frameCache.entryCount if engine.scheduler else 0,
        "cacheMaxFrames": FrameCache.MAX_FRAMES,
        "previewScale":   scale,
        "jpegQuality":    quality,
        "prefetchRadius": _comp.PREFETCH_RADIUS,
        "batchSize":      DecodeScheduler.BATCH_SIZE,
        "decoderMode":    _DECODER_MODE,
    }


@app.get("/settings")
def getSettings():
    return _get_settings()


@app.post("/settings")
def postSettings(payload: SettingsPayload):
    import backend.compositor.compositor as _comp
    from backend.media.scheduler.decodeScheduler import DecodeScheduler

    if payload.cacheMaxMB is not None:
        mb = max(64, min(4096, payload.cacheMaxMB))
        if engine.scheduler:
            engine.scheduler._frameCache._maxBytes = mb * 1024 * 1024

    if payload.previewScale is not None:
        engine.setPreviewScale(payload.previewScale)

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



@app.get("/project")
def getProject():
    if engine.project is None:
        return {"error": "No active project"}
    return engine.project.toDict()


@app.post("/project/new")
def newProject(name: str = "Untitled Project",
               width: int = 1920, height: int = 1080, fps: float = 30.0):
    engine.newProject(name=name, width=width, height=height, fps=fps)
    return {"status": "ok", "project": engine.project.toDict()}


#   Library routes  

class ImportRequest(BaseModel):
    filepath: str


def _mediaType(filepath: str) -> str:
    ext = os.path.splitext(filepath)[1].lower()
    if ext in {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}:
        return "video"
    if ext in {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp", ".gif"}:
        return "image"
    if ext in {".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a"}:
        return "audio"
    return "unknown"


@app.get("/library/assets")
def listAssets():
    return [
        {
            "assetId":  a.assetId,
            "filename": os.path.basename(a.filepath),
            "filepath": a.filepath,
            "type":     a.mediaType.value if hasattr(a.mediaType, 'value') else str(a.mediaType),
        }
        for a in _library.values()
    ]


@app.post("/library/import")
def importAsset(req: ImportRequest):
    if not os.path.exists(req.filepath):
        raise HTTPException(404, f"File not found: {req.filepath}")

    # De-duplicate by path
    for a in _library.values():
        if a.filepath == req.filepath:
            return {
                "assetId":  a.assetId,
                "filename": os.path.basename(a.filepath),
                "filepath": a.filepath,
                "type":     a.mediaType,
            }

    assetId = str(uuid.uuid4())
    asset = MediaAsset(
        filepath = req.filepath,
        assetId  = assetId,
    )
    _library[assetId] = asset

    return {
        "assetId":  assetId,
        "filename": os.path.basename(req.filepath),
        "filepath": req.filepath,
        "type":     asset.mediaType,
    }


@app.delete("/library/assets/{assetId}")
def deleteAsset(assetId: str):
    _library.pop(assetId, None)
    return {"status": "ok"}


#   Timeline routes  

class AddClipRequest(BaseModel):
    assetId: str
    trackIndex: int
    startFrame: int
    duration: int


class MoveClipRequest(BaseModel):
    clipId: str
    startFrame: int
    trackIndex: int


class TrimClipRequest(BaseModel):
    clipId: str
    side: str        # 'left' or 'right'
    frameDelta: int  # positive = extend, negative = shrink


class SplitClipRequest(BaseModel):
    clipId: str
    frame: int       # global timeline frame at which to split


@app.post("/timeline/add-clip")
def addClip(req: AddClipRequest):
    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(400, "No active timeline")

    asset = _library.get(req.assetId)
    if asset is None:
        raise HTTPException(404, f"Asset {req.assetId!r} not in library — import it first")

    if req.trackIndex >= len(tl.tracks):
        raise HTTPException(400, f"Track index {req.trackIndex} out of range (have {len(tl.tracks)})")

    track = tl.tracks[req.trackIndex]

    clip = VideoClip(
        startFrame = req.startFrame,
        duration = req.duration,
        assetId = req.assetId,
    )

    # Wire scheduler so the clip can decode immediately
    if engine.scheduler:
        clip.setScheduler(engine.scheduler, engine.project.fps if engine.project else 30.0)
        engine.scheduler.registerClip(clip.clipId, asset)

    track.addClip(clip)
    _clipTrackMap[clip.clipId] = req.trackIndex

    return {
        "clipId": clip.clipId,
        "trackId": track.trackId,
        "startFrame": clip.startFrame,
        "duration": clip.duration,
        "assetId": req.assetId,
        "type": "video",
    }


@app.post("/timeline/move-clip")
def moveClip(req: MoveClipRequest):
    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(400, "No active timeline")

    # Find and remove clip from its current track
    clip = None
    srcIdx = None
    for i, track in enumerate(tl.tracks):
        c = track.getClip(req.clipId)
        if c:
            clip   = c
            srcIdx = i
            track.removeClip(req.clipId)
            break

    if clip is None:
        raise HTTPException(404, f"Clip {req.clipId!r} not found")

    dstIdx = max(0, min(len(tl.tracks) - 1, req.trackIndex))
    clip.startFrame = max(0, req.startFrame)
    tl.tracks[dstIdx].addClip(clip)
    _clipTrackMap[req.clipId] = dstIdx
    return {"status": "ok"}


@app.delete("/timeline/clips/{clipId}")
def deleteClip(clipId: str):
    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(400, "No active timeline")

    for track in tl.tracks:
        clip = track.getClip(clipId)
        if clip:
            from backend.history.commandStack import RemoveClipCommand
            cmd = RemoveClipCommand(track, clip)
            engine.commandStack.execute(cmd)    # removes clip from track
            if engine.scheduler:
                engine.scheduler.unregisterClip(clipId)
            _clipTrackMap.pop(clipId, None)
            return {"status": "ok"}

    raise HTTPException(404, f"Clip {clipId!r} not found")


@app.post("/timeline/trim-clip")
def trimClip(req: TrimClipRequest):
    """Trim the left or right edge of a clip. Pushed to CommandStack for undo."""
    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(400, "No active timeline")

    for track in tl.tracks:
        clip = track.getClip(req.clipId)
        if clip:
            cmd = TrimClipCommand(clip, req.side, req.frameDelta)
            engine.commandStack.execute(cmd)
            track.clips.sort(key=lambda c: c.startFrame)
            return {
                "clipId":     clip.clipId,
                "startFrame": clip.startFrame,
                "duration":   clip.duration,
            }

    raise HTTPException(404, f"Clip {req.clipId!r} not found")


@app.post("/timeline/split-clip")
def splitClip(req: SplitClipRequest):
    """Split a clip at global timeline frame. Returns both clip IDs."""
    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(400, "No active timeline")

    fps = engine.project.fps if engine.project else 30.0

    for track in tl.tracks:
        clip = track.getClip(req.clipId)
        if clip:
            asset = _library.get(clip.assetId) if clip.assetId else None
            cmd = SplitClipCommand(
                track, clip, req.frame,
                scheduler = engine.scheduler,
                asset     = asset,
                fps       = fps,
            )
            try:
                engine.commandStack.execute(cmd)
            except ValueError as e:
                raise HTTPException(400, str(e))
            right = cmd._rightClip
            trackIndex = tl.tracks.index(track)
            _clipTrackMap[clip.clipId] = trackIndex
            if right:
                _clipTrackMap[right.clipId] = trackIndex
            return {
                "leftClipId":  clip.clipId,
                "rightClipId": right.clipId if right else None,
                "splitFrame":  req.frame,
                "trackId":     track.trackId,
            }

    raise HTTPException(404, f"Clip {req.clipId!r} not found")


# ── Undo / Redo ───────────────────────────────────────────────────────────────

@app.post("/history/undo")
def undoAction():
    desc = engine.commandStack.undo()
    return {
        "undone":   desc,
        "canUndo":  engine.commandStack.canUndo,
        "canRedo":  engine.commandStack.canRedo,
    }


@app.post("/history/redo")
def redoAction():
    desc = engine.commandStack.redo()
    return {
        "redone":   desc,
        "canUndo":  engine.commandStack.canUndo,
        "canRedo":  engine.commandStack.canRedo,
    }


@app.get("/history/state")
def historyState():
    return {
        "canUndo":       engine.commandStack.canUndo,
        "canRedo":       engine.commandStack.canRedo,
        "undoLabel":     engine.commandStack.undoDescription,
        "redoLabel":     engine.commandStack.redoDescription,
    }


# ── Track controls ────────────────────────────────────────────────────────────

@app.post("/timeline/track/{trackId}/mute")
def muteTrack(trackId: str):
    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(400, "No active timeline")
    track = tl.getTrack(trackId)
    if track is None:
        raise HTTPException(404, f"Track {trackId!r} not found")
    track.muted = not track.muted
    return {"trackId": trackId, "muted": track.muted}


@app.post("/timeline/track/{trackId}/solo")
def soloTrack(trackId: str):
    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(400, "No active timeline")
    track = tl.getTrack(trackId)
    if track is None:
        raise HTTPException(404, f"Track {trackId!r} not found")
    target = not getattr(track, 'solo', False)
    # Solo is exclusive — unsolo all others
    for t in tl.tracks:
        t.solo = False
    track.solo = target
    return {"trackId": trackId, "solo": track.solo}


@app.post("/timeline/track/{trackId}/lock")
def lockTrack(trackId: str):
    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(400, "No active timeline")
    track = tl.getTrack(trackId)
    if track is None:
        raise HTTPException(404, f"Track {trackId!r} not found")
    track.locked = not track.locked
    return {"trackId": trackId, "locked": track.locked}



@app.get("/timeline/state")
def timelineState():
    tl  = engine.activeTimeline
    prj = engine.project
    fps         = prj.fps         if prj else 30.0
    totalFrames = prj.totalFrame  if prj else 1800
    if tl is None:
        return {"tracks": [], "totalFrames": totalFrames, "fps": fps}
    data = tl.toDict()
    data["totalFrames"] = totalFrames
    data["fps"]         = fps
    return data


#   Playback routes  

@app.post("/playback/play")
def play():
    engine.play()
    return {"playing": True}


@app.post("/playback/pause")
def pause():
    engine.pause()
    return {"playing": False}


class SeekRequest(BaseModel):
    frame: int

@app.post("/playback/seek")
def seek(req: SeekRequest):
    engine.seek(req.frame)
    return {"frame": engine.currentFrame}


@app.get("/playback/state")
def playbackState():
    prj = engine.project
    return {
        "frame":       engine.currentFrame,
        "playing":     engine._playing,
        "fps":         prj.fps if prj else 30.0,
        "totalFrames": prj.totalFrame if prj else 1800,
    }


@app.get("/perf")
def perfStats():
    return engine.perfStats()


 
@app.get("/frame/{frame}")
def getFrame(frame: int):
    png = engine.renderFramePng(frame)
    return Response(content=png, media_type="image/png")


@app.get("/thumbnail/{frame}")
def getThumbnail(frame: int, w: int = 320, h: int = 180):
    png = engine.renderThumbnail(frame, w, h)
    return Response(content=png, media_type="image/png")


class ScaleRequest(BaseModel):
    scale: float   


@app.post("/preview/scale")
def setPreviewScale(req: ScaleRequest):
    """Change decoder resolution cap — restarts decoders with new scale."""
    clamped = max(0.125, min(1.0, req.scale))
    engine.setPreviewScale(clamped)
    return {"scale": clamped}


@app.get("/preview/scale")
def getPreviewScale():
    return {"scale": engine.getPreviewScale()}


#   WebSocket preview  

@app.websocket("/ws/preview")
async def previewStream(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            jpeg = await engine.frameQueue.get()
            await ws.send_bytes(jpeg)
    except WebSocketDisconnect:
        pass


#   Entry point  

def _findFreePort(start: int = 8000, end: int = 8010) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found between {start} and {end}")


# ═══════════════════════════════════════════════════════════════════════
#   Text / Shape / Pen / Mask routes
# ═══════════════════════════════════════════════════════════════════════

from backend.timeline.clips.textClip  import TextClip,  TextStyle,  MaskLayer
from backend.timeline.clips.shapeClip import ShapeClip, ShapeStyle
from backend.timeline.clips.penClip   import PenClip,   BezierPoint


def _active_timeline():
    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(status_code=400, detail="No active timeline")
    return tl


def _find_clip(clipId: str):
    tl = _active_timeline()
    for track in tl.tracks:
        for clip in track.clips:
            if clip.clipId == clipId:
                return clip, track
    raise HTTPException(status_code=404, detail=f"Clip {clipId!r} not found")


def _default_video_track():
    """Return first non-audio track, or create one."""
    from backend.timeline.tracks.videoTrack import VideoTrack
    tl = _active_timeline()
    for track in tl.tracks:
        if not getattr(track, 'isAudio', lambda: False)():
            return track
    track = VideoTrack("Video 1")
    tl.addTrack(track)
    return track


# ── Text ─────────────────────────────────────────────────────────────

class TextClipRequest(BaseModel):
    trackIndex: int  | None = None
    startFrame: int         = 0
    duration:   int         = 150
    style:      dict        = {}


@app.post("/clips/text")
def addTextClip(req: TextClipRequest):
    import uuid
    tl    = _active_timeline()
    track = _default_video_track()
    clip  = TextClip(
        clipId     = str(uuid.uuid4()),
        startFrame = req.startFrame,
        duration   = req.duration,
        style      = TextStyle.fromDict(req.style),
    )
    track.addClip(clip)
    return clip.toDict()


class TextPatchRequest(BaseModel):
    style:    dict | None = None
    transform: dict | None = None


@app.patch("/clips/text/{clipId}")
def updateTextClip(clipId: str, req: TextPatchRequest):
    clip, _ = _find_clip(clipId)
    if not isinstance(clip, TextClip):
        raise HTTPException(400, "Not a text clip")
    if req.style:
        for k, v in req.style.items():
            if hasattr(clip.style, k):
                setattr(clip.style, k, v)
    if req.transform:
        from backend.animation.transform import Transform
        clip.transform = Transform.fromDict(req.transform)
    return clip.toDict()


# ── Shape ─────────────────────────────────────────────────────────────

class ShapeClipRequest(BaseModel):
    startFrame: int  = 0
    duration:   int  = 150
    style:      dict = {}


@app.post("/clips/shape")
def addShapeClip(req: ShapeClipRequest):
    import uuid
    track = _default_video_track()
    clip  = ShapeClip(
        clipId     = str(uuid.uuid4()),
        startFrame = req.startFrame,
        duration   = req.duration,
        style      = ShapeStyle.fromDict(req.style),
    )
    track.addClip(clip)
    return clip.toDict()


class ShapePatchRequest(BaseModel):
    style:     dict | None = None
    transform: dict | None = None


@app.patch("/clips/shape/{clipId}")
def updateShapeClip(clipId: str, req: ShapePatchRequest):
    clip, _ = _find_clip(clipId)
    if not isinstance(clip, ShapeClip):
        raise HTTPException(400, "Not a shape clip")
    if req.style:
        for k, v in req.style.items():
            if hasattr(clip.style, k):
                setattr(clip.style, k, v)
    if req.transform:
        from backend.animation.transform import Transform
        clip.transform = Transform.fromDict(req.transform)
    return clip.toDict()


# ── Pen ───────────────────────────────────────────────────────────────

class PenClipRequest(BaseModel):
    startFrame: int   = 0
    duration:   int   = 150
    isClosed:   bool  = False
    points:     list  = []
    style:      dict  = {}


@app.post("/clips/pen")
def addPenClip(req: PenClipRequest):
    import uuid
    track = _default_video_track()
    clip  = PenClip(
        clipId     = str(uuid.uuid4()),
        startFrame = req.startFrame,
        duration   = req.duration,
        isClosed   = req.isClosed,
        points     = [BezierPoint.fromDict(p) for p in req.points],
        style      = ShapeStyle.fromDict(req.style),
    )
    track.addClip(clip)
    return clip.toDict()


class PenPointsRequest(BaseModel):
    points:   list = []
    isClosed: bool | None = None


@app.patch("/clips/pen/{clipId}/points")
def updatePenPoints(clipId: str, req: PenPointsRequest):
    clip, _ = _find_clip(clipId)
    if not isinstance(clip, PenClip):
        raise HTTPException(400, "Not a pen clip")
    clip.points = [BezierPoint.fromDict(p) for p in req.points]
    if req.isClosed is not None:
        clip.isClosed = req.isClosed
    return clip.toDict()


# ── Mask ──────────────────────────────────────────────────────────────

class MaskRequest(BaseModel):
    name:     str   = "Mask"
    shape:    str   = "rect"    # rect | ellipse | bezier
    mode:     str   = "add"
    inverted: bool  = False
    feather:  float = 0.0
    opacity:  float = 1.0
    points:   list  = []


@app.post("/clips/{clipId}/mask")
def addMask(clipId: str, req: MaskRequest):
    import uuid
    clip, _ = _find_clip(clipId)
    if not hasattr(clip, "masks"):
        raise HTTPException(400, "Clip type does not support masks")
    mask = MaskLayer(
        maskId   = str(uuid.uuid4()),
        name     = req.name,
        shape    = req.shape,
        mode     = req.mode,
        inverted = req.inverted,
        feather  = req.feather,
        opacity  = req.opacity,
        points   = req.points,
    )
    clip.addMask(mask)
    return clip.toDict()


class MaskPatchRequest(BaseModel):
    name:     str   | None = None
    mode:     str   | None = None
    inverted: bool  | None = None
    feather:  float | None = None
    opacity:  float | None = None
    points:   list  | None = None


@app.patch("/clips/{clipId}/mask/{maskId}")
def updateMask(clipId: str, maskId: str, req: MaskPatchRequest):
    clip, _ = _find_clip(clipId)
    mask = getattr(clip, "getMask", lambda _: None)(maskId)
    if mask is None:
        raise HTTPException(404, f"Mask {maskId!r} not found on clip {clipId!r}")
    for field_name in ("name", "mode", "inverted", "feather", "opacity", "points"):
        v = getattr(req, field_name)
        if v is not None:
            setattr(mask, field_name, v)
    return clip.toDict()


@app.delete("/clips/{clipId}/mask/{maskId}")
def removeMask(clipId: str, maskId: str):
    clip, _ = _find_clip(clipId)
    removed = getattr(clip, "removeMask", lambda _: False)(maskId)
    if not removed:
        raise HTTPException(404, f"Mask {maskId!r} not found")
    return {"status": "ok", "clipId": clipId}


# ── System fonts ───────────────────────────────────────────────────────

@app.get("/fonts")
def listFonts():
    """Return system font families available to Skia."""
    try:
        import skia
        fm = skia.FontMgr()
        families = [fm.getFamilyName(i) for i in range(fm.countFamilies())]
        return {"fonts": sorted(set(families))}
    except Exception as e:
        return {"fonts": [], "error": str(e)}



if __name__ == "__main__":
    port = _findFreePort()
    print(f"[Fade] Backend starting on port {port}", flush=True)
    print(f"[Fade] Python {__import__('sys').version.split()[0]} | skia + subprocess-ffmpeg ready", flush=True)
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
