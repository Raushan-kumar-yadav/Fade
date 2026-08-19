from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import skia
    from backend.timeline.clips.baseClip import BaseClip


@dataclass
class RenderContext:
    """
    Immutable context passed down through every node's execute().
    Python equivalent of C++ RenderContext struct.

    canvas      — the FINAL output canvas (written to by OutputNode only)
    frame       — current timeline frame number
    width/height— composition dimensions in pixels
    scheduler   — DecodeScheduler for frame cache lookups
    """
    canvas:    "skia.Canvas"
    frame:     int
    width:     int
    height:    int
    fps:       float = 30.0
    panX:      float = 0.0
    panY:      float = 0.0
    zoom:      float = 1.0
    scheduler: object = None        # DecodeScheduler | None

    def makeOffscreenSurface(self, w: int = 0, h: int = 0) -> "skia.Surface":
        """
        Create a temporary Skia raster surface for intermediate rendering.
        Each ClipNode/EffectNode draws into its own offscreen surface,
        then the result is composited by MergeNode.
        """
        import skia
        return skia.Surface(w or self.width, h or self.height)
