from __future__ import annotations
import skia
from backend.rendering.graph.baseNode import BaseNode, RenderResult
from backend.rendering.renderContext import RenderContext


class MergeNode(BaseNode):
  

    def __init__(self, trackId: str, trackOpacity: float = 1.0) -> None:
        super().__init__(f"merge_{trackId}")
        self.trackOpacity = trackOpacity

    def execute(self, ctx: RenderContext) -> RenderResult:
        surf = ctx.makeOffscreenSurface()
        canvas = surf.getCanvas()
        canvas.clear(skia.Color4f(0, 0, 0, 0))

        for inputNode in self.inputs:
            result = inputNode.getResult()
            if not result or not result.valid:
                continue

            paint = skia.Paint()
            paint.setAlphaf(result.opacity * self.trackOpacity)
            canvas.drawImage(result.image, 0, 0, skia.SamplingOptions(), paint)

        img = surf.makeImageSnapshot()
        return RenderResult(image=img, opacity=self.trackOpacity)
