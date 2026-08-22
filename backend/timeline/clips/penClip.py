"""
penClip.py — Bezier pen/path clip with a Qteee-style AnimPathProperty.

`self.shapePath` mirrors Qteee CustomPathData.shapePath:
  AnimatableProperty<MaskPathSnapshot>  →  AnimPathProperty

To animate the path:
    clip.shapePath.addKeyframe(frame=0)       # snapshot current path
    clip.shapePath.vertices[1].x = 400        # move a point
    clip.shapePath.addKeyframe(frame=30)      # snapshot morphed path

evaluateAll(frame) is called by the compositor and evaluates the path track.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from backend.timeline.clips.baseClip import BaseClip
from backend.animation.transform import Transform
from backend.timeline.clips.textClip import MaskLayer
from backend.timeline.clips.shapeClip import ShapeStyle
from backend.animation.animPath import (
    AnimPathProperty, PathVertex, PathSnapshot
)


# ── Legacy BezierPoint (kept for external callers / backwards compat) ────────

@dataclass
class BezierPoint:
    """Static bezier point. Use PathVertex for animated paths."""
    x: float = 0.0;  y: float = 0.0
    inX: float = 0.0; inY: float = 0.0
    outX: float = 0.0; outY: float = 0.0

    def toDict(self) -> dict:
        return {"x": self.x, "y": self.y,
                "inX": self.inX, "inY": self.inY,
                "outX": self.outX, "outY": self.outY}

    @classmethod
    def fromDict(cls, d: dict) -> "BezierPoint":
        return cls(x=d.get("x", 0.0), y=d.get("y", 0.0),
                   inX=d.get("inX", 0.0), inY=d.get("inY", 0.0),
                   outX=d.get("outX", 0.0), outY=d.get("outY", 0.0))


# ── PenClip ──────────────────────────────────────────────────────────────────

class PenClip(BaseClip):
    """
    Bezier pen/custom-path clip.

    `self.shapePath`  ≡  Qteee CustomPathData.shapePath
                          AnimatableProperty<MaskPathSnapshot>

    `self.isClosed`   ≡  CustomPathData.isClosed
    """

    clipType = "pen"

    def __init__(
        self,
        clipId: str,
        startFrame: int,
        duration: int,
        isClosed: bool = False,
        style: ShapeStyle | None = None,
    ) -> None:
        super().__init__(clipId, startFrame, duration)
        self.shapePath: AnimPathProperty = AnimPathProperty()
        self.isClosed: bool = isClosed
        self.style:    ShapeStyle = style or ShapeStyle(shapeType="custom_path")
        self.masks:    list[MaskLayer] = []

    # ── Legacy `points` property (for renderers) ──────────────────────────────

    @property
    def points(self) -> list[PathVertex]:
        """Current evaluated vertices (post-interpolation)."""
        return self.shapePath.get().vertices

    def addPoint(self, x=0.0, y=0.0,
                 inX=0.0, inY=0.0, outX=0.0, outY=0.0) -> PathVertex:
        """Append a static point to the base path."""
        v = PathVertex(x=x, y=y, inX=inX, inY=inY, outX=outX, outY=outY)
        self.shapePath.vertices.append(v)
        # Keep base snapshot in sync (≡ CustomPathData::syncPointsToBaseValue)
        self._syncBase()
        return v

    def _syncBase(self) -> None:
        """Sync self.shapePath.vertices into base snapshot (≡ syncPointsToBaseValue)."""
        snap = PathSnapshot(
            vertices=list(self.shapePath.vertices),
            isClosed=self.isClosed,
        )
        self.shapePath.setBaseValue(snap)

    # ── evaluateAll (≡ CustomPathData::generatePath) ─────────────────────────

    def evaluateAll(self, frame: int) -> None:
        super().evaluateAll(frame)
        lf = self.localFrame(frame)
        # Keep base in sync with any UI edits, then evaluate animated track
        self._syncBase()
        self.shapePath.update(lf)

    # ── Style param animation ─────────────────────────────────────────────────

    def applyParam(self, key: str, val: float) -> None:
        super().applyParam(key, val)
        if   key == "stroke_r": self.style.strokeColor[0] = val
        elif key == "stroke_g": self.style.strokeColor[1] = val
        elif key == "stroke_b": self.style.strokeColor[2] = val
        elif key == "stroke_w": self.style.strokeWidth = val
        elif key == "fill_a":   self.style.fillColor[3] = val

    # ── Render ────────────────────────────────────────────────────────────────

    def render(self, canvas, frame: int) -> None:
        from backend.rendering.nodes.penNode import draw_pen
        draw_pen(canvas, self, frame)

    def getThumbnail(self, frame: int, width: int = 160, height: int = 90) -> bytes:
        try:
            import skia
            surf = skia.Surface.MakeRaster(skia.ImageInfo.MakeN32Premul(width, height))
            c = surf.getCanvas()
            c.clear(skia.ColorSetARGB(200, 15, 15, 20))
            self.render(c, frame)
            return bytes(surf.makeImageSnapshot().encodeToData(skia.kJPEG, 80))
        except Exception:
            return b""

    # ── Mask helpers ──────────────────────────────────────────────────────────

    def addMask(self, mask: MaskLayer) -> None:
        self.masks.append(mask)

    def removeMask(self, maskId: str) -> bool:
        before = len(self.masks)
        self.masks = [m for m in self.masks if m.maskId != maskId]
        return len(self.masks) < before

    # ── Serialisation ─────────────────────────────────────────────────────────

    def toDict(self) -> dict:
        return {
            "clipType":   self.clipType,
            "clipId":     self.clipId,
            "startFrame": self.startFrame,
            "duration":   self.duration,
            "isClosed":   self.isClosed,
            "shapePath":  self.shapePath.toDict(),
            "transform":  self.transform.toDict(),
            "style":      self.style.toDict(),
            "masks":      [m.toDict() for m in self.masks],
        }

    @classmethod
    def fromDict(cls, data: dict) -> "PenClip":
        clip = cls(
            clipId     = data["clipId"],
            startFrame = data["startFrame"],
            duration   = data["duration"],
            isClosed   = data.get("isClosed", False),
            style      = ShapeStyle.fromDict(data.get("style", {})),
        )
        clip.transform = Transform.fromDict(data.get("transform", {}))
        clip.masks     = [MaskLayer.fromDict(m) for m in data.get("masks", [])]

        # Support new "shapePath" key, old "path" key, and legacy "points" list
        raw = data.get("shapePath", data.get("path", data.get("points", [])))
        clip.shapePath = AnimPathProperty.fromDict(
            raw if isinstance(raw, (dict, list)) else []
        )
        return clip
