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


def _top_empty_track(startFrame: int, duration: int):
    """Return the topmost video track with no clip overlapping [startFrame, startFrame+duration).
    If all tracks are occupied, create a new VideoTrack above them."""
    from backend.timeline.tracks.videoTrack import VideoTrack
    tl = _active_timeline()
    endFrame = startFrame + duration

    video_tracks = [t for t in tl.tracks if not getattr(t, 'isAudio', lambda: False)()]

    # Walk from top (last) to bottom; return the first free one
    for track in reversed(video_tracks):
        clips = getattr(track, 'clips', [])
        overlaps = any(
            not (clip.startFrame >= endFrame or clip.startFrame + clip.duration <= startFrame)
            for clip in clips
        )
        if not overlaps:
            return track

    # All occupied — add a new track at the top
    name = f"Video {len(video_tracks) + 1}"
    new_track = VideoTrack(name)
    tl.addTrack(new_track)
    return new_track


def _default_video_track():
    """Return first non-audio track, or create one (legacy helper)."""
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
    track = _top_empty_track(req.startFrame, req.duration)
    clip  = TextClip(
        clipId     = str(uuid.uuid4()),
        startFrame = req.startFrame,
        duration   = req.duration,
        style      = TextStyle.fromDict(req.style),
    )
    track.addClip(clip)
    _clipTrackMap[clip.clipId] = tl.tracks.index(track)
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
    startFrame: int   = 0
    duration:   int   = 150
    style:      dict  = {}
    x:          float = 960.0   # center x in design space (default: canvas center)
    y:          float = 540.0   # center y in design space


@app.post("/clips/shape")
def addShapeClip(req: ShapeClipRequest):
    import uuid
    tl    = _active_timeline()
    track = _top_empty_track(req.startFrame, req.duration)
    clip  = ShapeClip(
        clipId     = str(uuid.uuid4()),
        startFrame = req.startFrame,
        duration   = req.duration,
        style      = ShapeStyle.fromDict(req.style),
    )
    # Position the shape where the user drew it
    clip.transform.position.setBase(req.x, req.y)
    track.addClip(clip)
    _clipTrackMap[clip.clipId] = tl.tracks.index(track)
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
    tl    = _active_timeline()
    track = _top_empty_track(req.startFrame, req.duration)
    clip  = PenClip(
        clipId     = str(uuid.uuid4()),
        startFrame = req.startFrame,
        duration   = req.duration,
        isClosed   = req.isClosed,
        points     = [BezierPoint.fromDict(p) for p in req.points],
        style      = ShapeStyle.fromDict(req.style),
    )
    track.addClip(clip)
    _clipTrackMap[clip.clipId] = tl.tracks.index(track)
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
    # All clips now support masks via BaseClip
    if not hasattr(clip, 'masks'):
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
    print(f"[addMask] clipId={clipId[:8]} maskId={mask.maskId[:8]} shape={mask.shape} pts={len(mask.points)} mode={mask.mode}")
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
            print(f"[updateMask] clipId={clipId[:8]} maskId={maskId[:8]} {field_name}={v}")
            setattr(mask, field_name, v)
    return clip.toDict()


@app.delete("/clips/{clipId}/mask/{maskId}")
def removeMask(clipId: str, maskId: str):
    clip, _ = _find_clip(clipId)
    removed = getattr(clip, "removeMask", lambda _: False)(maskId)
    if not removed:
        raise HTTPException(404, f"Mask {maskId!r} not found")
    return {"status": "ok", "clipId": clipId}


@app.get("/clips/{clipId}/masks")
def listMasks(clipId: str):
    """Return all masks attached to a clip."""
    clip, _ = _find_clip(clipId)
    masks = getattr(clip, 'masks', [])
    return {
        "clipId": clipId,
        "masks": [
            {
                "maskId":   m.maskId,
                "name":     m.name,
                "shape":    m.shape,
                "mode":     m.mode,
                "inverted": m.inverted,
                "feather":  m.feather,
                "opacity":  m.opacity,
                "pointCount": len(getattr(m, 'points', [])),
            }
            for m in masks
        ],
    }


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



