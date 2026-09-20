from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.state import engine
from backend.events import notify as _notify

router = APIRouter()


class SeekRequest(BaseModel):
    frame: int


class SpeedRequest(BaseModel):
    speed: float


class InOutRequest(BaseModel):
    inPoint: int | None = None
    outPoint: int | None = None


def _playback_state() -> dict:
    """Snapshot of current playback state for SSE push."""
    prj = engine.project
    return {
        "playing": engine._playing,
        "frame": engine.currentFrame,
        "fps": prj.fps if prj else 30.0,
        "totalFrames": prj.totalFrame if prj else 1800,
        "speed": engine._speed,
        "inPoint": engine._inPoint,
        "outPoint": engine._outPoint,
    }


@router.post("/playback/play")
def play():
    engine.play()
    _notify("playback", _playback_state())
    return {"playing": True}


@router.post("/playback/pause")
def pause():
    engine.pause()
    _notify("playback", _playback_state())
    return {"playing": False}


@router.post("/playback/seek")
def seek(req: SeekRequest):
    engine.seek(req.frame)
    _notify("playback", _playback_state())
    return {"frame": engine.currentFrame}


@router.get("/playback/state")
def playbackState():
    prj = engine.project
    return {
        "frame": engine.currentFrame,
        "playing": engine._playing,
        "fps": prj.fps if prj else 30.0,
        "totalFrames": prj.totalFrame if prj else 1800,
        "speed": engine._speed,
        "inPoint": engine._inPoint,
        "outPoint": engine._outPoint,
    }


@router.post("/playback/speed")
def setPlaybackSpeed(req: SpeedRequest):
    engine.setSpeed(req.speed)
    _notify("playback", _playback_state())
    return {"speed": engine._speed}


@router.post("/playback/inout")
def setInOut(req: InOutRequest):
    engine.setInPoint(req.inPoint)
    engine.setOutPoint(req.outPoint)
    _notify("playback", _playback_state())
    return {"inPoint": engine._inPoint, "outPoint": engine._outPoint}
