from __future__ import annotations
import skia
from backend.rendering.graph.baseNode import BaseNode, RenderResult
from backend.rendering.renderContext import RenderContext


class EffectNode(BaseNode):
    """
    Applies one BaseEffect to the output of a ClipNode.
    Sits between ClipNode (upstream) and MergeNode (downstream).

    Reads the single upstream RenderResult, applies the effect
    on an offscreen surface, and passes the result forward.
    """

    def __init__(self, effect, clipId: str) -> None:
        super().__init__(f"effect_{effect.__class__.__name__}_{clipId}")
        self.effect = effect

    def execute(self, ctx: RenderContext) -> RenderResult:
        if not self.inputs:
            return RenderResult()

        upstream = self.inputs[0].getResult()
        if not upstream or not upstream.valid:
            return RenderResult()

        surf   = ctx.makeOffscreenSurface()
        canvas = surf.getCanvas()
        canvas.clear(skia.Color4f(0, 0, 0, 0))

        try:
            self.effect.apply(canvas, upstream.image, ctx.frame)
        except Exception as e:
            print(f"[EffectNode] error applying {self.effect}: {e}")
            # Fall back to passing the upstream image unchanged
            paint = skia.Paint()
            canvas.drawImage(upstream.image, 0, 0, paint)

        img = surf.makeImageSnapshot()
        return RenderResult(image=img, opacity=upstream.opacity)
