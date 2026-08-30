import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.state import engine, _library, _clipTrackMap
from backend.events import notify
from backend.timeline.clips.textClip  import TextClip,  TextStyle,  MaskLayer
from backend.timeline.clips.shapeClip import ShapeClip, ShapeStyle
from backend.timeline.clips.penClip   import PenClip,   BezierPoint
from backend.timeline.clips.animEngine import AnimParam, Interp, Keyframe as KF
from backend.timeline.tracks.videoTrack import VideoTrack

router = APIRouter()


#   helpers  

def _active_timeline():
    """Return the UI-active timeline (may be a comp). Only use for read operations."""
    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(400, "No active timeline")
    return tl


def _resolve_timeline(comp_id: str | None = None):
    """Resolve which timeline to target for clip creation.

    - comp_id=None  → always root/main timeline (safe default; never affected by which
                       comp tab the user has open in the UI).
    - comp_id=<id>  → the specific comp timeline with that id, so the agent can
                       explicitly target any comp without the user having to open it.

    This is the single place all clip-creation routes should call.
    """
    if comp_id:
        tl = engine.getTimeline(comp_id)
        if tl is None:
            raise HTTPException(404, f"Comp timeline {comp_id!r} not found")
        return tl
    tl = engine.rootTimeline
    if tl is None:
        raise HTTPException(400, "No active timeline")
    return tl


def _find_clip(clipId: str):
    """Search every timeline in the project for the clip."""
    if engine.project:
        for timeline in engine.project.timelines:
            for track in timeline.tracks:
                for clip in track.clips:
                    if clip.clipId == clipId:
                        return clip, track
    raise HTTPException(404, f"Clip {clipId!r} not found")


def _top_empty_track(startFrame: int, duration: int, tl=None):
    """Find or create a non-overlapping video track in `tl` (defaults to root timeline)."""
    if tl is None:
        tl = _resolve_timeline()
    endFrame = startFrame + duration
    video_tracks = [t for t in tl.tracks if not getattr(t, 'isAudio', lambda: False)()]
    for track in reversed(video_tracks):
        overlaps = any(
            not (clip.startFrame >= endFrame or clip.startFrame + clip.duration <= startFrame)
            for clip in getattr(track, 'clips', [])
        )
        if not overlaps:
            return track
    name = f"Video {len(video_tracks) + 1}"
    new_track = VideoTrack(name)
    tl.addTrack(new_track)
    return new_track


def _get_or_create_anim(clip, key: str, base_value) -> AnimParam:
    if not hasattr(clip, '_anim_params'):
        clip._anim_params = {}
    if key not in clip._anim_params:
        clip._anim_params[key] = AnimParam(base_value)
    return clip._anim_params[key]


