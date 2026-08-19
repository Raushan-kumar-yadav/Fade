from __future__ import annotations
import skia
from backend.rendering.graph.graphBuilder import GraphBuilder
from backend.rendering.renderContext import RenderContext


class Compositor:
    """
    Orchestrates one frame of rendering via the Render DAG.
    Port of C++ Compositor — minus Vulkan (we use Skia CPU/raster here).

    Render loop per frame:
      1. GraphBuilder.build()   → create a fresh DAG from the timeline
      2. graph.compile()        → Kahn's topo sort
      3. graph.execute(ctx)     → run nodes in sorted order
      4. Snapshot the surface   → return JPEG bytes for the preview stream

    The graph is rebuilt every frame (cheap: O(clips + effects)).
    Kahn's sort is also per-frame (O(V+E), dominated by clip count).
    """

    def __init__(self, width: int, height: int, fps: float = 30.0) -> None:
        self.width  = width
        self.height = height
        self.fps    = fps

        # Single persistent surface — avoids reallocating every frame
        self._surface = skia.Surface(width, height)

    def renderFrame(
        self,
        timeline,
        frame:     int,
        panX:      float = 0.0,
        panY:      float = 0.0,
        zoom:      float = 1.0,
        scheduler  = None,
    ) -> skia.Image:
        """
        Render one frame and return a Skia Image snapshot.
        Called by Engine's preview loop.
        """
        canvas = self._surface.getCanvas()
        canvas.clear(skia.Color4f(0, 0, 0, 1))   # black background

        if timeline is None or len(timeline.tracks) == 0:
            return self._surface.makeImageSnapshot()

        # 1. Build DAG
        graph = GraphBuilder.build(timeline, frame)

        # 2. Kahn's topological sort
        graph.compile()

        # 3. Create context and execute
        ctx = RenderContext(
            canvas    = canvas,
            frame     = frame,
            width     = self.width,
            height    = self.height,
            fps       = self.fps,
            panX      = panX,
            panY      = panY,
            zoom      = zoom,
            scheduler = scheduler,
        )
        graph.execute(ctx)

        # 4. Return snapshot
        return self._surface.makeImageSnapshot()

    def renderJpeg(
        self,
        timeline,
        frame:   int,
        quality: int   = 85,
        panX:    float = 0.0,
        panY:    float = 0.0,
        zoom:    float = 1.0,
        scheduler      = None,
    ) -> bytes:
        """Return JPEG bytes — used by the Engine preview loop and REST endpoint."""
        img  = self.renderFrame(timeline, frame, panX, panY, zoom, scheduler)
        data = img.encodeToData(skia.kJPEG, quality)
        return bytes(data)

    def renderThumbnail(
        self,
        timeline,
        frame:   int,
        width:   int = 320,
        height:  int = 180,
        quality: int = 70,
    ) -> bytes:
        """Render a small thumbnail — used for timeline strips."""
        img  = self.renderFrame(timeline, frame)
        # Rescale
        resized = img.resize(skia.ISize(width, height))
        if resized is None:
            resized = img
        data = resized.encodeToData(skia.kJPEG, quality)
        return bytes(data)

    def resize(self, width: int, height: int) -> None:
        """Called when the project resolution changes."""
        if width != self.width or height != self.height:
            self.width    = width
            self.height   = height
            self._surface = skia.Surface(width, height)
