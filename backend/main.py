from __future__ import annotations
import asyncio
import socket
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from backend.engine.engine import Engine
from backend.timeline.tracks.videoTrack import VideoTrack
from backend.timeline.clips.videoClip import VideoClip

engine = Engine()

#   FastAPI app  
app = FastAPI(title="Fade Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Lifecycle  

@app.on_event("startup")
async def startup() -> None:
    """Create a default project and start the preview loop on startup."""
    engine.newProject()

    # Add a default video 
    vt = VideoTrack("Video 1")
    clip = VideoClip(startFrame=0, duration=300, color=(74, 144, 226, 255))
    vt.addClip(clip)
    if engine.activeTimeline:
        engine.activeTimeline.addTrack(vt)

    asyncio.create_task(engine.startPreviewLoop())


#   Project routes  

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


# Frame routes  

@app.get("/frame/{frame}")
def getFrame(frame: int):
   
    jpeg = engine.renderFrameJpeg(frame)
    return Response(content=jpeg, media_type="image/jpeg")


@app.get("/thumbnail/{frame}")
def getThumbnail(frame: int, w: int = 320, h: int = 180):
 
    jpeg = engine.renderThumbnail(frame, w, h)
    return Response(content=jpeg, media_type="image/jpeg")


# WebSocket preview stream  

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
    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=port,
        log_level="warning",
        reload=False,
    )