def _clip_param_schema(clip) -> list:
    t = clip.transform
    px, py = t.position.get()
    sx, sy = t.scale.get()
    ax, ay = t.anchor.get()
    base = [
        {"id": "opacity",    "label": "Opacity", "type": "float", "min": 0, "max": 1, "default": round(t.opacity.get(), 4),   "group": "Transform"},
        {"id": "blend_mode", "label": "Blend Mode", "type": "int",   "min": 0, "max": 11,   "default": (lambda bm: int(bm.get()) if hasattr(bm, "get") else int(bm) if bm else 0)(getattr(clip, "blendMode", 0)), "group": "Transform"},
        {"id": "pos_x", "label": "Position X", "type": "float", "min": -3840,"max": 3840, "default": round(px, 2), "group": "Transform"},
        {"id": "pos_y", "label": "Position Y", "type": "float", "min": -2160,"max": 2160, "default": round(py, 2), "group": "Transform"},
        {"id": "scale_x", "label": "Scale X", "type": "float", "min": 0, "max": 10, "default": round(sx, 4), "group": "Transform"},
        {"id": "scale_y", "label": "Scale Y", "type": "float", "min": 0, "max": 10, "default": round(sy, 4), "group": "Transform"},
        {"id": "rotation", "label": "Rotation",   "type": "float", "min": -360, "max": 360,  "default": round(t.rotation.get(), 2),  "group": "Transform"},
        {"id": "anchor_x", "label": "Anchor X", "type": "float", "min": -1920,"max": 1920, "default": round(ax, 2), "group": "Transform"},
        {"id": "anchor_y", "label": "Anchor Y", "type": "float", "min": -1080,"max": 1080, "default": round(ay, 2), "group": "Transform"},
    ]
    if isinstance(clip, TextClip):
        s = clip.style
        base += [
            {"id": "font_size",   "label": "Font Size",   "type": "float", "min": 4,   "max": 400, "default": s.fontSize,      "group": "Text"},
            {"id": "tracking",    "label": "Tracking",    "type": "float", "min": -20, "max": 100, "default": s.letterSpacing, "group": "Text"},
            {"id": "line_height", "label": "Line Height", "type": "float", "min": 0.5, "max": 4,   "default": s.lineHeight,    "group": "Text"},
            {"id": "fill_r", "label": "Fill R", "type": "float", "min": 0, "max": 1, "default": s.color[0], "group": "Text"},
            {"id": "fill_g", "label": "Fill G", "type": "float", "min": 0, "max": 1, "default": s.color[1], "group": "Text"},
            {"id": "fill_b", "label": "Fill B", "type": "float", "min": 0, "max": 1, "default": s.color[2], "group": "Text"},
            {"id": "fill_a", "label": "Fill A", "type": "float", "min": 0, "max": 1, "default": s.color[3], "group": "Text"},
        ]
    elif isinstance(clip, ShapeClip):
        s      = clip.style
        fill   = s.fillColor   or [0.4, 0.4, 1.0, 1.0]
        stroke = s.strokeColor or [1.0, 1.0, 1.0, 1.0]
        base += [
            {"id": "shape_w", "label": "Width", "type": "float", "min": 1, "max": 3840, "default": s.width, "group": "Shape"},
            {"id": "shape_h", "label": "Height", "type": "float", "min": 1, "max": 2160, "default": s.height, "group": "Shape"},
            {"id": "fill_r", "label": "Fill R", "type": "float", "min": 0, "max": 1, "default": fill[0], "group": "Shape"},
            {"id": "fill_g", "label": "Fill G", "type": "float", "min": 0, "max": 1, "default": fill[1], "group": "Shape"},
            {"id": "fill_b", "label": "Fill B", "type": "float", "min": 0, "max": 1, "default": fill[2], "group": "Shape"},
            {"id": "fill_a",   "label": "Fill A", "type": "float", "min": 0, "max": 1, "default": fill[3], "group": "Shape"},
            {"id": "stroke_r", "label": "Stroke R", "type": "float", "min": 0, "max": 1, "default": stroke[0], "group": "Shape"},
            {"id": "stroke_g", "label": "Stroke G", "type": "float", "min": 0, "max": 1, "default": stroke[1], "group": "Shape"},
            {"id": "stroke_b", "label": "Stroke B", "type": "float", "min": 0, "max": 1, "default": stroke[2], "group": "Shape"},
            {"id": "stroke_w", "label": "Stroke Width", "type": "float", "min": 0, "max": 50, "default": s.strokeWidth, "group": "Shape"},
        ]
    elif isinstance(clip, PenClip):
        s  = clip.style
        sc = s.strokeColor if hasattr(s, 'strokeColor') else [1.0, 1.0, 1.0, 1.0]
        fc = s.fillColor   if hasattr(s, 'fillColor')   else [0.0, 0.0, 0.0, 0.0]
        base += [
            {"id": "stroke_r", "label": "Stroke R", "type": "float", "min": 0, "max": 1,  "default": sc[0], "group": "Path"},
            {"id": "stroke_g", "label": "Stroke G", "type": "float", "min": 0, "max": 1,  "default": sc[1], "group": "Path"},
            {"id": "stroke_b", "label": "Stroke B", "type": "float", "min": 0, "max": 1,  "default": sc[2], "group": "Path"},
            {"id": "stroke_w", "label": "Stroke Width", "type": "float", "min": 0, "max": 50, "default": s.strokeWidth, "group": "Path"},
            {"id": "fill_a",   "label": "Fill Alpha",   "type": "float", "min": 0, "max": 1,  "default": fc[3], "group": "Path"},
        ]
    return base


