 
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


# Toggle per-frame logging  

class DebugToggle(BaseModel):
    enabled: bool = True
    every_n: int  = 1    


@router.put("/debug/anim-debug")
def set_anim_debug(req: DebugToggle):
    from backend.animation import anim_debug as _dbg
    _dbg.set_debug(req.enabled, req.every_n)
    return {
        "anim_debug": _dbg.ANIM_DEBUG,
        "log_every_n": _dbg._LOG_EVERY_N,
        "message": (
            "Console will now log every frame's evaluated value, linear reference, "
            "and deviation. Watch the backend terminal."
            if req.enabled else "Logging disabled."
        )
    }


@router.get("/debug/anim-debug")
def get_anim_debug():
    from backend.animation import anim_debug as _dbg
    return {"anim_debug": _dbg.ANIM_DEBUG, "log_every_n": _dbg._LOG_EVERY_N}


#   Curve tracer  

@router.get("/debug/anim-trace/{clipId}")
def anim_trace(clipId: str, param: str = "opacity", samples: int = 30):
    
    from backend.state import engine
    from backend.animation import anim_debug as _dbg

    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(503, "No active timeline")

    clip = None
    for track in tl.tracks:
        for c in track.clips:
            if c.clipId == clipId or c.clipId.startswith(clipId):
                clip = c
                break
        if clip:
            break

    if clip is None:
        raise HTTPException(404, f"Clip '{clipId}' not found in active timeline")

    # Resolve the track
    _PROP_MAP = {
        "opacity": lambda c: c.transform.opacity,
        "pos_x": lambda c: c.transform.position.x,
        "pos_y": lambda c: c.transform.position.y,
        "scale_x": lambda c: c.transform.scale.x,
        "scale_y": lambda c: c.transform.scale.y,
        "rotation": lambda c: c.transform.rotation,
        "anchor_x": lambda c: c.transform.anchor.x,
        "anchor_y": lambda c: c.transform.anchor.y,
    }

    getter = _PROP_MAP.get(param)
    if getter is None:
        raise HTTPException(400, f"Unknown param '{param}'. Valid: {list(_PROP_MAP)}")

    try:
        ap = getter(clip)
    except AttributeError as e:
        raise HTTPException(400, f"Clip does not have property '{param}': {e}")

    if not ap.isAnimated or ap.track.empty():
        return {
            "clipId": clipId,
            "param": param,
            "animated": False,
            "verdict": "NOT ANIMATED — no keyframes on this property",
            "keyframes": [],
            "samples": [],
        }

    trace = _dbg.dump_curve_trace(ap.track, prop_name=param, n_samples=samples)
    trace["clipId"] = clipId
    trace["clip_type"] = type(clip).__name__
    trace["clip_start"] = clip.startFrame
    trace["clip_duration"] = clip.duration
    return trace


#   Live sample  

@router.get("/debug/anim-eval/{clipId}")
def anim_eval(clipId: str, frame: int = 0, param: str = "opacity"):
    """
    Evaluate a single property at a specific TIMELINE frame and return:
      - the curve value
      - the linear interpolation reference
      - the deviation
      - the interpolation mode
    """
    from backend.state import engine

    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(503, "No active timeline")

    clip = None
    for track in tl.tracks:
        for c in track.clips:
            if c.clipId == clipId or c.clipId.startswith(clipId):
                clip = c
                break
        if clip:
            break

    if clip is None:
        raise HTTPException(404, f"Clip '{clipId}' not found")

    _PROP_MAP = {
        "opacity": lambda c: c.transform.opacity,
        "pos_x": lambda c: c.transform.position.x,
        "pos_y": lambda c: c.transform.position.y,
        "scale_x": lambda c: c.transform.scale.x,
        "scale_y":  lambda c: c.transform.scale.y,
        "rotation": lambda c: c.transform.rotation,
        "anchor_x": lambda c: c.transform.anchor.x,
        "anchor_y": lambda c: c.transform.anchor.y,
    }

    ap = _PROP_MAP.get(param, lambda c: None)(clip)
    if ap is None:
        raise HTTPException(400, f"Unknown param '{param}'")

    local_frame = frame - clip.startFrame

    if not ap.isAnimated or ap.track.empty():
        return {"frame": frame, "local_frame": local_frame, "animated": False,
                "value": ap.baseValue}

    kfs = ap.track.keyframes()
    value = ap.track.evaluateAt(local_frame)

    # Compute linear reference between surrounding keyframes
    import bisect
    nxt_idx = bisect.bisect_right([k.frame for k in kfs], local_frame)
    if nxt_idx == 0:
        lin = kfs[0].value
        interp_name = "before_start"
    elif nxt_idx >= len(kfs):
        lin = kfs[-1].value
        interp_name = "after_end"
    else:
        pk = kfs[nxt_idx - 1]; nk = kfs[nxt_idx]
        span = max(nk.frame - pk.frame, 1)
        t = (local_frame - pk.frame) / span
        lin = pk.value + t * (nk.value - pk.value)
        interp_name = pk.interp.name

    deviation = value - lin
    verdict = ("LINEAR ⚠️" if abs(deviation) < 0.001 * (abs(kfs[-1].value - kfs[0].value) + 1e-9)
               else f"CURVED ✅ (dev={deviation:+.4f})")

    return {
        "clipId":       clipId,
        "param":        param,
        "timeline_frame": frame,
        "local_frame":  local_frame,
        "value":        round(value, 6),
        "linear_ref":   round(lin, 6),
        "deviation":    round(deviation, 6),
        "interp":       interp_name,
        "verdict":      verdict,
        "keyframe_frames": [k.frame for k in kfs],
        "keyframe_values": [k.value for k in kfs],
    }
