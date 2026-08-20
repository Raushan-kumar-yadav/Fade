from __future__ import annotations
import skia
from backend.rendering.graph.baseNode import BaseNode, RenderResult
from backend.rendering.renderContext import RenderContext


class OutputNode(BaseNode):
  

    def __init__(self) -> None:
        super().__init__("output")

    def execute(self, ctx: RenderContext) -> RenderResult:
        ctx.canvas.save()

        ctx.canvas.translate(ctx.panX, ctx.panY)
        ctx.canvas.scale(ctx.zoom, ctx.zoom)

        for mergeNode in self.inputs:
            mergeNode.execute(ctx)

        ctx.canvas.restore()
        return RenderResult()