#   Text  

class TextClipRequest(BaseModel):
    trackIndex:  int | None = None
    startFrame:  int = 0
    duration:    int = 150
    text: str = "New Text"      # promoted
    fontFamily: str = "Arial"   # promoted
    style:       dict = {}       # full style dict override
    compId: str | None = None   # target comp; None = root/main timeline


class TextPatchRequest(BaseModel):
    text: str | None = None       # direct text content update
    style: dict | None = None
    transform: dict | None = None


@router.post("/clips/text")
def addTextClip(req: TextClipRequest):
    tl    = _resolve_timeline(req.compId)
    track = _top_empty_track(req.startFrame, req.duration, tl)
    # Merge: promoted fields take priority over style dict
    merged_style = {"fontFamily": req.fontFamily, **req.style}
    clip  = TextClip(clipId=str(uuid.uuid4()), startFrame=req.startFrame,
                     duration=req.duration, style=TextStyle.fromDict(merged_style))
    # Always apply the promoted text field directly
    clip.style.text = req.text
    track.addClip(clip)
    _clipTrackMap[clip.clipId] = tl.tracks.index(track)
    notify("timeline")
    return clip.toDict()


@router.get("/clips/text/{clipId}")
def getTextClip(clipId: str):
    clip, _ = _find_clip(clipId)
    if not isinstance(clip, TextClip):
        raise HTTPException(404, "Not a text clip")
    return clip.toDict()


@router.patch("/clips/text/{clipId}")
def updateTextClip(clipId: str, req: TextPatchRequest):
    clip, _ = _find_clip(clipId)
    if not isinstance(clip, TextClip):
        raise HTTPException(400, "Not a text clip")
    if req.text is not None:
        clip.style.text = req.text           # direct text update
    if req.style:
        for k, v in req.style.items():
            if hasattr(clip.style, k):
                setattr(clip.style, k, v)
    if req.transform:
        from backend.animation.transform import Transform
        clip.transform = Transform.fromDict(req.transform)
    notify("timeline")
    notify("render")    # signal viewport to re-render current frame immediately
    return clip.toDict()


# Shape  

class ShapeClipRequest(BaseModel):
    startFrame: int   = 0
    duration: int   = 150
    style: dict  = {}
    x: float = 960.0
    y: float = 540.0
    compId: str | None = None   # target comp; None = root/main timeline


class ShapePatchRequest(BaseModel):
    style: dict | None = None
    transform: dict | None = None


@router.post("/clips/shape")
def addShapeClip(req: ShapeClipRequest):
    tl    = _resolve_timeline(req.compId)
    track = _top_empty_track(req.startFrame, req.duration, tl)
    clip  = ShapeClip(clipId=str(uuid.uuid4()), startFrame=req.startFrame,
                      duration=req.duration, style=ShapeStyle.fromDict(req.style))
    clip.transform.position.setBase(req.x, req.y)
    track.addClip(clip)
    _clipTrackMap[clip.clipId] = tl.tracks.index(track)
    notify("timeline")
    return clip.toDict()


@router.patch("/clips/shape/{clipId}")
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


#   Pen  

class PenClipRequest(BaseModel):
    startFrame: int  = 0
    duration: int  = 150
    isClosed: bool = False
    points: list = []
    style: dict = {}
    compId: str | None = None   # target comp; None = root/main timeline


class PenPointsRequest(BaseModel):
    points: list       = []
    isClosed: bool | None = None


class PathKeyframeRequest(BaseModel):
    frame:  int = 0
    interp: str = "bezier"


