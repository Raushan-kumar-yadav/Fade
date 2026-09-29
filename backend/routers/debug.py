 
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
        "clipId": clipId,
        "param": param,
        "timeline_frame": frame,
        "local_frame":  local_frame,
        "value": round(value, 6),
        "linear_ref":   round(lin, 6),
        "deviation": round(deviation, 6),
        "interp": interp_name,
        "verdict": verdict,
        "keyframe_frames": [k.frame for k in kfs],
        "keyframe_values": [k.value for k in kfs],
    }

@router.post("/debug/reload-anim")
def reloadAnimModules():
    """Hot-reload animation + clip modules so code changes take effect without restart."""
    import importlib
    reloaded = []
    for mod_name in list(__import__('sys').modules.keys()):
        if any(x in mod_name for x in ('baseClip','animatableProperty','transform','render','animEngine','scalarTrack')):
            try:
                importlib.reload(__import__('sys').modules[mod_name])
                reloaded.append(mod_name)
            except Exception as e:
                pass
    return {"reloaded": reloaded}


@router.post("/debug/patch-anim")
def patchAnimMethods():
    from backend.timeline.clips.baseClip import BaseClip
    from backend.animation import anim_debug as _dbg

    def _evaluateAll(self, frame: int, _timeline=None):
        lf = self.localFrame(frame)
        if _timeline is None:
            try:
                from backend.state import engine as _eng
                _timeline = _eng.activeTimeline if _eng else None
            except Exception:
                pass
        if hasattr(self, '_anim_params'):
            for key, ap in self._anim_params.items():
                try:
                    val = ap.evaluate(frame) if ap.is_animated() else ap._base[0]
                    self.applyParam(key, val)
                except Exception as _e:
                    print(f"[ANIM] applyParam error key={key}: {_e}", flush=True)
        self.transform.evaluateAll(lf, _clip=self, _timeline=_timeline)
        for effect in self.effects:
            if hasattr(effect, 'evaluateAll'):
                effect.evaluateAll(lf)

    def _applyParam(self, key: str, val: float):
        t = self.transform
        if key == "opacity":
            t.opacity.setBaseValue(val); t.opacity._currentValue = val
        elif key == "pos_x":
            t.position.setBase(val, t.position.y.baseValue); t.position.x._currentValue = val
        elif key == "pos_y":
            t.position.setBase(t.position.x.baseValue, val); t.position.y._currentValue = val
        elif key == "scale_x":
            t.scale.setBase(val, t.scale.y.baseValue); t.scale.x._currentValue = val
        elif key == "scale_y":
            t.scale.setBase(t.scale.x.baseValue, val); t.scale.y._currentValue = val
        elif key == "rotation":
            t.rotation.setBaseValue(val); t.rotation._currentValue = val
        elif key == "anchor_x":
            t.anchor.setBase(val, t.anchor.y.baseValue); t.anchor.x._currentValue = val
        elif key == "anchor_y":
            t.anchor.setBase(t.anchor.x.baseValue, val); t.anchor.y._currentValue = val
        elif key == "blend_mode":
            bm = getattr(self, "blendMode", None)
            if hasattr(bm, "setBaseValue"):
                bm.setBaseValue(float(round(val))); bm._currentValue = float(round(val))
            else:
                self.blendMode = int(round(val))

    BaseClip.evaluateAll = _evaluateAll
    BaseClip.applyParam  = _applyParam

    # Also patch subclass overrides — in the running process they still have
    # `super().evaluateAll(frame, _timeline=_timeline)` which crashes with NameError.
    # Replace each subclass override with a minimal one that calls the fixed super().
    from backend.timeline.clips import imageClip as _ic, videoClip as _vc
    try:
        from backend.timeline.clips import penClip as _pc
    except Exception:
        _pc = None
    try:
        from backend.timeline.clips import textClip as _tc
    except Exception:
        _tc = None

    def _img_evaluateAll(self, frame: int, _timeline=None) -> None:
        super(self.__class__, self).evaluateAll(frame, _timeline=_timeline)
        lf = self.localFrame(frame)
        for prop in ('cropLeft', 'cropRight', 'cropTop', 'cropBottom', 'blendMode'):
            p = getattr(self, prop, None)
            if p and hasattr(p, 'update'): p.update(lf)

    def _vid_evaluateAll(self, frame: int, _timeline=None) -> None:
        if frame == self._lastFrame:
            return
        self._lastFrame = frame
        super(self.__class__, self).evaluateAll(frame, _timeline=_timeline)
        lf = self.localFrame(frame)
        for prop in ('cropLeft', 'cropRight', 'cropTop', 'cropBottom', 'blendMode'):
            p = getattr(self, prop, None)
            if p and hasattr(p, 'update'): p.update(lf)

    _ic.ImageClip.evaluateAll = _img_evaluateAll
    _vc.VideoClip.evaluateAll = _vid_evaluateAll
    patched = ["BaseClip.evaluateAll", "BaseClip.applyParam", "ImageClip.evaluateAll", "VideoClip.evaluateAll"]

    if _pc:
        def _pen_evaluateAll(self, frame: int, _timeline=None) -> None:
            super(self.__class__, self).evaluateAll(frame, _timeline=_timeline)
            lf = self.localFrame(frame)
            if hasattr(self, '_syncBase'): self._syncBase()
            if hasattr(self, 'shapePath'): self.shapePath.update(lf)
        _pc.PenClip.evaluateAll = _pen_evaluateAll
        patched.append("PenClip.evaluateAll")

    if _tc:
        def _txt_evaluateAll(self, frame: int, _timeline=None) -> None:
            super(self.__class__, self).evaluateAll(frame, _timeline=_timeline)
        _tc.TextClip.evaluateAll = _txt_evaluateAll
        patched.append("TextClip.evaluateAll")

    print(f"[DEBUG] Patched: {patched}", flush=True)
    return {"patched": patched}
@router.get("/debug/kf-test")
def kfTest():
    from backend.state import engine as _eng
    tl = _eng.activeTimeline if _eng else None
    if not tl: return {"error": "no timeline"}
    out = []
    for track in tl.tracks:
        for clip in track.clips:
            cid = clip.clipId[:8]
            has_ap = hasattr(clip, "_anim_params")
            if has_ap:
                ap = clip._anim_params.get("pos_x")
                if ap:
                    animated = ap.is_animated()
                    v40 = ap.evaluate(40) if animated else ap._base[0]
                    clip.evaluateAll(40)
                    cur = clip.transform.position.x._currentValue
                    base = clip.transform.position.x._baseValue
                    out.append({"clip":cid,"animated":animated,"ap_eval_40":v40,"pos_x_cur":cur,"pos_x_base":base})
    return {"results": out}
