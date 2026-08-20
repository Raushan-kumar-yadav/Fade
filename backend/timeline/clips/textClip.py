"""
TextClip — Skia-rendered text layer.

Mirrors Qteee-Vulkan's TextClip + TextLayoutSettings + TextStylingSettings,
adapted for Python + skia-python (CPU raster surface).
"""
from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from backend.timeline.clips.baseClip import BaseClip
from backend.animation.transform import Transform


@dataclass
class TextStyle:
    """Mirrors TextLayoutSettings + TextStylingSettings + TextFormatSettings."""
    # Content
    text:           str   = "New Text"
    # Font
    fontFamily:     str   = "Arial"
    fontSize:       float = 48.0
    bold:           bool  = False
    italic:         bool  = False
    # Layout
    alignment:      str   = "left"      # left | center | right
    lineHeight:     float = 1.2
    letterSpacing:  float = 0.0
    wordSpacing:    float = 0.0
    maxWidth:       float = 0.0         # 0 = no wrap
    allCaps:        bool  = False
    # Fill
    color:          list  = field(default_factory=lambda: [1.0, 1.0, 1.0, 1.0])   # RGBA 0-1
    # Stroke
    strokeColor:    list  = field(default_factory=lambda: [0.0, 0.0, 0.0, 1.0])
    strokeWidth:    float = 0.0
    # Shadow
    shadowEnabled:  bool  = False
    shadowColor:    list  = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.6])
    shadowOffsetX:  float = 4.0
    shadowOffsetY:  float = 4.0
    shadowBlur:     float = 6.0
    # Background box (like Qteee TextBackgroundSettings)
    bgEnabled:      bool  = False
    bgColor:        list  = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.5])
    bgPaddingX:     float = 20.0
    bgPaddingY:     float = 10.0
    bgCornerRadius: float = 0.0

    def toDict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def fromDict(cls, d: dict) -> "TextStyle":
        obj = cls()
        for k, v in d.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        return obj


@dataclass
class MaskLayer:
    """Single mask — mirrors clipMask.hpp."""
    maskId:    str   = field(default_factory=lambda: str(uuid.uuid4()))
    name:      str   = "Mask 1"
    shape:     str   = "rect"          # rect | ellipse | bezier
    mode:      str   = "add"           # add | subtract
    inverted:  bool  = False
    feather:   float = 0.0             # blur sigma
    opacity:   float = 1.0
    # Bezier points: [{x, y, inX, inY, outX, outY}]
    points:    list  = field(default_factory=list)

    def toDict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def fromDict(cls, d: dict) -> "MaskLayer":
        obj = cls()
        for k, v in d.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        return obj


class TextClip(BaseClip):
    """Skia-rendered text clip. Rendered by TextNode via render()."""

    clipType = "text"

    def __init__(
        self,
        clipId:     str,
        startFrame: int,
        duration:   int,
        style:      TextStyle | None = None,
    ) -> None:
        super().__init__(clipId, startFrame, duration)
        self.style:  TextStyle   = style or TextStyle()
        self.masks:  list[MaskLayer] = []

    # ── Render (called by ClipNode) ─────────────────────────────────────────

    def render(self, canvas, frame: int) -> None:
        from backend.rendering.nodes.textNode import draw_text
        draw_text(canvas, self, frame)

    def getThumbnail(self, frame: int, width: int = 160, height: int = 90) -> bytes:
        import skia
        info = skia.ImageInfo.MakeN32Premul(width, height)
        surf = skia.Surface.MakeRaster(info)
        c = surf.getCanvas()
        c.clear(skia.ColorSetARGB(200, 20, 20, 30))
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
    def fromDict(cls, data: dict) -> "TextClip":
        clip = cls(
            clipId     = data["clipId"],
            startFrame = data["startFrame"],
            duration   = data["duration"],
            style      = TextStyle.fromDict(data.get("style", {})),
        )
        clip.transform = Transform.fromDict(data.get("transform", {}))
        clip.masks     = [MaskLayer.fromDict(m) for m in data.get("masks", [])]
        return clip

    def __repr__(self) -> str:
        return (
            f"TextClip(id={self.clipId!r}, "
            f"text={self.style.text!r}, "
            f"start={self.startFrame}, dur={self.duration})"
        )
