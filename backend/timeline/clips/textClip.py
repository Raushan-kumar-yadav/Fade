 
from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from backend.timeline.clips.baseClip import BaseClip
from backend.animation.transform import Transform
from backend.animation.animPath import AnimPathProperty, PathVertex
from backend.animation.animatableProperty import AnimatableProperty, Vec2Property


@dataclass
class TextStyle:
     
    # Content
    text: str   = "New Text"
    # Font
    fontFamily: str   = "Arial"
    fontSize: float = 48.0
    bold: bool  = False
    italic: bool  = False
    # Layout
    alignment: str   = "left"      # left | center | right
    lineHeight: float = 1.2
    letterSpacing: float = 0.0
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
    # Background box  
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


class MaskLayer:
    """
    Single mask layer.
    Mirrors Qteee clipMask exactly:
      maskPath   ≡  AnimatableProperty<MaskPathSnapshot>  (AnimPathProperty)
      feather    ≡  AnimatableProperty<float>
      opacity    ≡  AnimatableProperty<float>
      expansion  ≡  AnimatableProperty<float>
      size       ≡  AnimatableProperty<float>
      position   ≡  AnimatableProperty<glm::vec2>  (Vec2Property)
      rotation   ≡  AnimatableProperty<float>
    """

    def __init__(
        self,
        maskId:   str  = None,
        name:     str  = "Mask 1",
        shape:    str  = "rect",    # rect | ellipse | bezier
        mode:     str  = "add",     # add | subtract
        inverted: bool = False,
    ) -> None:
        self.maskId:   str  = maskId or str(uuid.uuid4())
        self.name:     str  = name
        self.shape:    str  = shape
        self.mode:     str  = mode
        self.inverted: bool = inverted

        # Animatable scalar/vec properties (≡ clipMask member fields)
        self.feather:   AnimatableProperty = AnimatableProperty(0.0)
        self.opacity:   AnimatableProperty = AnimatableProperty(1.0)
        self.expansion: AnimatableProperty = AnimatableProperty(0.0)
        self.size:      AnimatableProperty = AnimatableProperty(100.0)
        self.position:  Vec2Property       = Vec2Property(0.0, 0.0)
        self.rotation:  AnimatableProperty = AnimatableProperty(0.0)

        # Animated bezier path (≡ clipMask::m_maskPath)
        self.maskPath: AnimPathProperty = AnimPathProperty()

    # ── Legacy `points` property ─────────────────────────────────────────────
    @property
    def points(self) -> list[PathVertex]:
        """Evaluated vertices from the current frame snapshot."""
        return self.maskPath.get().vertices

    # ── Evaluation (≡ clipMask::update) ──────────────────────────────────────
    def evaluateAll(self, frame: int) -> None:
        """Tick all animatable properties (≡ clipMask::update)."""
        self.feather.update(frame)
        self.opacity.update(frame)
        self.expansion.update(frame)
        self.size.update(frame)
        self.position.update(frame)
        self.rotation.update(frame)
        self.maskPath.update(frame)

    # ── Serialisation ─────────────────────────────────────────────────────────
    def toDict(self) -> dict:
        def _ap(p: AnimatableProperty) -> dict:
            d: dict = {"base": p.baseValue}
            if p.isAnimated:
                d["animated"] = True
                d["keyframes"] = [
                    {"frame": kf.frame, "value": kf.value,
                     "interp": kf.interp.value}
                    for kf in p.track.keyframes()
                ]
            return d

        return {
            "maskId":    self.maskId,
            "name":      self.name,
            "shape":     self.shape,
            "mode":      self.mode,
            "inverted":  self.inverted,
            "feather":   _ap(self.feather),
            "opacity":   _ap(self.opacity),
            "expansion": _ap(self.expansion),
            "size":      _ap(self.size),
            "position":  {"x": self.position.x.baseValue,
                          "y": self.position.y.baseValue},
            "rotation":  _ap(self.rotation),
            "maskPath":  self.maskPath.toDict(),
        }

    @classmethod
    def fromDict(cls, d: dict) -> "MaskLayer":
        from backend.animation.keyframe import Keyframe, Interpolation

        ml = cls(
            maskId   = d.get("maskId"),
            name     = d.get("name",     "Mask 1"),
            shape    = d.get("shape",    "rect"),
            mode     = d.get("mode",     "add"),
            inverted = d.get("inverted", False),
        )

        def _load(prop: AnimatableProperty, v) -> None:
            if isinstance(v, (int, float)):
                prop.setBaseValue(float(v))
                return
            prop.setBaseValue(v.get("base", prop.baseValue))
            if v.get("animated"):
                prop.setAnimated(True)
                for kd in v.get("keyframes", []):
                    kf = Keyframe(kd["frame"], kd["value"],
                                  Interpolation(kd.get("interp", "bezier")))
                    prop.track.insertKeyframe(kf)

        _load(ml.feather,   d.get("feather",   0.0))
        _load(ml.opacity,   d.get("opacity",   1.0))
        _load(ml.expansion, d.get("expansion", 0.0))
        _load(ml.size,      d.get("size",      100.0))
        _load(ml.rotation,  d.get("rotation",  0.0))

        pos = d.get("position", {})
        if isinstance(pos, dict):
            ml.position.setBase(pos.get("x", 0.0), pos.get("y", 0.0))

        # Support new "maskPath", old "path", and legacy "points" list
        raw = d.get("maskPath", d.get("path", d.get("points", [])))
        ml.maskPath = AnimPathProperty.fromDict(
            raw if isinstance(raw, (dict, list)) else []
        )
        return ml


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

    # ── Render (called by ClipNode)  

    def applyParam(self, key: str, val: float) -> None:
        super().applyParam(key, val)
        if key == "font_size":   self.style.fontSize = val
        elif key == "tracking":  self.style.letterSpacing = val
        elif key == "line_height": self.style.lineHeight = val
        elif key == "fill_r":    self.style.color[0] = val
        elif key == "fill_g":    self.style.color[1] = val
        elif key == "fill_b":    self.style.color[2] = val
        elif key == "fill_a":    self.style.color[3] = val

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

    def evaluateAll(self, frame: int) -> None:
        """Tick transform + mask path animations."""
        super().evaluateAll(frame)
        lf = self.localFrame(frame)
        for mask in self.masks:
            mask.evaluateAll(lf)

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
