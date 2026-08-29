from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.state import engine

router = APIRouter()


class SeekRequest(BaseModel):
    frame: int


class SpeedRequest(BaseModel):
    speed: float


class InOutRequest(BaseModel):
    inPoint: int | None = None
    outPoint: int | None = None


@router.post("/playback/play")
def play():
    engine.play()
    return {"playing": True}


@router.post("/playback/pause")
def pause():
    engine.pause()
    return {"playing": False}


@router.post("/playback/seek")
def seek(req: SeekRequest):
    engine.seek(req.frame)
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
    return {"speed": engine._speed}


@router.post("/playback/inout")
def setInOut(req: InOutRequest):
    engine.setInPoint(req.inPoint)
    engine.setOutPoint(req.outPoint)
    return {"inPoint": engine._inPoint, "outPoint": engine._outPoint}