@router.post("/clips/pen")
def addPenClip(req: PenClipRequest):
    tl    = _resolve_timeline(req.compId)
    track = _top_empty_track(req.startFrame, req.duration, tl)
    clip  = PenClip(clipId=str(uuid.uuid4()), startFrame=req.startFrame,
                    duration=req.duration, isClosed=req.isClosed,
                    style=ShapeStyle.fromDict(req.style))
    for p in req.points:
        clip.addPoint(x=float(p.get("x",0)), y=float(p.get("y",0)),
                      inX=float(p.get("inX",0)), inY=float(p.get("inY",0)),
                      outX=float(p.get("outX",0)), outY=float(p.get("outY",0)))
    track.addClip(clip)
    _clipTrackMap[clip.clipId] = tl.tracks.index(track)
    notify("timeline")
    return clip.toDict()


@router.patch("/clips/pen/{clipId}/points")
def updatePenPoints(clipId: str, req: PenPointsRequest):
    clip, _ = _find_clip(clipId)
    if not isinstance(clip, PenClip):
        raise HTTPException(400, "Not a pen clip")
    clip.shapePath.vertices.clear()
    for p in req.points:
        clip.addPoint(x=float(p.get("x",0)), y=float(p.get("y",0)),
                      inX=float(p.get("inX",0)), inY=float(p.get("inY",0)),
                      outX=float(p.get("outX",0)), outY=float(p.get("outY",0)))
    if req.isClosed is not None:
        clip.isClosed = req.isClosed
    return clip.toDict()


@router.post("/clips/pen/{clipId}/path-keyframe")
def addPenPathKeyframe(clipId: str, req: PathKeyframeRequest):
    from backend.animation.keyframe import Interpolation
    clip, _ = _find_clip(clipId)
    if not isinstance(clip, PenClip):
        raise HTTPException(400, "Not a pen clip")
    try:
        interp = Interpolation(req.interp)
    except ValueError:
        interp = Interpolation.Bezier
    clip._syncBase()
    clip.shapePath.addKeyframe(req.frame, interp=interp)
    return {"clipId": clipId, "frame": req.frame, "keyframes": clip.shapePath.track.frameIndex()}


@router.delete("/clips/pen/{clipId}/path-keyframe/{frame}")
def removePenPathKeyframe(clipId: str, frame: int):
    clip, _ = _find_clip(clipId)
    if not isinstance(clip, PenClip):
        raise HTTPException(400, "Not a pen clip")
    removed = clip.shapePath.removeKeyframe(frame)
    if not clip.shapePath.track.frameIndex():
        clip.shapePath.setAnimated(False)
    return {"removed": removed, "keyframes": clip.shapePath.track.frameIndex()}


#   Masks  

class MaskRequest(BaseModel):
    name: str   = "Mask"
    shape:    str   = "rect"
    mode: str   = "add"
    inverted: bool  = False
    feather:  float = 0.0
    opacity:  float = 1.0
    points: list  = []


class MaskPatchRequest(BaseModel):
    name: str   | None = None
    mode: str   | None = None
    inverted: bool  | None = None
    feather: float | None = None
    opacity:  float | None = None
    points: list  | None = None


@router.post("/clips/{clipId}/mask")
def addMask(clipId: str, req: MaskRequest):
    from backend.animation.animPath import PathVertex
    clip, _ = _find_clip(clipId)
    if not hasattr(clip, 'masks'):
        raise HTTPException(400, "Clip type does not support masks")
    mask = MaskLayer(maskId=str(uuid.uuid4()), name=req.name, shape=req.shape,
                     mode=req.mode, inverted=req.inverted)
    mask.feather.setBaseValue(req.feather)
    mask.opacity.setBaseValue(req.opacity)
    if req.points:
        verts = [PathVertex(x=float(p.get("x",0)), y=float(p.get("y",0)),
                            inX=float(p.get("inX",0)), inY=float(p.get("inY",0)),
                            outX=float(p.get("outX",0)), outY=float(p.get("outY",0)))
                 for p in req.points]
        mask.maskPath.setBase(verts, closed=True)
    clip.addMask(mask)
    return {"clipId": clipId, "maskId": mask.maskId, "masks": [m.toDict() for m in clip.masks]}


