   
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.state import engine, _clipTrackMap
from backend.events import notify

router = APIRouter(tags=["animation"])


# helpers  

def _active_tl():
    tl = engine.activeTimeline if engine else None
    if tl is None:
        raise HTTPException(400, "No active timeline")
    return tl


def _find_clip(clip_id: str):
    tl = _active_tl()
    clip, track = tl.findClip(clip_id)
    if clip is None:
        raise HTTPException(404, f"Clip '{clip_id}' not found")
    return clip, track


# Map param id 
def _resolve_property(clip, param: str):
    """
    Return the AnimatableProperty for a named param on any clip.
    Raises ValueError if param is unknown for this clip type.
    """
    t = clip.transform
    mapping = {
        "opacity": t.opacity,
        "pos_x": t.position.x,
        "pos_y": t.position.y,
        "scale_x": t.scale.x,
        "scale_y": t.scale.y,
        "rotation": t.rotation,
        "anchor_x": t.anchor.x,
        "anchor_y": t.anchor.y,
    }

    # Clip-type-specific params
    from backend.timeline.clips.textClip  import TextClip
    from backend.timeline.clips.shapeClip import ShapeClip
    from backend.timeline.clips.penClip   import PenClip

    if isinstance(clip, TextClip):
        s = clip.style
        # Text uses a generic _anim_params dict (via animEngine / applyParam pattern)
        text_props = {
            "font_size": _get_anim_param(clip, "font_size",   s.fontSize),
            "fill_r": _get_anim_param(clip, "fill_r", s.color[0]),
            "fill_g": _get_anim_param(clip, "fill_g", s.color[1]),
            "fill_b": _get_anim_param(clip, "fill_b", s.color[2]),
            "fill_a": _get_anim_param(clip, "fill_a", s.color[3]),
            "tracking": _get_anim_param(clip, "tracking",    s.letterSpacing),
            "line_height": _get_anim_param(clip, "line_height", s.lineHeight),
        }
        mapping.update(text_props)

    elif isinstance(clip, ShapeClip):
        s  = clip.style
        fc = s.fillColor   or [0.4, 0.4, 1.0, 1.0]
        sc = s.strokeColor or [1.0, 1.0, 1.0, 1.0]
        shape_props = {
            "shape_w":  _get_anim_param(clip, "shape_w", s.width),
            "shape_h": _get_anim_param(clip, "shape_h", s.height),
            "fill_r": _get_anim_param(clip, "fill_r", fc[0]),
            "fill_g": _get_anim_param(clip, "fill_g", fc[1]),
            "fill_b": _get_anim_param(clip, "fill_b", fc[2]),
            "fill_a": _get_anim_param(clip, "fill_a", fc[3]),
            "stroke_r": _get_anim_param(clip, "stroke_r", sc[0]),
            "stroke_g": _get_anim_param(clip, "stroke_g", sc[1]),
            "stroke_b": _get_anim_param(clip, "stroke_b", sc[2]),
            "stroke_w": _get_anim_param(clip, "stroke_w", s.strokeWidth),
        }
        mapping.update(shape_props)

    elif isinstance(clip, PenClip):
        s  = clip.style
        sc = getattr(s, "strokeColor", [1.0, 1.0, 1.0, 1.0])
        fc = getattr(s, "fillColor",   [0.0, 0.0, 0.0, 0.0])
        pen_props = {
            "stroke_r": _get_anim_param(clip, "stroke_r", sc[0]),
            "stroke_g": _get_anim_param(clip, "stroke_g", sc[1]),
            "stroke_b": _get_anim_param(clip, "stroke_b", sc[2]),
            "stroke_w": _get_anim_param(clip, "stroke_w", s.strokeWidth),
            "fill_a":   _get_anim_param(clip, "fill_a",   fc[3]),
        }
        mapping.update(pen_props)

    if param not in mapping:
        raise ValueError(
            f"Unknown param '{param}' for clip type '{getattr(clip, 'CLIP_TYPE', type(clip).__name__)}'.\n"
            f"Valid params: {sorted(mapping.keys())}"
        )
    return mapping[param]


def _get_anim_param(clip, key: str, base_value: float):
    """
    Return (or lazily create) an AnimatableProperty stored on the clip
    under clip._anim_props[key].  This mirrors how applyParam() reads it.
    """
    from backend.animation.animatableProperty import AnimatableProperty
    if not hasattr(clip, "_anim_props"):
        clip._anim_props = {}
    if key not in clip._anim_props:
        clip._anim_props[key] = AnimatableProperty(base_value)
    return clip._anim_props[key]


_EASING_MAP = {
    "constant": 0,    
    "linear": 1,   # Interpolation.Linear
    "bezier": 2,   # Interpolation.Bezier
    "ease_in": 3,   # Interpolation.EaseIn
    "ease_out":  4,   # Interpolation.EaseOut
    "ease_both": 5,   # Interpolation.EaseBoth
}

_EASING_NAME = {v: k for k, v in _EASING_MAP.items()}


def _kf_to_dict(kf) -> dict:
    return {
        "frame": kf.frame,
        "value": round(kf.value, 6),
        "easing": _EASING_NAME.get(int(kf.interp), "bezier"),
        "handle_in_frames": round(kf.handleInFrame, 4),
        "handle_in_value":  round(kf.handleInValue, 6),
        "handle_out_frames": round(kf.handleOutFrame, 4),
        "handle_out_value": round(kf.handleOutValue, 6),
    }


