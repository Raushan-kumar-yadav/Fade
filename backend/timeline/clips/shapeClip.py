"""
ShapeClip — Skia-rendered shape layer.

Shape types: rect / circle / ellipse / star / polygon / line / arc / custom_path
Mirrors Qteee-Vulkan's ShapeData hierarchy and ShapeClip.
"""
from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from backend.timeline.clips.baseClip import BaseClip
from backend.animation.transform import Transform
from backend.timeline.clips.textClip import MaskLayer   # shared mask model


@dataclass
class ShapeStyle:
    """
    Mirrors Qteee ShapeData appearance properties.
    All values are Python scalars (not AnimatableProperty — we add keyframes later).
    """
    shapeType:      str   = "rect"     # rect|circle|ellipse|star|polygon|line|arc
    # Rect / rounded rect
    width:          float = 200.0
    height:         float = 120.0
    cornerRadius:   float = 0.0
    # Circle / Ellipse
    radiusX:        float = 100.0
    radiusY:        float = 80.0
    # Star
    outerRadius:    float = 100.0
    innerRadius:    float = 40.0
    numPoints:      int   = 5
    # Polygon
    numSides:       int   = 6
    polygonRadius:  float = 100.0
    # Line
    x1: float = -100.0; y1: float = 0.0
    x2: float =  100.0; y2: float = 0.0
    # Arc
    arcStartAngle:  float = 0.0
    arcSweepAngle:  float = 180.0
    arcRadius:      float = 100.0
    # Fill
    fillColor:      list  = field(default_factory=lambda: [0.4, 0.4, 1.0, 1.0])
    fillOpacity:    float = 1.0
    # Stroke
    strokeColor:    list  = field(default_factory=lambda: [1.0, 1.0, 1.0, 1.0])
    strokeWidth:    float = 0.0
    strokeStyle:    str   = "center"   # center | inside | outside
    # Shadow (mirrors Qteee ShapeData shadow fields)
    shadowEnabled:  bool  = False
    shadowColor:    list  = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.75])
    shadowAngle:    float = 135.0      # degrees
    shadowDistance: float = 10.0
    shadowBlur:     float = 5.0

    def toDict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def fromDict(cls, d: dict) -> "ShapeStyle":
        obj = cls()
        for k, v in d.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        return obj


class ShapeClip(BaseClip):
    """Skia-rendered shape clip. Rendered by ShapeNode via render()."""

    clipType = "shape"

    def __init__(
        self,
        clipId:     str,
        startFrame: int,
        duration:   int,
        style:      ShapeStyle | None = None,
    ) -> None:
        super().__init__(clipId, startFrame, duration)
        self.style = style or ShapeStyle()
        self.masks: list[MaskLayer] = []

    # ── Render ──────────────────────────────────────────────────────────────

    def render(self, canvas, frame: int) -> None:
        from backend.rendering.nodes.shapeNode import draw_shape
        draw_shape(canvas, self, frame)

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

    def getMask(self, maskId: str) -> MaskLayer | None:
        return next((m for m in self.masks if m.maskId == maskId), None)

    # ── Serialization ───────────────────────────────────────────────────────

    def toDict(self) -> dict:
        return {
            "clipType":   self.clipType,
            "clipId":     self.clipId,
            "startFrame": self.startFrame,
            "duration":   self.duration,
            "transform":  self.transform.toDict(),
            "style":      self.style.toDict(),
            "masks":      [m.toDict() for m in self.masks],
        }

    @classmethod
    def fromDict(cls, data: dict) -> "ShapeClip":
        clip = cls(
            clipId     = data["clipId"],
            startFrame = data["startFrame"],
            duration   = data["duration"],
            style      = ShapeStyle.fromDict(data.get("style", {})),
        )
        clip.transform = Transform.fromDict(data.get("transform", {}))
        clip.masks     = [MaskLayer.fromDict(m) for m in data.get("masks", [])]
        return clip
