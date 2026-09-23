import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.state import engine, _clipTrackMap
from backend.timeline.tracks.videoTrack import VideoTrack
from backend.timeline.tracks.audioTrack import AudioTrack

router = APIRouter()


def _comp_clips_in_timeline(tl) -> list[str]:
    from backend.timeline.clips.compClip import CompClip
    return [clip.compId for track in tl.tracks for clip in track.clips if isinstance(clip, CompClip)]


def _has_cycle(start_id: str, target_id: str, visited: set | None = None) -> bool:
    if visited is None:
        visited = set()
    if start_id == target_id:
        return True
    if start_id in visited:
        return False
    visited.add(start_id)
    tl = engine.getTimeline(start_id)
    if tl is None:
        return False
    for child_id in _comp_clips_in_timeline(tl):
        if _has_cycle(child_id, target_id, visited):
            return True
    return False


def _ensure_comp_tracks(tl) -> None:
    if tl.tracks:
        return
    tl.tracks.append(VideoTrack(name="Video 1"))
    # Image comps are purely visual — no audio track
    if getattr(tl, "kind", "video") != "image":
        tl.tracks.append(AudioTrack(name="Audio 1"))


def _active_timeline():
    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(400, "No active timeline")
    return tl


def _top_empty_track(startFrame: int, duration: int):
    tl = _active_timeline()
    endFrame = startFrame + duration
    video_tracks = [t for t in tl.tracks if not getattr(t, 'isAudio', lambda: False)()]
    for track in reversed(video_tracks):
        overlaps = any(
            not (clip.startFrame >= endFrame or clip.startFrame + clip.duration <= startFrame)
            for clip in getattr(track, 'clips', [])
        )
        if not overlaps:
            return track
    new_track = VideoTrack(f"Video {len(video_tracks) + 1}")
    tl.addTrack(new_track)
    return new_track


class CreateCompRequest(BaseModel):
    name: str = "Composition"
    width: int = 1920
    height: int = 1080
    fps: float = 30.0
    totalFrames: int = 900
    kind : str = "video"


class CompRenameRequest(BaseModel):
    name: str


class AddCompClipRequest(BaseModel):
    compId: str
    trackIndex: int | None = None
    startFrame: int = 0
    duration: int = 90
    mediaOffset: int = 0


@router.get("/comps")
def listComps():
    if engine.project is None:
        return {"comps": []}
    root_id  = engine.project.timelines[0].timelineId if engine.project.timelines else ""
    proj_w = engine.project.width
    proj_h = engine.project.height
    proj_fps = engine.project.fps
    comps = []
    for tl in engine.project.timelines:
        comps.append({
            "compId": tl.timelineId,
            "name": tl.name,
            "kind" :getattr(tl , "kind" , "video"),
            "isRoot": tl.timelineId == root_id,
            "width": getattr(tl, "width", proj_w),
            "height": getattr(tl, "height", proj_h),
            "fps": getattr(tl, "fps", proj_fps),
            "totalFrames": getattr(tl, "totalFrames", 900),
            "trackCount": len(tl.tracks),
            "clipCount": sum(len(t.clips) for t in tl.tracks),
        })
    return {"comps": comps}


@router.post("/comps")
def createComp(req: CreateCompRequest):
    if engine.project is None:
        raise HTTPException(400, "No active project")
    comp = engine.createComposition(name=req.name, width=req.width, height=req.height,
                                    fps=req.fps, total_frames=req.totalFrames)

    comp.kind = req.kind
    from backend.events import notify; notify("comps")
    return {
        "compId": comp.timelineId, "name": comp.name,
        "kind" : comp.kind ,
        "width": getattr(comp, "width", req.width),
        "height": getattr(comp, "height", req.height),
        "fps": getattr(comp, "fps", req.fps),
        "totalFrames": getattr(comp, "totalFrames", req.totalFrames),
        "isRoot": False, "trackCount": 0, "clipCount": 0,
    }


@router.delete("/comps/{compId}")
def deleteComp(compId: str):
    ok = engine.deleteComposition(compId)
    if not ok:
        raise HTTPException(404, f"Composition {compId!r} not found or is root")
    from backend.events import notify; notify("comps")
    return {"status": "ok"}


@router.patch("/comps/{compId}/rename")
def renameCompRoute(compId: str, req: CompRenameRequest):
    tl = engine.getTimeline(compId)
    if tl is None:
        raise HTTPException(404, f"Composition {compId!r} not found")
    name = req.name.strip()
    if not name:
        raise HTTPException(400, "Name cannot be empty")
    tl.name = name
    from backend.events import notify; notify("comps")
    return {"compId": compId, "name": name}


@router.post("/comps/{compId}/activate")
def activateComp(compId: str):
    if engine.project is None:
        raise HTTPException(400, "No active project")
    if compId == "root":
        engine.setActiveComp(None)
        root = engine.project.timelines[0] if engine.project.timelines else None
        return {"activeCompId": root.timelineId if root else None}
    tl = engine.getTimeline(compId)
    if tl is None:
        raise HTTPException(404, f"Composition {compId!r} not found")
    engine.setActiveComp(compId)
    return {"activeCompId": compId}


@router.post("/comps/{compId}/ensure-tracks")
def ensureCompTracks(compId: str):
    tl = engine.getTimeline(compId)
    if tl is None:
        raise HTTPException(404, f"Composition {compId!r} not found")
    _ensure_comp_tracks(tl)
    return {"trackCount": len(tl.tracks)}