@router.patch("/clips/{clipId}/mask/{maskId}")
def updateMask(clipId: str, maskId: str, req: MaskPatchRequest):
    from backend.animation.animPath import PathVertex
    clip, _ = _find_clip(clipId)
    mask = getattr(clip, "getMask", lambda _: None)(maskId)
    if mask is None:
        raise HTTPException(404, f"Mask {maskId!r} not found")
    if req.name     is not None: mask.name = req.name
    if req.mode     is not None: mask.mode = req.mode
    if req.inverted is not None: mask.inverted = req.inverted
    if req.feather  is not None: mask.feather.setBaseValue(req.feather)
    if req.opacity  is not None: mask.opacity.setBaseValue(req.opacity)
    if req.points   is not None:
        verts = [PathVertex(x=float(p.get("x",0)), y=float(p.get("y",0)),
                            inX=float(p.get("inX",0)), inY=float(p.get("inY",0)),
                            outX=float(p.get("outX",0)), outY=float(p.get("outY",0)))
                 for p in req.points]
        mask.maskPath.setBase(verts)
    return clip.toDict()


@router.post("/clips/{clipId}/mask/{maskId}/path-keyframe")
def addMaskPathKeyframe(clipId: str, maskId: str, req: PathKeyframeRequest):
    from backend.animation.keyframe import Interpolation
    clip, _ = _find_clip(clipId)
    mask = getattr(clip, "getMask", lambda _: None)(maskId)
    if mask is None:
        raise HTTPException(404, f"Mask {maskId!r} not found")
    try:
        interp = Interpolation(req.interp)
    except ValueError:
        interp = Interpolation.Bezier
    mask.maskPath.addKeyframe(req.frame, interp=interp)
    return {"maskId": maskId, "frame": req.frame, "keyframes": mask.maskPath.track.frameIndex()}


@router.delete("/clips/{clipId}/mask/{maskId}/path-keyframe/{frame}")
def removeMaskPathKeyframe(clipId: str, maskId: str, frame: int):
    clip, _ = _find_clip(clipId)
    mask = getattr(clip, "getMask", lambda _: None)(maskId)
    if mask is None:
        raise HTTPException(404, f"Mask {maskId!r} not found")
    removed = mask.maskPath.removeKeyframe(frame)
    if not mask.maskPath.track.frameIndex():
        mask.maskPath.setAnimated(False)
    return {"removed": removed, "keyframes": mask.maskPath.track.frameIndex()}


@router.delete("/clips/{clipId}/mask/{maskId}")
def removeMask(clipId: str, maskId: str):
    clip, _ = _find_clip(clipId)
    removed = getattr(clip, "removeMask", lambda _: False)(maskId)
    if not removed:
        raise HTTPException(404, f"Mask {maskId!r} not found")
    return {"status": "ok", "clipId": clipId}


@router.get("/clips/{clipId}/masks")
def listMasks(clipId: str):
    clip, _ = _find_clip(clipId)
    return {
        "clipId": clipId,
        "masks": [
            {"maskId": m.maskId, "name": m.name, "shape": m.shape, "mode": m.mode,
             "inverted": m.inverted, "feather": m.feather, "opacity": m.opacity,
             "points": getattr(m, 'points', []), "pointCount": len(getattr(m, 'points', []))}
            for m in getattr(clip, 'masks', [])
        ],
    }


#   Selection  

import backend.state as _state


class SelectClipRequest(BaseModel):
    clipId: str | None = None
    # Multi-select: all currently selected clip IDs from the frontend
    selectedIds: list[str] | None = None


