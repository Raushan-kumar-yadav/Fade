"""svgClip.py — SVG clip for Fade's timeline.

Mirrors Qteee-Vulkan svgClip adapted to Python:
  - Clip type = "svg"
  - `file` is the absolute path to the .svg file
  - Optional display size override (displayW / displayH in pixels)
  - Optional tint color [R, G, B, A] in 0-1 range
  - Full transform / opacity / blendMode support via BaseClip.Transform
"""
from __future__ import annotations

import os
import uuid
from backend.timeline.clips.baseClip import BaseClip


class SvgClip(BaseClip):
    CLIP_TYPE = "svg"

    def __init__(
        self,
        filepath: str,
        startFrame: int,
        duration: int,
        clipId: str | None = None,
        displayW: float = 0.0,
        displayH: float = 0.0,
    ) -> None:
        super().__init__(
            clipId=clipId or str(uuid.uuid4()),
            startFrame=startFrame,
            duration=duration,
        )
        self.filepath: str = os.path.normpath(filepath)

        # Display size override — 0 means "use full compositor canvas"
        self.displayW: float = displayW
        self.displayH: float = displayH

        # Tint / recolor
        self.tintEnabled: bool = False
        self.tintColor: list[float] = [1.0, 1.0, 1.0, 1.0]  # RGBA 0-1

    # ── BaseClip abstract overrides ──────────────────────────────────────────

    def render(self, canvas, frame: int) -> None:
        """Python-side render (Skia canvas).
        The C++ HeadlessCompositor handles SVG; this is a CPU-side fallback.
        """
        try:
            import skia
        except ImportError:
            return

        try:
            stream = skia.DynamicMemoryWStream()
            with open(self.filepath, "rb") as f:
                data = f.read()
            if not data:
                return
            # Skia Python bindings don't expose SkSVGDOM yet — draw placeholder
            paint = skia.Paint(Color=skia.ColorRED, StrokeWidth=2,
                               Style=skia.Paint.kStroke_Style)
            canvas.drawRect(skia.Rect.MakeXYWH(0, 0, 400, 300), paint)
        except Exception:
            pass

    def getThumbnail(self, frame: int, width: int = 160, height: int = 90) -> bytes:
        """Return a simple coloured JPEG as thumbnail placeholder."""
        try:
            import skia
            surface = skia.Surface(width, height)
            with surface as canvas:
                canvas.clear(skia.Color4f(0.2, 0.4, 0.8, 1.0))
                p = skia.Paint(Color=skia.ColorWHITE)
                canvas.drawSimpleText(
                    "SVG", width / 2 - 20, height / 2 + 8,
                    skia.Font(None, 20), p,
                )
            image = surface.makeImageSnapshot()
            return image.encodeToData().bytes()
        except Exception:
            return b""

    def sourceFrame(self, _frame: int) -> int:
        return 0  # SVGs are static; no decoding needed

    # ── Serialisation ────────────────────────────────────────────────────────

    def toDict(self) -> dict:
        return {
            "clipId":      self.clipId,
            "type":        self.CLIP_TYPE,
            "filepath":    self.filepath,
            "startFrame":  self.startFrame,
            "duration":    self.duration,
            "displayW":    self.displayW,
            "displayH":    self.displayH,
            "tintEnabled": self.tintEnabled,
            "tintColor":   self.tintColor,
            "transform":   self.transform.toDict(),   # full keyframe-aware dict
            "effects":     [e.toDict() for e in self.effects],
        }

    @classmethod
    def fromDict(cls, data: dict) -> "SvgClip":
        from backend.animation.transform import Transform
        from backend.timeline.effects.skslEffect import SkslEffect
        clip = cls(
            filepath   = data["filepath"],
            startFrame = data["startFrame"],
            duration   = data["duration"],
            clipId     = data.get("clipId"),
            displayW   = data.get("displayW", 0.0),
            displayH   = data.get("displayH", 0.0),
        )
        clip.tintEnabled = data.get("tintEnabled", False)
        clip.tintColor   = data.get("tintColor", [1.0, 1.0, 1.0, 1.0])

        t = data.get("transform", {})
        # New format: full Transform dict (has "position", "scale", etc.)
        if "position" in t or "scale" in t:
            clip.transform = Transform.fromDict(t)
        else:
            # Legacy flat format: {x, y, scaleX, scaleY, rotation, opacity, anchorX, anchorY}
            clip.transform.position.setBase(t.get("x", 0.0), t.get("y", 0.0))
            clip.transform.scale.setBase(t.get("scaleX", 1.0), t.get("scaleY", 1.0))
            clip.transform.rotation.setBaseValue(t.get("rotation", 0.0))
            clip.transform.opacity.setBaseValue(t.get("opacity", 1.0))
            clip.transform.anchor.setBase(t.get("anchorX", 0.0), t.get("anchorY", 0.0))

        for ed in data.get("effects", []):
            if ed.get("type", "").startswith("sksl:") or "typeId" in ed:
                try:
                    clip.effects.append(SkslEffect.fromDict(ed))
                except Exception as ex:
                    print(f"[SvgClip] effect restore failed: {ex}")
        return clip


    def __repr__(self) -> str:
        return (
            f"SvgClip(id={self.clipId!r}, "
            f"file={os.path.basename(self.filepath)!r}, "
            f"start={self.startFrame}, dur={self.duration})"
        )
