from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.state import engine

router = APIRouter()


class TransitionAddRequest(BaseModel):
    typeId: str
    duration: int = 30
    clipA_id: str
    clipB_id: str
    trackId:  str | None = None


class TransitionPatchRequest(BaseModel):
    duration: int | None = None
    typeId: str | None = None
    params: dict | None = None


def _active_tl():
    tl = engine.activeTimeline if engine else None
    if tl is None:
        raise HTTPException(503, "No active timeline")
    return tl


@router.get("/transitions/catalog")
def transitionsCatalog():
    from backend.timeline.transitions.transition import TRANSITION_CATALOG
    return {"transitions": TRANSITION_CATALOG}


@router.post("/transitions")
def addTransition(req: TransitionAddRequest):
    from backend.timeline.transitions.transition import Transition
    tl = _active_tl()
    clipA, _ = tl.findClip(req.clipA_id)
    clipB, _ = tl.findClip(req.clipB_id)
    if clipA is None:
        raise HTTPException(404, f"Clip A '{req.clipA_id}' not found")
    if clipB is None:
        raise HTTPException(404, f"Clip B '{req.clipB_id}' not found")
    tr = Transition(typeId=req.typeId, duration=req.duration,
                    clipA_id=req.clipA_id, clipB_id=req.clipB_id)
    tl.addTransition(tr)
    return tr.toDict()


@router.get("/tracks/{trackId}/transitions")
def listTransitions(trackId: str):
    tl = engine.activeTimeline if engine else None
    if tl is None:
        return {"transitions": []}
    return {"transitions": [t.toDict() for t in tl.getTransitionsForTrack(trackId)]}


@router.get("/timeline/transitions")
def listAllTransitions():
    tl = engine.activeTimeline if engine else None
    if tl is None:
        return {"transitions": []}
    return {"transitions": [t.toDict() for t in tl.transitions]}


@router.patch("/transitions/{transId}")
def patchTransition(transId: str, req: TransitionPatchRequest):
    tl = _active_tl()
    for tr in tl.transitions:
        if tr.transId == transId:
            if req.duration is not None:
                tr.duration = max(1, req.duration)
            if req.typeId is not None:
                tr.typeId = req.typeId
            if req.params:
                for k, v in req.params.items():
                    tr.setParam(k, v)
            return tr.toDict()
    raise HTTPException(404, f"Transition {transId!r} not found")


@router.delete("/transitions/{transId}")
def deleteTransition(transId: str):
    tl = _active_tl()
    before = len(tl.transitions)
    tl.removeTransition(transId)
    if len(tl.transitions) < before:
        return {"status": "ok"}
    raise HTTPException(404, f"Transition {transId!r} not found")