@router.post("/clips/select")
def selectClip(req: SelectClipRequest):
    _state._selected_clip_id = req.clipId
    if req.selectedIds is not None:
        _state._selected_clip_ids = set(req.selectedIds)
    elif req.clipId:
        _state._selected_clip_ids = {req.clipId}
    else:
        _state._selected_clip_ids = set()
    return {"selectedClipId": _state._selected_clip_id}


@router.get("/clips/selected")
def getSelectedClip():
    if not _state._selected_clip_id:
        return {"clip": None}
    try:
        clip, track = _find_clip(_state._selected_clip_id)
        # Search all timelines for the track — don't depend on which comp is active in UI
        tl = next(
            (tl for tl in (engine.project.timelines if engine.project else [])
             if track in tl.tracks),
            None
        )
        track_idx = tl.tracks.index(track) if tl and track in tl.tracks else -1
        return {"clip": {
            "clipId": clip.clipId, "trackIndex": track_idx,
            "startFrame": clip.startFrame, "duration": clip.duration,
            "type": type(clip).__name__, "effectCount": len(getattr(clip, "effects", [])),
        }}
    except Exception:
        return {"clip": None}


@router.get("/clips/selected-all")
def getSelectedClips():
    """Return all currently selected clips across all timelines."""
    results = []
    ids = _state._selected_clip_ids
    if not ids:
        # Fallback: single-select
        if _state._selected_clip_id:
            ids = {_state._selected_clip_id}
        else:
            return {"clips": []}
    try:
        timelines = engine.project.timelines if engine.project else []
        for tl in timelines:
            tl_id = getattr(tl, "compId", getattr(tl, "id", "root"))
            for track_idx, track in enumerate(tl.tracks):
                for clip in track.clips:
                    if clip.clipId not in ids:
                        continue
                    results.append({
                        "clipId":      clip.clipId,
                        "trackId":     track.trackId,
                        "trackIndex":  track_idx,
                        "compId":      tl_id,
                        "startFrame":  clip.startFrame,
                        "duration":    clip.duration,
                        "type":        type(clip).__name__,
                        "effectCount": len(getattr(clip, "effects", [])),
                    })
    except Exception:
        pass
    return {"clips": results}



class ParamValueBody(BaseModel):
    value: float
    frame: int = -1


class KeyframeBody(BaseModel):
    frame: int
    value: float
    interp: str   = "linear"
    handle_in_f:  float = -5.0
    handle_in_v:  float =  0.0
    handle_out_f: float =  5.0
    handle_out_v: float =  0.0


class MoveKeyframeBody(BaseModel):
    from_frame: int
    to_frame:   int


@router.get("/clips/{clipId}/params")
def getClipParams(clipId: str, frame: int = 0):
    clip, _ = _find_clip(clipId)
    schema   = _clip_param_schema(clip)
    rows     = []
    for p in schema:
        ap    = _get_or_create_anim(clip, p["id"], p["default"])
        value = ap.evaluate(frame) if ap.is_animated() else ap._base[0]
        rows.append({
            "id": p["id"], "label": p["label"], "type": p["type"],
            "min": p["min"], "max": p["max"], "default": p["default"],
            "group": p["group"], "value": value,
            "isAnimated": ap.is_animated(),
            "hasKeyframe": ap.has_keyframe_at(frame),
            "keyframes": ap.all_keyframe_frames(),
        })
    return {"clipId": clipId, "clipType": type(clip).__name__,
            "startFrame": clip.startFrame, "duration": clip.duration, "params": rows}


@router.post("/clips/{clipId}/params/{key}")
def setClipParam(clipId: str, key: str, body: ParamValueBody):
    clip, _ = _find_clip(clipId)
    schema  = _clip_param_schema(clip)
    p_def   = next((p for p in schema if p["id"] == key), None)
    if p_def is None:
        raise HTTPException(404, f"Unknown param {key!r}")
    ap = _get_or_create_anim(clip, key, p_def["default"])
    if body.frame >= 0:
        ap.add_keyframe(body.frame, body.value, Interp.linear)
    else:
        ap.set_base(body.value)
        clip.applyParam(key, body.value)
        if hasattr(clip, '_lastFrame'):
            clip._lastFrame = -1
    return {"status": "ok", "key": key, "value": body.value, "isAnimated": ap.is_animated()}