@router.get("/comps/{compId}/state")
def getCompState(compId: str):
    tl = engine.getTimeline(compId)
    if tl is None:
        raise HTTPException(404, f"Composition {compId!r} not found")
    _ensure_comp_tracks(tl)
    comp_fps   = getattr(tl, "fps", engine.project.fps if engine.project else 30.0)
    comp_total = getattr(tl, "totalFrames", None) or max(
        (max((c.startFrame + c.duration for c in t.clips), default=0) for t in tl.tracks),
        default=900
    )
    tracks_out = []
    for track in tl.tracks:
        clips_out = []
        for clip in track.clips:
            clips_out.append({
                "clipId": getattr(clip, "clipId", ""),
                "type": getattr(clip, "CLIP_TYPE", getattr(clip, "clipType", "video")),
                "name": getattr(clip, "name", getattr(clip, "compId", getattr(clip, "assetId", "Clip"))),
                "startFrame": getattr(clip, "startFrame", 0),
                "duration": getattr(clip, "duration", 90),
                "assetId": getattr(clip, "assetId", None),
                "compId": getattr(clip, "compId", None),
            })
        tracks_out.append({
            "trackId": track.trackId, "name": track.name,
            "type": getattr(track, "TRACK_TYPE", "video"),
            "muted": track.muted,
            "solo": getattr(track, "solo", False),
            "locked": track.locked,
            "clips": clips_out,
        })
    return {"timelineId": tl.timelineId, "name": tl.name,
            "tracks": tracks_out, "totalFrames": comp_total, "fps": comp_fps}


@router.post("/clips/comp")
def addCompClip(req: AddCompClipRequest):
    from backend.timeline.clips.compClip import CompClip
    if engine.project is None:
        raise HTTPException(400, "No active project")
    tl = _active_timeline()
    if req.compId == tl.timelineId:
        raise HTTPException(400, "Cannot add a composition inside itself")
    if _has_cycle(req.compId, tl.timelineId):
        raise HTTPException(400, f"Cycle detected")
    track = _top_empty_track(req.startFrame, req.duration)
    if req.trackIndex is not None and 0 <= req.trackIndex < len(tl.tracks):
        track = tl.tracks[req.trackIndex]
    clip = CompClip(clipId=str(uuid.uuid4()), startFrame=req.startFrame,
                    duration=req.duration, compId=req.compId, mediaOffset=req.mediaOffset)
    track.addClip(clip)
    _clipTrackMap[clip.clipId] = tl.tracks.index(track)
    from backend.events import notify; notify("timeline")
    return clip.toDict()



class AddLayerRequest(BaseModel):
    name:str = "Layer"
    element:dict | None = None


class UpdateLayerRequest(BaseModel):
    name:str | None = None
    visible : bool | None = None
    locked : bool | None = None 
    opacity : float | None = None
    blendMode : str | None = None
    z_index : int | None = None
    element : dict | None = None


class ReorderLayerRequest(BaseModel):
    layerIds : list[str]


@router.get("/comps/{compId}/layers")
def getLayers(compId : str):
    from backend.timeline.tracks.imageLayer import imageLayer
    tl = engine.getTimeline(compId)
    if tl is None:
        raise HTTPException(404,f"comp {CompId!r} not found")

    if getattr(tl ,  "kind","video") != "image":
        raise HTTPException(400, "Not an image compositor")

    layers = sorted([t for t in tl.tracks if isinstance(t , imageLayer)],
    key=lambda l : l.z_index , reverse=True
    )
    return {"layers":[l.toDict() for l in layers]}

@router.post("/comp/{compId}/layers")
def addLayer(compId:str , req:AddLayerRequest):
    from backend.timeline.tracks.imageLayer import imageLayer
    t1 = engine.getTimeline(compId)
    if t1 is None:
        raise HTTPException(404,f"Comp {compId!r} not found ") 
    
    if getattr(t1 , "kind" , "video") != "image":
        raise HTTPException(400 , "not an image composition")

    lyr = imageLayer(name=req.name)
    lyr.zIndex = len(t1.tracks)
    lyr.element = req.element
    t1.tracks(lyr)
    from backend.events import notify ; notify("timeline")
    return lyr.toDict()

@router.patch('/comps/{compId}/layers/{layerId}')
def updateLayer(compId:str , layerId:str , req:UpdateLayerRequest):
    from backend.timeline.tracks.imageLayer import imageLayer 
    t1 = engine.getTimeline(compId)

    if t1 is None:
        raise HTTPException(404 , f"comp {compId!r} not found")
    
    lyr = next((t for t in t1.tracks if isinstance(t , imageLayer) and (t.trackId == layerId)) , None )

    if lyr is None:
        raise HTTPException(404 , f"Layer {layerId!r} not found ")

    if req.name is not None: lyr.name = req.name
    if req.visible is not None: lyr.visible = req.visible
    if req.locked is not None: lyr.locked = req.locked
    if req.opacity is not None: lyr.opacity = req.opacity
    if req.blendMode is not None: lyr.blendMode = req.blendMode
    if req.z_index is not None: lyr.z_index = req.z_index
    if req.element is not None: lyr.element = req.element
    from backend.events import notify; notify("timeline")
    return lyr.toDict()
    