# Request models  

class AddKeyframeRequest(BaseModel):
    param:  str
    frame:  int
    value:  float
    easing: str = "ease_both"   # constant | linear | bezier | ease_in | ease_out | ease_both
     
    handle_in_frames:  float = -8.0   # negative = left side
    handle_in_value:   float =  0.0
    handle_out_frames: float =  8.0   # positive = right side
    handle_out_value:  float =  0.0


# Routes  

@router.post("/anim/{clipId}/keyframe")
def addKeyframe(clipId: str, req: AddKeyframeRequest):
    """
    Add or update a keyframe on any animatable property.
    The frame is relative to timeline start (not clip-local).
    """
    from backend.animation.keyframe import Keyframe, Interpolation

    clip, _ = _find_clip(clipId)

    easing_int = _EASING_MAP.get(req.easing.lower(), 5)  # default ease_both

    try:
        prop = _resolve_property(clip, req.param)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Build keyframe 
    local_frame = req.frame - clip.startFrame

    kf = Keyframe(
        frame = local_frame,
        value = req.value,
        interp = Interpolation(easing_int),
        handleInFrame  = req.handle_in_frames,
        handleInValue  = req.handle_in_value,
        handleOutFrame = req.handle_out_frames,
        handleOutValue = req.handle_out_value,
    )
    prop._isAnimated = True
    prop._track.insertKeyframe(kf)

    notify("timeline")
    return {
        "clipId": clipId,
        "param": req.param,
        "frame": req.frame,
        "localFrame": local_frame,
        "keyframe": _kf_to_dict(kf),
        "totalKeyframes": len(prop._track),
    }


@router.delete("/anim/{clipId}/keyframe/{param}/{frame}")
def removeKeyframe(clipId: str, param: str, frame: int):
    """Remove a single keyframe (frame = timeline frame)."""
    clip, _ = _find_clip(clipId)

    try:
        prop = _resolve_property(clip, param)
    except ValueError as e:
        raise HTTPException(400, str(e))

    local_frame = frame - clip.startFrame
    removed = prop._track.removeKeyframe(local_frame)
    if not removed:
        raise HTTPException(404, f"No keyframe at frame {frame} (local {local_frame}) for param '{param}'")

    if prop._track.empty():
        prop._isAnimated = False

    notify("timeline")
    return {"removed": True, "clipId": clipId, "param": param, "frame": frame}


@router.post("/anim/{clipId}/clear/{param}")
def clearAnimation(clipId: str, param: str):
    """Remove all keyframes from a property, reverting it to a static value."""
    clip, _ = _find_clip(clipId)

    try:
        prop = _resolve_property(clip, param)
    except ValueError as e:
        raise HTTPException(400, str(e))

    count = len(prop._track)
    prop.clearAnimation()

    notify("timeline")
    return {"cleared": True, "clipId": clipId, "param": param, "keyframesRemoved": count}


@router.get("/anim/{clipId}/keyframes")
def getKeyframes(clipId: str):
    """
    Return all animated properties and their keyframes for a clip.
    Also lists static properties with their current base values.
    """
    clip, _ = _find_clip(clipId)

    # Collect all properties  
    t = clip.transform
    all_props: dict[str, object] = {
        "opacity": t.opacity,
        "pos_x": t.position.x,
        "pos_y": t.position.y,
        "scale_x": t.scale.x,
        "scale_y": t.scale.y,
        "rotation": t.rotation,
        "anchor_x":  t.anchor.x,
        "anchor_y": t.anchor.y,
    }

    # Add clip-specific anim props if they exist
    for key, prop in getattr(clip, "_anim_props", {}).items():
        all_props[key] = prop

    animated = []
    static = []

    for name, prop in all_props.items():
        is_anim = getattr(prop, "_isAnimated", False) and not prop._track.empty()
        if is_anim:
            animated.append({
                "param":     name,
                "keyframes": [_kf_to_dict(kf) for kf in prop._track.keyframes()],
            })
        else:
            static.append({
                "param": name,
                "value": round(prop._baseValue if hasattr(prop, "_baseValue") else prop.get(), 6),
            })

    return {
        "clipId": clipId,
        "clipType": getattr(clip, "CLIP_TYPE", type(clip).__name__),
        "startFrame":  clip.startFrame,
        "animated": animated,
        "static": static,
    }


@router.get("/anim/{clipId}/params")
def getClipParams(clipId: str):
    """
    Return all animatable parameter IDs with current values, ranges, and animated status.
    Call this first to discover what you can animate on a clip.
    """
    from backend.routers.clips import _clip_param_schema, _find_clip as clips_find

    clip, _ = _find_clip(clipId)
    schema  = _clip_param_schema(clip)

    # Enrich with animated flag
    t = clip.transform
    anim_check: dict[str, object] = {
        "opacity": t.opacity,
        "pos_x": t.position.x,
        "pos_y": t.position.y,
        "scale_x":  t.scale.x,
        "scale_y":  t.scale.y,
        "rotation": t.rotation,
        "anchor_x": t.anchor.x,
        "anchor_y": t.anchor.y,
    }
    anim_check.update(getattr(clip, "_anim_props", {}))

    result = []
    for p in schema:
        pid  = p["id"]
        prop = anim_check.get(pid)
        is_animated = (
            prop is not None
            and getattr(prop, "_isAnimated", False)
            and not prop._track.empty()
        )
        result.append({**p, "animated": is_animated})

    return {"clipId": clipId, "params": result}