@router.post("/clips/{clipId}/keyframes/{key}")
def addKeyframe(clipId: str, key: str, body: KeyframeBody):
    clip, _ = _find_clip(clipId)
    schema  = _clip_param_schema(clip)
    p_def   = next((p for p in schema if p["id"] == key), None)
    if p_def is None:
        raise HTTPException(404, f"Unknown param {key!r}")
    ap = _get_or_create_anim(clip, key, p_def["default"])
    kf = KF(frame=body.frame, value=body.value, interp=Interp(body.interp),
             handle_in_f=body.handle_in_f, handle_in_v=body.handle_in_v,
             handle_out_f=body.handle_out_f, handle_out_v=body.handle_out_v)
    ap._tracks[0].add(kf)
    return {"status": "ok", "frames": ap.all_keyframe_frames()}


@router.get("/clips/{clipId}/keyframes/{key}")
def listKeyframes(clipId: str, key: str):
    clip, _ = _find_clip(clipId)
    if not hasattr(clip, '_anim_params') or key not in clip._anim_params:
        return {"frames": [], "allFrames": [], "vecType": "float"}
    ap = clip._anim_params[key]
    return {
        "frames": ap.keyframes_for_component(0),
        "allFrames": ap.all_keyframe_frames(),
        "vecType": ap.to_schema_type() if hasattr(ap, 'to_schema_type') else "float",
        "components": ap.components if hasattr(ap, 'components') else 1,
    }


@router.post("/clips/{clipId}/keyframes/{key}/move")
def moveKeyframe(clipId: str, key: str, body: MoveKeyframeBody):
    clip, _ = _find_clip(clipId)
    if not hasattr(clip, '_anim_params') or key not in clip._anim_params:
        raise HTTPException(404, "No keyframes on this param")
    ap    = clip._anim_params[key]
    moved = ap.move_keyframe(body.from_frame, body.to_frame)
    if not moved:
        raise HTTPException(404, f"No keyframe at frame {body.from_frame}")
    return {"status": "ok", "frames": ap.all_keyframe_frames()}


@router.delete("/clips/{clipId}/keyframes/{key}/{frame}")
def removeKeyframe(clipId: str, key: str, frame: int):
    clip, _ = _find_clip(clipId)
    if not hasattr(clip, '_anim_params') or key not in clip._anim_params:
        raise HTTPException(404, "No keyframes on this param")
    removed = clip._anim_params[key].remove_keyframe(frame)
    if not removed:
        raise HTTPException(404, f"No keyframe at frame {frame}")
    return {"status": "ok"}


# ── Bulk Update ────────────────────────────────────────────────────────────────

class BulkUpdateRequest(BaseModel):
    clip_ids: list[str]
    style: dict = {}          # TextStyle fields (fontSize, color, etc.)
    transform: dict = {}      # Transform fields (pos_x, pos_y, scale_x, etc.)
    include_text: bool = False  # if False, 'text' key in style is ignored


@router.post("/clips/bulk-update")
def bulkUpdateClips(req: BulkUpdateRequest):
    """
    Apply style/transform params to multiple clips at once.

    - style dict is applied to TextClip.style (skipping 'text' unless include_text=True)
    - transform dict keys: pos_x, pos_y, scale_x, scale_y, rotation, opacity, anchor_x, anchor_y
    - Returns per-clip results with ok/error status
    """
    from backend.animation.transform import Transform
    results = []
    for cid in req.clip_ids:
        try:
            clip, _ = _find_clip(cid)
        except HTTPException:
            results.append({"clipId": cid, "status": "error", "error": "not found"})
            continue
        try:
            if req.style and isinstance(clip, TextClip):
                for k, v in req.style.items():
                    if k == "text" and not req.include_text:
                        continue
                    if hasattr(clip.style, k):
                        setattr(clip.style, k, v)
            if req.transform:
                _apply_transform_dict(clip, req.transform)
            results.append({"clipId": cid, "status": "ok"})
        except Exception as exc:
            results.append({"clipId": cid, "status": "error", "error": str(exc)})
    notify("timeline")
    notify("render")
    return {"updated": len([r for r in results if r["status"] == "ok"]), "results": results}