# ── Inspector — params + keyframes ─────────────────────────────────────────

from backend.timeline.clips.animEngine import AnimParam, Interp, Keyframe as KF


def _get_or_create_anim(clip, key: str, base_value) -> AnimParam:
    """Lazily create AnimParam store on clip."""
    if not hasattr(clip, '_anim_params'):
        clip._anim_params = {}
    if key not in clip._anim_params:
        clip._anim_params[key] = AnimParam(base_value)
    return clip._anim_params[key]


def _clip_param_schema(clip) -> list:
    """Build param descriptor list based on clip type."""
    from backend.timeline.clips.textClip  import TextClip
    from backend.timeline.clips.shapeClip import ShapeClip
    from backend.timeline.clips.penClip   import PenClip

    t = clip.transform
    px, py = t.position.get()
    sx, sy = t.scale.get()
    ax, ay = t.anchor.get()

    # Transform params — real units: opacity 0-1, scale 0-10, position px, rotation deg
    base = [
        {"id": "opacity",  "label": "Opacity",    "type": "float", "min": 0,     "max": 1,    "default": round(t.opacity.get(), 4),  "group": "Transform"},
        {"id": "pos_x",    "label": "Position X", "type": "float", "min": -3840, "max": 3840, "default": round(px, 2),               "group": "Transform"},
        {"id": "pos_y",    "label": "Position Y", "type": "float", "min": -2160, "max": 2160, "default": round(py, 2),               "group": "Transform"},
        {"id": "scale_x",  "label": "Scale X",    "type": "float", "min": 0,     "max": 10,   "default": round(sx, 4),               "group": "Transform"},
        {"id": "scale_y",  "label": "Scale Y",    "type": "float", "min": 0,     "max": 10,   "default": round(sy, 4),               "group": "Transform"},
        {"id": "rotation", "label": "Rotation",   "type": "float", "min": -360,  "max": 360,  "default": round(t.rotation.get(), 2), "group": "Transform"},
        {"id": "anchor_x", "label": "Anchor X",   "type": "float", "min": -1920, "max": 1920, "default": round(ax, 2),               "group": "Transform"},
        {"id": "anchor_y", "label": "Anchor Y",   "type": "float", "min": -1080, "max": 1080, "default": round(ay, 2),               "group": "Transform"},
    ]

    if isinstance(clip, TextClip):
        s = clip.style
        base += [
            {"id": "font_size",    "label": "Font Size",     "type": "float", "min": 4,  "max": 400, "default": s.fontSize,     "group": "Text"},
            {"id": "tracking",     "label": "Tracking",      "type": "float", "min": -20,"max": 100, "default": s.letterSpacing,"group": "Text"},
            {"id": "line_height",  "label": "Line Height",   "type": "float", "min": 0.5,"max": 4,   "default": s.lineHeight,   "group": "Text"},
            {"id": "fill_r",       "label": "Fill R",        "type": "float", "min": 0,  "max": 1,   "default": s.color[0],     "group": "Text"},
            {"id": "fill_g",       "label": "Fill G",        "type": "float", "min": 0,  "max": 1,   "default": s.color[1],     "group": "Text"},
            {"id": "fill_b",       "label": "Fill B",        "type": "float", "min": 0,  "max": 1,   "default": s.color[2],     "group": "Text"},
            {"id": "fill_a",       "label": "Fill A",        "type": "float", "min": 0,  "max": 1,   "default": s.color[3],     "group": "Text"},
        ]

    elif isinstance(clip, ShapeClip):
        s      = clip.style
        fill   = s.fillColor   or [0.4, 0.4, 1.0, 1.0]
        stroke = s.strokeColor or [1.0, 1.0, 1.0, 1.0]
        base += [
            {"id": "shape_w",  "label": "Width",        "type": "float", "min": 1, "max": 3840, "default": s.width,       "group": "Shape"},
            {"id": "shape_h",  "label": "Height",       "type": "float", "min": 1, "max": 2160, "default": s.height,      "group": "Shape"},
            {"id": "fill_r",   "label": "Fill R",       "type": "float", "min": 0, "max": 1,    "default": fill[0],       "group": "Shape"},
            {"id": "fill_g",   "label": "Fill G",       "type": "float", "min": 0, "max": 1,    "default": fill[1],       "group": "Shape"},
            {"id": "fill_b",   "label": "Fill B",       "type": "float", "min": 0, "max": 1,    "default": fill[2],       "group": "Shape"},
            {"id": "fill_a",   "label": "Fill A",       "type": "float", "min": 0, "max": 1,    "default": fill[3],       "group": "Shape"},
            {"id": "stroke_r", "label": "Stroke R",     "type": "float", "min": 0, "max": 1,    "default": stroke[0],     "group": "Shape"},
            {"id": "stroke_g", "label": "Stroke G",     "type": "float", "min": 0, "max": 1,    "default": stroke[1],     "group": "Shape"},
            {"id": "stroke_b", "label": "Stroke B",     "type": "float", "min": 0, "max": 1,    "default": stroke[2],     "group": "Shape"},
            {"id": "stroke_w", "label": "Stroke Width", "type": "float", "min": 0, "max": 50,   "default": s.strokeWidth, "group": "Shape"},
        ]

    elif isinstance(clip, PenClip):
        s  = clip.style
        sc = s.strokeColor if hasattr(s, 'strokeColor') else [1.0, 1.0, 1.0, 1.0]
        fc = s.fillColor   if hasattr(s, 'fillColor')   else [0.0, 0.0, 0.0, 0.0]
        base += [
            {"id": "stroke_r", "label": "Stroke R",     "type": "float", "min": 0, "max": 1,  "default": sc[0],         "group": "Path"},
            {"id": "stroke_g", "label": "Stroke G",     "type": "float", "min": 0, "max": 1,  "default": sc[1],         "group": "Path"},
            {"id": "stroke_b", "label": "Stroke B",     "type": "float", "min": 0, "max": 1,  "default": sc[2],         "group": "Path"},
            {"id": "stroke_w", "label": "Stroke Width", "type": "float", "min": 0, "max": 50, "default": s.strokeWidth, "group": "Path"},
            {"id": "fill_a",   "label": "Fill Alpha",   "type": "float", "min": 0, "max": 1,  "default": fc[3],         "group": "Path"},
        ]

    return base


