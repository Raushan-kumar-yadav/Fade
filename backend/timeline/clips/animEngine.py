"""
animEngine.py — Keyframe interpolation engine
Mirrors Qteee-Vulkan Keyframe.hpp + KeyframeTrack.cpp

Interpolation modes: constant, linear, bezier, ease_in, ease_out, ease_both
VecTypes: scalar (float), vec2 [x,y], vec3 [r,g,b], vec4 [r,g,b,a], toggle (bool)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import math


class VecType(int, Enum):
    """Component count / semantic type — mirrors Qteee AnimParamType."""
    toggle = 0   # bool, only stepped keyframes
    scalar = 1   # float
    vec2   = 2   # [x, y]
    vec3   = 3   # [r, g, b]
    vec4   = 4   # [r, g, b, a]


class Interp(str, Enum):
    constant  = "constant"
    linear = "linear"
    bezier = "bezier"
    ease_in = "ease_in"
    ease_out  = "ease_out"
    ease_both = "ease_both"


@dataclass
class Keyframe:
    frame: int
    value: float
    interp: Interp = Interp.linear
    # Bezier handles  
    handle_in_f: float  = -5.0
    handle_in_v: float  =  0.0
    handle_out_f: float  =  5.0
    handle_out_v: float  =  0.0

    def to_dict(self) -> dict:
        return {
            "frame": self.frame,
            "value": self.value,
            "interp": self.interp.value,
            "handle_in_f":  self.handle_in_f,
            "handle_in_v":  self.handle_in_v,
            "handle_out_f": self.handle_out_f,
            "handle_out_v": self.handle_out_v,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Keyframe":
        return cls(
            frame=int(d["frame"]),
            value=float(d["value"]),
            interp=Interp(d.get("interp", "linear")),
            handle_in_f=float(d.get("handle_in_f", -5.0)),
            handle_in_v=float(d.get("handle_in_v",  0.0)),
            handle_out_f=float(d.get("handle_out_f", 5.0)),
            handle_out_v=float(d.get("handle_out_v", 0.0)),
        )


def _cubic_bezier_t(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
    """Standard cubic Bezier evaluation."""
    mt = 1.0 - t
    return (mt**3)*p0 + 3*(mt**2)*t*p1 + 3*mt*(t**2)*p2 + (t**3)*p3


def _solve_t_for_x(x: float, x0: float, x1: float, x2: float, x3: float,
                   iterations: int = 12) -> float:
    """Binary-search for t such that B(t).x == x (Newton's method alternative)."""
    lo, hi = 0.0, 1.0
    for _ in range(iterations):
        mid = (lo + hi) * 0.5
        bx  = _cubic_bezier_t(x0, x1, x2, x3, mid)
        if bx < x:
            lo = mid
        else:
            hi = mid
    return (lo + hi) * 0.5


class KeyframeTrack:
    """Sorted list of keyframes for one scalar parameter component."""

    def __init__(self) -> None:
        self._kfs: List[Keyframe] = []

    # Mutation  

    def add(self, kf: Keyframe) -> None:
        """Insert or replace keyframe at the given frame."""
        self._kfs = [k for k in self._kfs if k.frame != kf.frame]
        self._kfs.append(kf)
        self._kfs.sort(key=lambda k: k.frame)

    def remove(self, frame: int) -> bool:
        before = len(self._kfs)
        self._kfs = [k for k in self._kfs if k.frame != frame]
        return len(self._kfs) < before

    def clear(self) -> None:
        self._kfs.clear()

    # Query  

    def is_animated(self) -> bool:
        return len(self._kfs) >= 1

    def has_keyframe_at(self, frame: int) -> bool:
        return any(k.frame == frame for k in self._kfs)

    def keyframes(self) -> List[Keyframe]:
        return list(self._kfs)

    def prev_frame(self, current: int) -> Optional[int]:
        candidates = [k.frame for k in self._kfs if k.frame < current]
        return max(candidates) if candidates else None

    def next_frame(self, current: int) -> Optional[int]:
        candidates = [k.frame for k in self._kfs if k.frame > current]
        return min(candidates) if candidates else None

    def evaluate(self, frame: int, base_value: float) -> float:
        if not self._kfs:
            return base_value
        if len(self._kfs) == 1:
            return self._kfs[0].value
        if frame <= self._kfs[0].frame:
            return self._kfs[0].value
        if frame >= self._kfs[-1].frame:
            return self._kfs[-1].value

        # Find surrounding pair
        k0, k1 = None, None
        for i in range(len(self._kfs) - 1):
            if self._kfs[i].frame <= frame <= self._kfs[i + 1].frame:
                k0, k1 = self._kfs[i], self._kfs[i + 1]
                break
        if k0 is None:
            return base_value

        span = k1.frame - k0.frame
        if span == 0:
            return k0.value
        t = (frame - k0.frame) / span

        interp = k0.interp

        if interp == Interp.constant:
            return k0.value

        if interp == Interp.linear:
            return k0.value + (k1.value - k0.value) * t

        if interp in (Interp.ease_in, Interp.ease_out, Interp.ease_both):
            # Smooth-step variants
            if interp == Interp.ease_in:
                t = t * t
            elif interp == Interp.ease_out:
                t = t * (2.0 - t)
            else:  # ease_both
                t = t * t * (3.0 - 2.0 * t)
            return k0.value + (k1.value - k0.value) * t

        if interp == Interp.bezier:
            # Control points in (frame, value) space
            cp0f, cp0v = float(k0.frame),        k0.value
            cp1f = k0.frame + k0.handle_out_f
            cp1v = k0.value + k0.handle_out_v
            cp2f = k1.frame + k1.handle_in_f
            cp2v = k1.value + k1.handle_in_v
            cp3f, cp3v = float(k1.frame),        k1.value

            # Solve for t parameter corresponding to current frame on X axis
            bt = _solve_t_for_x(float(frame), cp0f, cp1f, cp2f, cp3f)
            return _cubic_bezier_t(cp0v, cp1v, cp2v, cp3v, bt)

        return k0.value + (k1.value - k0.value) * t


#   Multi-component param  

class AnimParam:
    """
    One animatable parameter — scalar, vec2, vec3, vec4, or toggle (bool).
    Mirrors Qteee-Vulkan AnimatableProperty<T>.

    - scalar  → evaluate() returns float
    - vec2/3/4 → evaluate() returns List[float]
    - toggle   → evaluate() returns bool (uses stepped constant interpolation)
    """

    def __init__(self, base_value: Any, vec_type: VecType = VecType.scalar) -> None:
        self._vec_type = vec_type

        if vec_type == VecType.toggle:
            # Boolean: store as single float 0.0/1.0
            self._components: int = 1
            self._base: List[float] = [1.0 if bool(base_value) else 0.0]
        elif isinstance(base_value, bool):
            self._components = 1
            self._base = [1.0 if base_value else 0.0]
            self._vec_type = VecType.toggle
        elif isinstance(base_value, (int, float)):
            self._components = max(1, int(vec_type)) if vec_type != VecType.toggle else 1
            self._base = [float(base_value)] * self._components
        elif isinstance(base_value, (list, tuple)):
            self._components = len(base_value)
            self._base = [float(v) for v in base_value]
            # Auto-detect VecType if not specified
            if vec_type == VecType.scalar and self._components > 1:
                self._vec_type = VecType(self._components)
        else:
            self._components = 1
            self._base = [0.0]

        self._tracks: List[KeyframeTrack] = [
            KeyframeTrack() for _ in range(self._components)
        ]

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def vec_type(self) -> VecType:
        return self._vec_type

    @property
    def components(self) -> int:
        return self._components

    # ── Animation state ───────────────────────────────────────────────────────

    def is_animated(self) -> bool:
        return any(t.is_animated() for t in self._tracks)

    def has_keyframe_at(self, frame: int) -> bool:
        return any(t.has_keyframe_at(frame) for t in self._tracks)

    # ── Keyframe editing ──────────────────────────────────────────────────────

    def add_keyframe(self, frame: int, value: Any,
                     interp: Interp = Interp.linear) -> None:
        # Toggle always uses constant interpolation
        if self._vec_type == VecType.toggle:
            interp = Interp.constant

        if isinstance(value, bool):
            vals = [1.0 if value else 0.0]
        elif isinstance(value, (int, float)):
            vals = [float(value)] * self._components
        else:
            vals = [float(v) for v in value]

        for i, track in enumerate(self._tracks):
            v = vals[i] if i < len(vals) else self._base[i]
            track.add(Keyframe(frame=frame, value=v, interp=interp))

    def remove_keyframe(self, frame: int) -> bool:
        removed = False
        for t in self._tracks:
            removed |= t.remove(frame)
        return removed

    def move_keyframe(self, old_frame: int, new_frame: int) -> bool:
        """Move a keyframe from old_frame to new_frame across all component tracks."""
        moved = False
        for t in self._tracks:
            kfs = [k for k in t.keyframes() if k.frame == old_frame]
            for kf in kfs:
                t.remove(old_frame)
                new_kf = Keyframe(frame=new_frame, value=kf.value, interp=kf.interp,
                                  handle_in_f=kf.handle_in_f, handle_in_v=kf.handle_in_v,
                                  handle_out_f=kf.handle_out_f, handle_out_v=kf.handle_out_v)
                t.add(new_kf)
                moved = True
        return moved

    # ── Evaluation ────────────────────────────────────────────────────────────

    def evaluate(self, frame: int) -> Any:
        result = [t.evaluate(frame, self._base[i])
                  for i, t in enumerate(self._tracks)]
        if self._vec_type == VecType.toggle:
            return bool(result[0] >= 0.5)
        if self._components == 1:
            return result[0]
        return result

    # ── Base value ────────────────────────────────────────────────────────────

    def set_base(self, value: Any) -> None:
        if isinstance(value, bool):
            self._base = [1.0 if value else 0.0]
        elif isinstance(value, (int, float)):
            self._base = [float(value)] * self._components
        else:
            vals = [float(v) for v in value]
            # Pad or truncate to match component count
            while len(vals) < self._components:
                vals.append(0.0)
            self._base = vals[:self._components]

    # ── Serialization helpers ─────────────────────────────────────────────────

    def keyframes_for_component(self, comp: int = 0) -> List[dict]:
        if comp >= len(self._tracks):
            return []
        return [k.to_dict() for k in self._tracks[comp].keyframes()]

    def all_keyframes_all_components(self) -> List[dict]:
        """All keyframes for all components, tagged with component index."""
        result = []
        for i, t in enumerate(self._tracks):
            for k in t.keyframes():
                d = k.to_dict()
                d['component'] = i
                result.append(d)
        return result

    def all_keyframe_frames(self) -> List[int]:
        frames: set[int] = set()
        for t in self._tracks:
            for k in t.keyframes():
                frames.add(k.frame)
        return sorted(frames)

    def prev_keyframe(self, frame: int) -> Optional[int]:
        candidates = [t.prev_frame(frame) for t in self._tracks]
        candidates = [c for c in candidates if c is not None]
        return max(candidates) if candidates else None

    def next_keyframe(self, frame: int) -> Optional[int]:
        candidates = [t.next_frame(frame) for t in self._tracks]
        candidates = [c for c in candidates if c is not None]
        return min(candidates) if candidates else None

    def to_schema_type(self) -> str:
        """Return JSON schema type string for the Inspector."""
        mapping = {
            VecType.toggle: 'toggle',
            VecType.scalar: 'float',
            VecType.vec2:   'vec2',
            VecType.vec3:   'vec3',
            VecType.vec4:   'vec4',
        }
        return mapping.get(self._vec_type, 'float')
