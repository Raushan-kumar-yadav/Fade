from __future__ import annotations
import skia
from backend.rendering.graph.baseNode import BaseNode, RenderResult
from backend.rendering.renderContext import RenderContext
from backend.timeline.clips.baseClip import BaseClip


class ClipNode(BaseNode):

    def __init__(self, clip: BaseClip) -> None:
        super().__init__(f"clip_{clip.clipId}")
        self.clip = clip

    def execute(self, ctx: RenderContext) -> RenderResult:
        if not self.clip.overlaps(ctx.frame):
            return RenderResult()

        # Evaluate all animated properties for this frame
        self.clip.evaluateAll(ctx.frame)

        surf = ctx.makeOffscreenSurface()
        canvas = surf.getCanvas()
        canvas.clear(skia.Color4f(0, 0, 0, 0))

        try:
            self.clip.render(canvas, ctx.frame)
        except Exception as e:
            print(f"[ClipNode] render error for {self.clip.clipId}: {e}")
            return RenderResult()

        img = surf.makeImageSnapshot()
        opacity = float(self.clip.transform.opacity.get())
        return RenderResult(image=img, opacity=opacity)