class ParamValueBody(BaseModel):
    value: float
    frame: int = -1   # if >= 0, set as keyframe at this frame


class KeyframeBody(BaseModel):
    frame:        int
    value:        float
    interp:       str = "linear"
    handle_in_f:  float = -5.0
    handle_in_v:  float =  0.0
    handle_out_f: float =  5.0
    handle_out_v: float =  0.0


@app.get("/clips/{clipId}/params")
def getClipParams(clipId: str, frame: int = 0):
    """Return all inspectable params + current values for a clip."""
    clip, _ = _find_clip(clipId)
    schema   = _clip_param_schema(clip)
    rows     = []
    for p in schema:
        ap = _get_or_create_anim(clip, p["id"], p["default"])
        value        = ap.evaluate(frame) if ap.is_animated() else p["default"]
        rows.append({
            "id":          p["id"],
            "label":       p["label"],
            "type":        p["type"],
            "min":         p["min"],
            "max":         p["max"],
            "default":     p["default"],
            "group":       p["group"],
            "value":       value,
            "isAnimated":  ap.is_animated(),
            "hasKeyframe": ap.has_keyframe_at(frame),
            "keyframes":   ap.all_keyframe_frames(),
        })
    return {
        "clipId": clipId,
        "clipType": type(clip).__name__,
        "startFrame": clip.startFrame,
        "duration":   clip.duration,
        "params": rows,
    }


