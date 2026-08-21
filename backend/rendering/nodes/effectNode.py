from __future__ import annotations
import skia


def applyEffects(canvas: skia.Canvas, clip, frame: int) -> None:
    for eff in getattr(clip, "effects", []):
        if getattr(eff, "enabled", True):
            try:
                eff.apply(canvas, frame)
            except Exception as e:
                print(f"[effectNode] {eff.name} error: {e}")
