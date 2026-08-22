"""
animPath.py — Animatable path property mirroring Qteee-Vulkan exactly.

Architecture (matches Qteee):
  PathVertex           ≡  PathVertex (position + inTangent + outTangent + id)
  PathSnapshot         ≡  MaskPathSnapshot (list of PathVertex + interp handles)
  PathTrack            ≡  pathTrack  (map of frame → PathSnapshot, lerpPath)
  AnimPathProperty     ≡  AnimatableProperty<MaskPathSnapshot>

A SINGLE keyframe stores the ENTIRE path shape at that frame.
Between two keyframes the whole path is lerped vertex-by-vertex (same t).
This is exactly how AE "path" keyframes work and how Qteee implements it.

Usage:
    path = AnimPathProperty()
    path.setBase([
        PathVertex(0,   0,   0,0, 50,0),
        PathVertex(200, 0,  -50,0, 50,0),
        PathVertex(200, 150, 0,-30, 0,30),
    ], closed=True)

    # Add keyframe at frame 0 (current base becomes snapshot)
    path.addKeyframe(0)

    # Move a point and add second keyframe at frame 30
    path.vertices[1].pos = (300, 0)
    path.addKeyframe(30)

    # Evaluate
    path.update(15)           # t=0.5 → interpolated
    pts = path.get()          # → list of PathVertex with lerped positions
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import List

from backend.animation.keyframe import Interpolation
from backend.animation.scalarTrack import _bezierSolveU  # reuse existing solver


# ─────────────────────────────────────────────────────────────────────────────
# PathVertex  (≡ Qteee PathVertex)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PathVertex:
    """
    One bezier control point.
    pos = anchor position (x, y)
    inTangent  = in-handle  RELATIVE offset from pos  (same as Qteee)
    outTangent = out-handle RELATIVE offset from pos
    """
    x:    float = 0.0
    y:    float = 0.0
    inX:  float = 0.0   # in-tangent relative offset
    inY:  float = 0.0
    outX: float = 0.0   # out-tangent relative offset
    outY: float = 0.0
    vid:  str   = field(default_factory=lambda: str(uuid.uuid4()))

    # ── Lerp (used by PathTrack.lerpPath) ────────────────────────────────────
    @staticmethod
    def lerp(a: "PathVertex", b: "PathVertex", t: float) -> "PathVertex":
        def _l(av, bv): return av + t * (bv - av)
        return PathVertex(
            x=_l(a.x, b.x), y=_l(a.y, b.y),
            inX=_l(a.inX, b.inX), inY=_l(a.inY, b.inY),
            outX=_l(a.outX, b.outX), outY=_l(a.outY, b.outY),
            vid=a.vid,
        )

    # ── Serialisation ─────────────────────────────────────────────────────────
    def toDict(self) -> dict:
        return {"x": self.x, "y": self.y,
                "inX": self.inX, "inY": self.inY,
                "outX": self.outX, "outY": self.outY,
                "vid": self.vid}

    @classmethod
    def fromDict(cls, d: dict | list) -> "PathVertex":
        if isinstance(d, (list, tuple)):
            # Legacy compact format [x, y, inX, inY, outX, outY]
            d = dict(zip(["x","y","inX","inY","outX","outY"], d))
        return cls(
            x=float(d.get("x", 0)), y=float(d.get("y", 0)),
            inX=float(d.get("inX", 0)), inY=float(d.get("inY", 0)),
            outX=float(d.get("outX", 0)), outY=float(d.get("outY", 0)),
            vid=d.get("vid", str(uuid.uuid4())),
        )

    def __repr__(self) -> str:
        return f"PathVertex(pos=({self.x:.1f},{self.y:.1f}))"


# ─────────────────────────────────────────────────────────────────────────────
# PathSnapshot  (≡ Qteee MaskPathSnapshot / ShapePathSnapshot)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PathSnapshot:
    """
    Immutable snapshot of a full path at a single point in time.
    Stored as a keyframe value in PathTrack.
    """
    vertices: List[PathVertex] = field(default_factory=list)
    isClosed: bool = False
    # Temporal easing handles (normalized, same as Qteee MaskPathSnapshot)
    interp:        Interpolation = Interpolation.Bezier
    handleInFrame:  float = -5.0
    handleOutFrame: float =  5.0
    handleInValue:  float =  0.0
    handleOutValue: float =  0.0

    def copy(self) -> "PathSnapshot":
        return PathSnapshot(
            vertices=[PathVertex(v.x, v.y, v.inX, v.inY, v.outX, v.outY, v.vid)
                      for v in self.vertices],
            isClosed=self.isClosed,
            interp=self.interp,
            handleInFrame=self.handleInFrame, handleOutFrame=self.handleOutFrame,
            handleInValue=self.handleInValue, handleOutValue=self.handleOutValue,
        )

    def toDict(self) -> dict:
        return {
            "vertices":       [v.toDict() for v in self.vertices],
            "isClosed":       self.isClosed,
            "interp":         self.interp.value,
            "handleInFrame":  self.handleInFrame,
            "handleOutFrame": self.handleOutFrame,
            "handleInValue":  self.handleInValue,
            "handleOutValue": self.handleOutValue,
        }

    @classmethod
    def fromDict(cls, d: dict) -> "PathSnapshot":
        verts = [PathVertex.fromDict(v) for v in d.get("vertices", [])]
        return cls(
            vertices=verts,
            isClosed=d.get("isClosed", False),
            interp=Interpolation(d.get("interp", "bezier")),
            handleInFrame=d.get("handleInFrame", -5.0),
            handleOutFrame=d.get("handleOutFrame", 5.0),
            handleInValue=d.get("handleInValue", 0.0),
            handleOutValue=d.get("handleOutValue", 0.0),
        )


# ─────────────────────────────────────────────────────────────────────────────
# PathTrack  (≡ Qteee pathTrack)
# ─────────────────────────────────────────────────────────────────────────────

class PathTrack:
    """
    A time-ordered map of {frame: PathSnapshot} with lerp-interpolation.
    Matches Qteee pathTrack.evaluateAt() exactly — same centroid-magnitude
    normalization for bezier handles, same lerpPath vertex-by-vertex.
    """

    def __init__(self) -> None:
        self._data: dict[int, PathSnapshot] = {}   # frame → snapshot

    # ── Mutation ─────────────────────────────────────────────────────────────

    def applyValue(self, snap: PathSnapshot, frame: int) -> None:
        """Insert or replace a keyframe snapshot (≡ pathTrack::applyValue)."""
        self._data[frame] = snap.copy()

    def deleteKeyframe(self, frame: int) -> bool:
        return self._data.pop(frame, None) is not None

    def hasKeyframe(self, frame: int) -> bool:
        return frame in self._data

    def clear(self) -> None:
        self._data.clear()

    def empty(self) -> bool:
        return len(self._data) == 0

    def frameIndex(self) -> list[int]:
        return sorted(self._data.keys())

    def snapshotAt(self, frame: int) -> PathSnapshot | None:
        return self._data.get(frame)

    # ── Evaluation (≡ pathTrack::evaluateAt) ─────────────────────────────────

    def evaluateAt(self, frame: int, base: PathSnapshot) -> PathSnapshot:
        """Interpolate between two surrounding keyframe snapshots."""
        if not self._data:
            return base

        frames = sorted(self._data.keys())

        if frame <= frames[0]:
            return self._data[frames[0]]
        if frame >= frames[-1]:
            return self._data[frames[-1]]

        # Find surrounding keyframes
        prev_f = max(f for f in frames if f <= frame)
        next_f = min(f for f in frames if f > frame)
        kf1 = self._data[prev_f]
        kf2 = self._data[next_f]

        frame_range = next_f - prev_f
        raw_t = (frame - prev_f) / frame_range

        eased_t = self._computeEase(raw_t, kf1, kf2, frame_range)
        return PathTrack._lerpPath(kf1, kf2, eased_t)

    def _computeEase(self, raw_t: float, kf1: PathSnapshot,
                     kf2: PathSnapshot, frame_range: int) -> float:
        """≡ pathTrack::evaluateAt ease computation."""
        if kf1.interp == Interpolation.Constant:
            return 0.0
        if kf1.interp == Interpolation.Linear:
            return raw_t

        # Bezier / EaseBoth — normalize handles exactly like Qteee
        norm_out_x = kf1.handleOutFrame / frame_range
        norm_in_x  = 1.0 + kf2.handleInFrame / frame_range

        # Centroid magnitude for Y normalization (same as Qteee centroidMag)
        def centroid_mag(snap: PathSnapshot) -> float:
            if not snap.vertices:
                return 0.0
            cx = sum(v.x for v in snap.vertices) / len(snap.vertices)
            cy = sum(v.y for v in snap.vertices) / len(snap.vertices)
            return (cx * cx + cy * cy) ** 0.5

        v1 = centroid_mag(kf1)
        v2 = centroid_mag(kf2)
        val_delta = v2 - v1

        if abs(val_delta) > 0.001:
            norm_out_y = kf1.handleOutValue / val_delta
            norm_in_y  = 1.0 + kf2.handleInValue / val_delta
        else:
            norm_out_y = 0.0
            norm_in_y  = 1.0

        # Use the existing bezier solver from ScalarTrack
        u = _bezierSolveU(0.0, norm_out_x, norm_in_x, 1.0, raw_t)
        # Evaluate Y at u (same cubic bezier)
        iu = 1.0 - u
        return (iu*iu*iu*0.0 + 3*iu*iu*u*norm_out_y +
                3*iu*u*u*norm_in_y + u*u*u*1.0)

    @staticmethod
    def _lerpPath(a: PathSnapshot, b: PathSnapshot, t: float) -> PathSnapshot:
        """≡ pathTrack::lerpPath — vertex-by-vertex linear interpolation."""
        if len(a.vertices) != len(b.vertices):
            return a   # can't lerp mismatched paths
        result = PathSnapshot(isClosed=a.isClosed)
        result.vertices = [PathVertex.lerp(va, vb, t)
                           for va, vb in zip(a.vertices, b.vertices)]
        return result

    # ── Serialisation ─────────────────────────────────────────────────────────

    def toDict(self) -> list:
        return [{"frame": f, "snapshot": s.toDict()}
                for f, s in sorted(self._data.items())]

    @classmethod
    def fromDict(cls, lst: list) -> "PathTrack":
        pt = cls()
        for entry in lst:
            pt._data[entry["frame"]] = PathSnapshot.fromDict(entry["snapshot"])
        return pt


# ─────────────────────────────────────────────────────────────────────────────
# AnimPathProperty  (≡ Qteee AnimatableProperty<MaskPathSnapshot>)
# ─────────────────────────────────────────────────────────────────────────────

class AnimPathProperty:
    """
    High-level animatable path property.

    Mirrors Qteee AnimatableProperty<MaskPathSnapshot>:
      - setBase(vertices, closed) → set the base / static path
      - addKeyframe(frame)        → snapshot current base as a keyframe
      - update(frame)             → evaluate track, cache result
      - get()                     → returns current PathSnapshot

    The `vertices` property exposes the MUTABLE base vertices so the UI can
    edit them in place. Call addKeyframe() after editing to record them.
    """

    def __init__(self) -> None:
        self._base: PathSnapshot = PathSnapshot()
        self._current: PathSnapshot = PathSnapshot()
        self._isAnimated: bool = False
        self._track: PathTrack = PathTrack()

    # ── Base-value API ────────────────────────────────────────────────────────

    @property
    def vertices(self) -> list[PathVertex]:
        """Mutable list of base path vertices."""
        return self._base.vertices

    @property
    def isClosed(self) -> bool:
        return self._base.isClosed

    @isClosed.setter
    def isClosed(self, v: bool) -> None:
        self._base.isClosed = v

    def setBase(self, vertices: list[PathVertex | dict],
                closed: bool = False) -> None:
        """Set the static base path (≡ setBaseValue in Qteee)."""
        verts = []
        for v in vertices:
            if isinstance(v, dict):
                verts.append(PathVertex.fromDict(v))
            else:
                verts.append(v)
        self._base = PathSnapshot(vertices=verts, isClosed=closed)
        if not self._isAnimated:
            self._current = self._base.copy()

    def setBaseValue(self, snap: PathSnapshot) -> None:
        """Direct snapshot assignment (≡ setBaseValue)."""
        self._base = snap.copy()
        if not self._isAnimated:
            self._current = self._base.copy()

    def getBaseValue(self) -> PathSnapshot:
        return self._base

    # ── Animation API ─────────────────────────────────────────────────────────

    @property
    def isAnimated(self) -> bool:
        return self._isAnimated

    def setAnimated(self, v: bool) -> None:
        self._isAnimated = v
        if not v:
            self._track.clear()

    def addKeyframe(self, frame: int,
                    interp: Interpolation = Interpolation.Bezier,
                    handleInFrame: float = -5.0,
                    handleOutFrame: float = 5.0) -> None:
        """
        Snapshot the current base path as a keyframe at `frame`.
        ≡ Qteee AnimatableProperty<MaskPathSnapshot>::setKeyframe()
        """
        self._isAnimated = True
        snap = self._base.copy()
        snap.interp = interp
        snap.handleInFrame  = handleInFrame
        snap.handleOutFrame = handleOutFrame
        self._track.applyValue(snap, frame)

    def setKeyframeSnapshot(self, frame: int, snap: PathSnapshot) -> None:
        """Store a fully-specified snapshot as a keyframe."""
        self._isAnimated = True
        self._track.applyValue(snap, frame)

    def removeKeyframe(self, frame: int) -> bool:
        return self._track.deleteKeyframe(frame)

    def hasKeyframe(self, frame: int) -> bool:
        return self._track.hasKeyframe(frame)

    def clearAnimation(self) -> None:
        self._track.clear()
        self._isAnimated = False

    @property
    def track(self) -> PathTrack:
        return self._track

    # ── Evaluation ────────────────────────────────────────────────────────────

    def update(self, frame: int) -> None:
        """Evaluate the track at `frame` and cache result (≡ AnimProp::update)."""
        if not self._isAnimated or self._track.empty():
            self._current = self._base.copy()
        else:
            self._current = self._track.evaluateAt(frame, self._base)

    def get(self) -> PathSnapshot:
        """Return the currently evaluated PathSnapshot."""
        return self._current

    def getFlatList(self) -> list[dict]:
        """Return evaluated vertices as [{x,y,inX,inY,outX,outY}] for compositor."""
        return [{"x": v.x, "y": v.y,
                 "inX": v.inX, "inY": v.inY,
                 "outX": v.outX, "outY": v.outY}
                for v in self._current.vertices]

    # ── Serialisation ─────────────────────────────────────────────────────────

    def toDict(self) -> dict:
        d: dict = {
            "base":       self._base.toDict(),
            "isAnimated": self._isAnimated,
        }
        if self._isAnimated:
            d["track"] = self._track.toDict()
        return d

    @classmethod
    def fromDict(cls, d: dict | list) -> "AnimPathProperty":
        ap = cls()
        if isinstance(d, list):
            # Legacy flat list [{x,y,inX,inY,outX,outY}, ...] — static path
            verts = [PathVertex.fromDict(v) for v in d]
            ap._base = PathSnapshot(vertices=verts)
            ap._current = ap._base.copy()
            return ap
        ap._base     = PathSnapshot.fromDict(d.get("base", {}))
        ap._current  = ap._base.copy()
        ap._isAnimated = d.get("isAnimated", False)
        if ap._isAnimated and "track" in d:
            ap._track = PathTrack.fromDict(d["track"])
        return ap

    def __repr__(self) -> str:
        n = len(self._current.vertices)
        a = f" [{len(self._track.frameIndex())} kf]" if self._isAnimated else ""
        return f"AnimPathProperty({n} pts{a})"
