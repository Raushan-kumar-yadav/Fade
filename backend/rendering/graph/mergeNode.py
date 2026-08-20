from __future__ import annotations
import skia
from backend.rendering.graph.baseNode import BaseNode, RenderResult
from backend.rendering.renderContext import RenderContext


class MergeNode(BaseNode):
  

    def __init__(self, trackId: str, trackOpacity: float = 1.0) -> None:
        super().__init__(f"merge_{trackId}")
        self.trackOpacity = trackOpacity

    def execute(self, ctx: RenderContext) -> RenderResult:
        if self.trackOpacity <= 0.0:
            return RenderResult()

        canvas = ctx.canvas
        if self.trackOpacity < 1.0:
            canvas.saveLayerAlphaf(self.trackOpacity)
        else:
            canvas.save()

        for inputNode in self.inputs:
            inputNode.execute(ctx)

        canvas.restore()
        return RenderResult()
