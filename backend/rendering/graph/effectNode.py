from __future__ import annotations
import skia
from backend.rendering.graph.baseNode import BaseNode, RenderResult
from backend.rendering.renderContext import RenderContext


class EffectNode(BaseNode):

    # Effects that overlay on top of already-rendered content (not saveLayer-based)
    _OVERLAY_EFFECTS = {"VignetteEffect", "ChromaKeyEffect"}

    def __init__(self, effect, clipId: str) -> None:
        super().__init__(f"effect_{effect.__class__.__name__}_{clipId}")
        self.effect = effect

    def execute(self, ctx: RenderContext) -> RenderResult:
        if not self.inputs:
            return RenderResult()

        effect = self.effect
        if not getattr(effect, "enabled", True):
            # Effect disabled — just pass through
            ctx.canvas.save()
            try:
                self.inputs[0].execute(ctx)
            finally:
                ctx.canvas.restore()
            return RenderResult()

        effect_class = effect.__class__.__name__
        canvas = ctx.canvas

        if effect_class in self._OVERLAY_EFFECTS:
            # Overlay effects: render child first, then paint on top
            canvas.save()
            try:
                self.inputs[0].execute(ctx)
                try:
                    effect.apply(canvas, ctx.frame)
                except Exception as e:
                    print(f"[EffectNode] overlay effect {effect.name!r} error: {e}")
            finally:
                canvas.restore()
        else:
            # Filter effects (Blur, Sharpen, BrightnessContrast, HSL, ColorGrade):
            # Build a Paint with the effect's ImageFilter/ColorFilter, open a
            # saveLayer so the child renders INTO the filtered layer.
            paint = skia.Paint()
            try:
                # Temporarily redirect to a dummy canvas to extract the paint
                # that effect.apply() would install, by monkey-patching saveLayer.
                _captured: list[skia.Paint] = []

                class _CaptureSurface:
                    """Minimal canvas shim that captures the Paint from saveLayer."""
                    def saveLayer(self, bounds, p):  # noqa: N802
                        if p is not None:
                            _captured.append(p)
                    def restore(self): pass  # noqa: N802
                    def saveLayerAlpha(self, bounds, alpha): pass  # noqa: N802
                    def saveLayerAlphaf(self, alpha): pass  # noqa: N802
                    def save(self): pass  # noqa: N802
                    def drawPaint(self, p): pass  # noqa: N802
                    def getLocalClipBounds(self): return None  # noqa: N802

                cap = _CaptureSurface()
                effect.apply(cap, ctx.frame)  # type: ignore[arg-type]

                if _captured:
                    paint = _captured[0]
            except Exception as e:
                print(f"[EffectNode] paint capture for {effect.name!r} failed: {e}")

            canvas.saveLayer(None, paint)
            try:
                self.inputs[0].execute(ctx)
            finally:
                canvas.restore()

        return RenderResult()
