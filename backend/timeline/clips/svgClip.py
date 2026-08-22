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
        px, py = self.transform.position.get()
        sx, sy = self.transform.scale.get()
        ax, ay = self.transform.anchor.get()
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
            "transform": {
                "x": px, "y": py,
                "scaleX": sx, "scaleY": sy,
                "rotation": self.transform.rotation.get(),
                "anchorX": ax, "anchorY": ay,
                "opacity": self.transform.opacity.get(),
            },
        }

    @classmethod
    def fromDict(cls, data: dict) -> "SvgClip":
        clip = cls(
            filepath=data["filepath"],
            startFrame=data["startFrame"],
            duration=data["duration"],
            clipId=data.get("clipId"),
            displayW=data.get("displayW", 0.0),
            displayH=data.get("displayH", 0.0),
        )
        clip.tintEnabled = data.get("tintEnabled", False)
        clip.tintColor   = data.get("tintColor", [1.0, 1.0, 1.0, 1.0])

        t = data.get("transform", {})
        clip.transform.position.setBase(t.get("x", 0.0), t.get("y", 0.0))
        clip.transform.scale.setBase(t.get("scaleX", 1.0), t.get("scaleY", 1.0))
        clip.transform.rotation.setBaseValue(t.get("rotation", 0.0))
        clip.transform.opacity.setBaseValue(t.get("opacity", 1.0))
        clip.transform.anchor.setBase(t.get("anchorX", 0.0), t.get("anchorY", 0.0))
        return clip

    def __repr__(self) -> str:
        return (
            f"SvgClip(id={self.clipId!r}, "
            f"file={os.path.basename(self.filepath)!r}, "
            f"start={self.startFrame}, dur={self.duration})"
        )