# ── Set static param (no keyframe) ─────────────────────────────────────────────

class SetParamRequest(BaseModel):
    clip_id: str
    param: str    # e.g. 'font_size', 'pos_x', 'opacity', 'scale_x'
    value: float


@router.post("/clips/set-param")
def setClipParam(req: SetParamRequest):
    """
    Directly set a static (non-animated) parameter value on a clip.
    This does NOT add a keyframe — it sets the base value.

    Useful for one-shot changes: move a clip, resize, change opacity, etc.
    For animated changes use POST /anim/{clipId}/keyframe instead.
    """
    clip, _ = _find_clip(req.clip_id)
    _apply_single_param(clip, req.param, req.value)
    notify("timeline")
    notify("render")
    return {"clipId": req.clip_id, "param": req.param, "value": req.value}


def _apply_transform_dict(clip, transform: dict) -> None:
    """Apply a dict of transform param names → float values to a clip's transform."""
    t = clip.transform
    _TRANSFORM_SETTERS = {
        "pos_x":    lambda v: t.position.setX(v),
        "pos_y":    lambda v: t.position.setY(v),
        "scale_x":  lambda v: t.scale.setX(v),
        "scale_y":  lambda v: t.scale.setY(v),
        "rotation": lambda v: setattr(t, "_rotation_base", v) or t.rotation.setBase(v),
        "opacity":  lambda v: t.opacity.setBase(v),
        "anchor_x": lambda v: t.anchor.setX(v),
        "anchor_y": lambda v: t.anchor.setY(v),
    }
    for k, v in transform.items():
        setter = _TRANSFORM_SETTERS.get(k)
        if setter:
            try:
                setter(float(v))
            except Exception:
                pass


def _apply_single_param(clip, param: str, value: float) -> None:
    """Set a single named param directly on a clip (static, no keyframe)."""
    t = clip.transform
    # Transform params
    transform_map = {
        "pos_x":    lambda: t.position.setX(value),
        "pos_y":    lambda: t.position.setY(value),
        "scale_x":  lambda: t.scale.setX(value),
        "scale_y":  lambda: t.scale.setY(value),
        "rotation": lambda: t.rotation.setBase(value),
        "opacity":  lambda: t.opacity.setBase(value),
        "anchor_x": lambda: t.anchor.setX(value),
        "anchor_y": lambda: t.anchor.setY(value),
    }
    if param in transform_map:
        transform_map[param]()
        return
    # Text-specific params
    if isinstance(clip, TextClip):
        text_map = {
            "font_size":    lambda: setattr(clip.style, "fontSize", value),
            "tracking":     lambda: setattr(clip.style, "letterSpacing", value),
            "line_height":  lambda: setattr(clip.style, "lineHeight", value),
            "fill_r":       lambda: clip.style.color.__setitem__(0, value),
            "fill_g":       lambda: clip.style.color.__setitem__(1, value),
            "fill_b":       lambda: clip.style.color.__setitem__(2, value),
            "fill_a":       lambda: clip.style.color.__setitem__(3, value),
        }
        if param in text_map:
            text_map[param]()
            return
    # Shape-specific
    from backend.timeline.clips.shapeClip import ShapeClip
    if isinstance(clip, ShapeClip):
        shape_map = {
            "shape_w": lambda: setattr(clip.style, "width", value),
            "shape_h": lambda: setattr(clip.style, "height", value),
            "stroke_w": lambda: setattr(clip.style, "strokeWidth", value),
        }
        if param in shape_map:
            shape_map[param]()
            return
    raise HTTPException(400, f"Unknown param '{param}' for this clip type")
