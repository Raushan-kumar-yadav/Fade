from __future__ import annotations
import skia
from backend.rendering.graph.baseNode import BaseNode, RenderResult
from backend.rendering.renderContext import RenderContext


class EffectNode(BaseNode):
    
    def __init__(self, effect, clipId: str) -> None:
        super().__init__(f"effect_{effect.__class__.__name__}_{clipId}")
        self.effect = effect

    def execute(self, ctx: RenderContext) -> RenderResult:
        if not self.inputs:
            return RenderResult()

        # Effect pipeline to be implemented via Skia ImageFilters attached to saveLayer
        # For now, pass-through to prevent memory leaks from offscreen surfaces
        
        ctx.canvas.save()
        try:
            self.inputs[0].execute(ctx)
        finally:
            ctx.canvas.restore()

        return RenderResult()

