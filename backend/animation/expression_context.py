

from __future__ import annotations
import math
import random
from typing import Any


#  Safe built-ins whitelist


SAFE_BUILTINS: dict = {
    "abs":   abs,
    "round": round,
    "min":   min,
    "max":   max,
    "int":   int,
    "float": float,
    "bool":  bool,
    "len":   len,
    "range": range,
    "sum":   sum,
    "None":  None,
    "True":  True,
    "False": False,
}



#  Wiggle â€” smooth random oscillation


def _make_wiggle():
    _cache: dict[tuple, float] = {}

    def _noise1(xi: int, seed: int) -> float:
        # Deterministic hash â†’ float in [-1, 1]
        h = hash((xi, seed)) & 0xFFFFFFFF
        return (h / 0xFFFFFFFF) * 2.0 - 1.0

    def wiggle(freq: float, amp: float, seed: int = 0) -> float:


        t = _time_ref[0]
        x = t * freq
        xi = int(x)
        xf = x - xi
        # Smooth-step interpolation
        xf = xf * xf * (3.0 - 2.0 * xf)
        a = _noise1(xi,     seed)
        b = _noise1(xi + 1, seed)
        return (a + (b - a) * xf) * amp

    _time_ref: list[float] = [0.0]
    return wiggle, _time_ref

_wiggle_fn, _time_ref_global = _make_wiggle()



#  CompProxy


class _PointProxy:
    __slots__ = ("x", "y")
    def __init__(self, x, y):
        self.x = x
        self.y = y

class _ClipProxy:
    """Lightweight read-only view of another clip's current transform values."""
    __slots__ = ("_clip", "_frame")

    def __init__(self, clip, frame) -> None:
        object.__setattr__(self, "_clip", clip)
        object.__setattr__(self, "_frame", frame)

    def tracking(self, tracking_id: str):
        from backend.state import _library
        if not hasattr(self._clip, "assetId") or not self._clip.assetId:
            return _PointProxy(0.0, 0.0)
        asset = _library.get(self._clip.assetId)
        if not asset or not getattr(asset, "trackingResults", None):
            return _PointProxy(0.0, 0.0)
        tdata = asset.trackingResults.get(tracking_id)
        if not tdata:
            return _PointProxy(0.0, 0.0)
        # Map frame to asset time
        asset_frame = self._clip.sourceFrame(self._frame) if hasattr(self._clip, "sourceFrame") else self._frame
        point = tdata.get("frames", {}).get(str(asset_frame))
        if point:
            return _PointProxy(point.get("x", 0.0), point.get("y", 0.0))
        return _PointProxy(0.0, 0.0)

    # Convenience: expr can do  comp.clip("id").pos_x
    @property
    def pos_x(self) -> float:
        return self._clip.transform.position.x.get()

    @property
    def pos_y(self) -> float:
        return self._clip.transform.position.y.get()

    @property
    def scale_x(self) -> float:
        return self._clip.transform.scale.x.get()

    @property
    def scale_y(self) -> float:
        return self._clip.transform.scale.y.get()

    @property
    def rotation(self) -> float:
        return self._clip.transform.rotation.get()

    @property
    def opacity(self) -> float:
        return self._clip.transform.opacity.get()

    # Full transform object access
    @property
    def transform(self):
        return self._clip.transform

    def __setattr__(self, name, value):
        raise AttributeError("Expression clip proxies are read-only.")


class _CompProxy:
    """Wraps a timeline to expose .clip(id) in expressions."""
    __slots__ = ('_timeline', '_frame')

    def __init__(self, timeline, frame) -> None:
        object.__setattr__(self, '_timeline', timeline)
        object.__setattr__(self, '_frame', frame)

    def clip(self, clip_id: str) -> _ClipProxy:
        """Get a read-only proxy for a clip by its clipId."""
        tl = object.__getattribute__(self, "_timeline")
        if tl is None:
            raise KeyError(f"No active timeline; cannot resolve clip '{clip_id}'")
        try:
            c, _ = tl.findClip(clip_id)
        except Exception:
            c = None
        if c is None:
            raise KeyError(f"Clip '{clip_id}' not found in timeline")
        return _ClipProxy(c, object.__getattribute__(self, '_frame'))

    def __setattr__(self, name, value):
        raise AttributeError("CompProxy is read-only.")



#  Context builder


def build_context(
    frame: int,
    base_value: float,
    clip: Any,
    timeline: Any,
) -> dict:

    fps = float(getattr(timeline, "fps", 30.0)) if timeline else 30.0
    t = frame / fps
    dur = int(getattr(clip, "duration", 1)) if clip else 1

    # Update time reference used by wiggle closure
    _time_ref_global[0] = t

    # clamp / lerp helpers
    def clamp(v: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, v))

    def lerp(a: float, b: float, t_: float) -> float:
        return a + (b - a) * t_

    def smoothstep(lo: float, hi: float, t_: float) -> float:
        t2 = max(0.0, min(1.0, (t_ - lo) / (hi - lo) if hi != lo else 0.0))
        return t2 * t2 * (3.0 - 2.0 * t2)

    return {
        # Time
        "frame": frame,
        "time": t,
        "fps": fps,
        "duration": dur,
        # Self
        "value": base_value,
        "this": _ClipProxy(clip, frame) if clip else None,
        # Comp access
        "comp": _CompProxy(timeline, frame) if timeline else None,
        #
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "atan2": math.atan2,
        "sqrt": math.sqrt,
        "pi": math.pi,
        "tau": math.tau,
        "e": math.e,
        "floor": math.floor,
        "ceil": math.ceil,
        "abs": abs,
        "min": min,
        "max": max,
        "round": round,
        "clamp": clamp,
        "lerp": lerp,
        "smoothstep": smoothstep,
        "wiggle": _wiggle_fn,
        # Expose random for staggered offsets
        "index":      hash(getattr(clip, "clipId", "")) % 1000 if clip else 0,
    }