@app.post("/clips/{clipId}/params/{key}")
def setClipParam(clipId: str, key: str, body: ParamValueBody):
    """Set a static value or add a keyframe."""
    clip, _ = _find_clip(clipId)
    schema   = _clip_param_schema(clip)
    p_def    = next((p for p in schema if p["id"] == key), None)
    if p_def is None:
        raise HTTPException(404, f"Unknown param {key!r}")

    ap = _get_or_create_anim(clip, key, p_def["default"])
    if body.frame >= 0:
        print(f"[setClipParam] clipId={clipId[:8]} key={key!r} frame={body.frame} value={body.value} (keyframe)")
        ap.add_keyframe(body.frame, body.value, Interp.linear)
    else:
        print(f"[setClipParam] clipId={clipId[:8]} key={key!r} value={body.value} (base)")
        ap.set_base(body.value)
        # Apply immediately so render on same frame picks up the change
        clip.applyParam(key, body.value)
        # Clear frame cache guard so evaluateAll re-runs on next render
        if hasattr(clip, '_lastFrame'):
            clip._lastFrame = -1

    return {"status": "ok", "key": key, "value": body.value,
            "isAnimated": ap.is_animated()}


@app.post("/clips/{clipId}/keyframes/{key}")
def addKeyframe(clipId: str, key: str, body: KeyframeBody):
    clip, _ = _find_clip(clipId)
    schema   = _clip_param_schema(clip)
    p_def    = next((p for p in schema if p["id"] == key), None)
    if p_def is None:
        raise HTTPException(404, f"Unknown param {key!r}")

    ap = _get_or_create_anim(clip, key, p_def["default"])
    kf = KF(
        frame=body.frame, value=body.value,
        interp=Interp(body.interp),
        handle_in_f=body.handle_in_f,  handle_in_v=body.handle_in_v,
        handle_out_f=body.handle_out_f, handle_out_v=body.handle_out_v,
    )
    # For scalar params, add to component 0 only; vec params get single-value per component
    ap._tracks[0].add(kf)
    return {"status": "ok", "frames": ap.all_keyframe_frames()}


@app.get("/clips/{clipId}/keyframes/{key}")
def listKeyframes(clipId: str, key: str):
    clip, _ = _find_clip(clipId)
    if not hasattr(clip, '_anim_params') or key not in clip._anim_params:
        return {"frames": [], "allFrames": [], "vecType": "float"}
    ap = clip._anim_params[key]
    return {
        "frames":     ap.keyframes_for_component(0),
        "allFrames":  ap.all_keyframe_frames(),
        "vecType":    ap.to_schema_type() if hasattr(ap, 'to_schema_type') else "float",
        "components": ap.components if hasattr(ap, 'components') else 1,
    }


class MoveKeyframeBody(BaseModel):
    from_frame: int
    to_frame:   int


@app.post("/clips/{clipId}/keyframes/{key}/move")
def moveKeyframe(clipId: str, key: str, body: MoveKeyframeBody):
    """Move a keyframe from one frame position to another."""
    clip, _ = _find_clip(clipId)
    if not hasattr(clip, '_anim_params') or key not in clip._anim_params:
        raise HTTPException(404, "No keyframes on this param")
    ap = clip._anim_params[key]
    moved = ap.move_keyframe(body.from_frame, body.to_frame)
    if not moved:
        raise HTTPException(404, f"No keyframe at frame {body.from_frame}")
    return {"status": "ok", "frames": ap.all_keyframe_frames()}


@app.delete("/clips/{clipId}/keyframes/{key}/{frame}")
def removeKeyframe(clipId: str, key: str, frame: int):
    clip, _ = _find_clip(clipId)
    if not hasattr(clip, '_anim_params') or key not in clip._anim_params:
        raise HTTPException(404, "No keyframes on this param")
    removed = clip._anim_params[key].remove_keyframe(frame)
    if not removed:
        raise HTTPException(404, f"No keyframe at frame {frame}")
    return {"status": "ok"}


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
