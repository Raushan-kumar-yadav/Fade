"""
PenClip — Bezier pen path clip.

Mirrors Qteee-Vulkan's CustomPathData: stores BezierPoints with
in/out tangents and generates SkPath via cubic bezier segments.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from backend.timeline.clips.baseClip import BaseClip
from backend.animation.transform import Transform
from backend.timeline.clips.textClip import MaskLayer
from backend.timeline.clips.shapeClip import ShapeStyle


@dataclass
class BezierPoint:
    """
    Mirrors Qteee BezierPoint + Qteee PathVertex.
    pos = anchor, inTangent/outTangent are relative offsets from pos.
    """
    x:    float = 0.0
    y:    float = 0.0
    inX:  float = 0.0   # in-tangent relative offset
    inY:  float = 0.0
    outX: float = 0.0   # out-tangent relative offset
    outY: float = 0.0

    def toDict(self) -> dict:
        return {"x": self.x, "y": self.y,
                "inX": self.inX, "inY": self.inY,
                "outX": self.outX, "outY": self.outY}

    @classmethod
    def fromDict(cls, d: dict) -> "BezierPoint":
        return cls(
            x=d.get("x", 0.0), y=d.get("y", 0.0),
            inX=d.get("inX", 0.0), inY=d.get("inY", 0.0),
            outX=d.get("outX", 0.0), outY=d.get("outY", 0.0),
        )


class PenClip(BaseClip):
    """
    Skia-rendered pen/bezier-path clip.

    points:   list of BezierPoint
    isClosed: whether the path is closed (last ↔ first)
    style:    fill + stroke + shadow appearance (reuses ShapeStyle)
    """

    clipType = "pen"

    def __init__(
        self,
        clipId:     str,
        startFrame: int,
        duration:   int,
        points:     list[BezierPoint] | None = None,
        isClosed:   bool = False,
        style:      ShapeStyle | None = None,
    ) -> None:
        super().__init__(clipId, startFrame, duration)
        self.points:   list[BezierPoint] = points or []
        self.isClosed: bool              = isClosed
        self.style:    ShapeStyle        = style or ShapeStyle(shapeType="custom_path")
        self.masks:    list[MaskLayer]   = []

    # ── Render ──────────────────────────────────────────────────────────────

    def applyParam(self, key: str, val: float) -> None:
        super().applyParam(key, val)
        if key == "stroke_r":    self.style.strokeColor[0] = val
        elif key == "stroke_g":  self.style.strokeColor[1] = val
        elif key == "stroke_b":  self.style.strokeColor[2] = val
        elif key == "stroke_w":  self.style.strokeWidth = val
        elif key == "fill_a":    self.style.fillColor[3] = val

    def render(self, canvas, frame: int) -> None:
        from backend.rendering.nodes.penNode import draw_pen
        draw_pen(canvas, self, frame)

    def getThumbnail(self, frame: int, width: int = 160, height: int = 90) -> bytes:
        import skia
        info = skia.ImageInfo.MakeN32Premul(width, height)
        surf = skia.Surface.MakeRaster(info)
        c = surf.getCanvas()
        c.clear(skia.ColorSetARGB(200, 15, 15, 20))
        self.render(c, frame)
        data = surf.makeImageSnapshot().encodeToData(skia.kJPEG, 80)
        return bytes(data)

    # ── Mask helpers ────────────────────────────────────────────────────────

    def addMask(self, mask: MaskLayer) -> None:
        self.masks.append(mask)

    def removeMask(self, maskId: str) -> bool:
        before = len(self.masks)
        self.masks = [m for m in self.masks if m.maskId != maskId]
        return len(self.masks) < before

    # ── Serialization ───────────────────────────────────────────────────────

    def toDict(self) -> dict:
        return {
            "clipType":   self.clipType,
            "clipId":     self.clipId,
            "startFrame": self.startFrame,
            "duration":   self.duration,
            "isClosed":   self.isClosed,
            "points":     [p.toDict() for p in self.points],
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
            points     = [BezierPoint.fromDict(p) for p in data.get("points", [])],
            style      = ShapeStyle.fromDict(data.get("style", {})),
        )
        clip.transform = Transform.fromDict(data.get("transform", {}))
        clip.masks     = [MaskLayer.fromDict(m) for m in data.get("masks", [])]
        return clip
