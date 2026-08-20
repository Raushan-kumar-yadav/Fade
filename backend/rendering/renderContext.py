from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import skia
    from backend.timeline.clips.baseClip import BaseClip


@dataclass
class RenderContext:
   
    canvas: "skia.Canvas"
    frame: int
    width: int
    height: int
    fps: float = 30.0
    panX: float = 0.0
    panY: float = 0.0
    zoom: float = 1.0
    scheduler: object = None         

    def makeOffscreenSurface(self, w: int = 0, h: int = 0) -> "skia.Surface":
     
        import skia
        width  = max(1, w or self.width)
        height = max(1, h or self.height)
        info   = skia.ImageInfo.MakeN32Premul(width, height)
        surf   = skia.Surface.MakeRaster(info)
        if surf is None:
            raise RuntimeError(
                f"skia.Surface.MakeRaster({width}x{height}) returned None — "
                "out of memory or invalid dimensions"
            )
        return surf
