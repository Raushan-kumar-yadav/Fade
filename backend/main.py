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
        if track.getClip(clipId):
            # Unregister from scheduler to free frame cache
            if engine.scheduler:
                engine.scheduler.unregisterClip(clipId)
            track.removeClip(clipId)
            _clipTrackMap.pop(clipId, None)
            return {"status": "ok"}

    raise HTTPException(404, f"Clip {clipId!r} not found")


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


@app.post("/playback/seek")
def seek(frame: int):
    engine.seek(frame)
    return {"frame": engine.currentFrame}


@app.get("/playback/state")
def playbackState():
    return {
        "frame":   engine.currentFrame,
        "playing": engine._playing,
        "fps":     engine.project.fps if engine.project else 30.0,
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
