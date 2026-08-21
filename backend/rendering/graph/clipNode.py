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

        self.clip.evaluateAll(ctx.frame)
        opacity = float(self.clip.transform.opacity.get())
        masks   = getattr(self.clip, "masks", [])
        print(f"[ClipNode] frame={ctx.frame} clip={self.clip.clipId[:8]} opacity={opacity:.3f} masks={len(masks)}")
        if opacity <= 0.0:
            return RenderResult()

        canvas = ctx.canvas
        if opacity < 1.0:
            canvas.saveLayerAlphaf(opacity)
        else:
            canvas.save()

        clip   = self.clip
        frame  = ctx.frame

        try:
            if masks:
                # Compositing with masks via maskNode
                from backend.rendering.nodes.maskNode import apply_masks
                apply_masks(canvas, clip, lambda: clip.render(canvas, frame))
            else:
                clip.render(canvas, frame)
        except Exception as e:
            print(f"[ClipNode] render error for {clip.clipId}: {e}")
            import traceback; traceback.print_exc()
        finally:
            canvas.restore()

        return RenderResult()
