"""
maskNode.py — Skia mask compositing.

Mirrors Qteee-Vulkan's MaskNode and clipMask.buildPath():
  - For each MaskLayer on a clip, builds SkPath (rect/ellipse/bezier)
  - Composites Add/Subtract masks using saveLayer + kDstIn/kDstOut blend mode
  - Applies feather via SkMaskFilter.MakeBlur
"""
from __future__ import annotations
import math
import skia
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.timeline.clips.textClip import MaskLayer


def _build_mask_path(mask: "MaskLayer") -> skia.Path:
    """Build SkPath from a MaskLayer — mirrors Qteee clipMask.buildPath()."""
    pts = mask.points
    shape = mask.shape

    if shape == "rect":
        if len(pts) >= 2:
            x1 = min(p["x"] for p in pts)
            y1 = min(p["y"] for p in pts)
            x2 = max(p["x"] for p in pts)
            y2 = max(p["y"] for p in pts)
        else:
            x1, y1, x2, y2 = -50, -50, 50, 50
        path = skia.Path()
        path.addRect(skia.Rect.MakeLTRB(x1, y1, x2, y2))
        return path

    if shape == "ellipse":
        if len(pts) >= 2:
            x1 = min(p["x"] for p in pts)
            y1 = min(p["y"] for p in pts)
            x2 = max(p["x"] for p in pts)
            y2 = max(p["y"] for p in pts)
        else:
            x1, y1, x2, y2 = -50, -50, 50, 50
        path = skia.Path()
        path.addOval(skia.Rect.MakeLTRB(x1, y1, x2, y2))
        return path

    # bezier (same logic as clipMask.buildPath)
    n = len(pts)
    if n < 2:
        return skia.Path()

    path = skia.Path()
    path.moveTo(pts[0]["x"], pts[0]["y"])

    for i in range(1, n):
        prev = pts[i - 1]
        curr = pts[i]
        px_out = prev["x"] + prev.get("outX", 0)
        py_out = prev["y"] + prev.get("outY", 0)
        cx_in  = curr["x"] + curr.get("inX", 0)
        cy_in  = curr["y"] + curr.get("inY", 0)
        has_t = (
            (prev.get("outX", 0) ** 2 + prev.get("outY", 0) ** 2) > 1e-6 or
            (curr.get("inX",  0) ** 2 + curr.get("inY",  0) ** 2) > 1e-6
        )
        if has_t:
            path.cubicTo(px_out, py_out, cx_in, cy_in, curr["x"], curr["y"])
        else:
            path.lineTo(curr["x"], curr["y"])

    # close
    last  = pts[-1]
    first = pts[0]
    lo_x = last["x"] + last.get("outX", 0)
    lo_y = last["y"] + last.get("outY", 0)
    fi_x = first["x"] + first.get("inX", 0)
    fi_y = first["y"] + first.get("inY", 0)
    has_t = (
        (last.get("outX", 0) ** 2 + last.get("outY", 0) ** 2) > 1e-6 or
        (first.get("inX", 0) ** 2 + first.get("inY", 0) ** 2) > 1e-6
    )
    if has_t:
        path.cubicTo(lo_x, lo_y, fi_x, fi_y, first["x"], first["y"])
    path.close()

    if mask.inverted:
        path.toggleInverseFillType()

    return path


def apply_masks(canvas: skia.Canvas, clip, draw_content_fn) -> None:
    """
    Apply all clip masks using Skia layer compositing.

    Algorithm:
      1. saveLayer (transparent backing)
      2. draw clip content
      3. For each mask: saveLayer → draw mask path → restore with blend mode
      4. restore backing layer

    Mirrors Qteee MaskNode compositor pass.
    """
    masks = getattr(clip, "masks", [])
    if not masks:
        draw_content_fn()
        return

    # Outer layer: captures clip content + mask compositing
    canvas.saveLayer(None, None)
    draw_content_fn()

    for mask in masks:
        path = _build_mask_path(mask)

        # Feather: blur the mask edge (Qteee: SkMaskFilter on feather)
        mask_paint = skia.Paint()
        mask_paint.setAntiAlias(True)
        alpha = int(mask.opacity * 255)
        mask_paint.setColor(skia.ColorSetARGB(alpha, 255, 255, 255))

        if mask.feather > 0.0:
            sigma = mask.feather * 0.5
            mask_paint.setMaskFilter(
                skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, sigma)
            )

        if mask.mode == "subtract":
            # Subtract: erase the masked region
            mask_paint.setBlendMode(skia.BlendMode.kDstOut)
        else:
            # Add: keep only the masked region (intersect)
            mask_paint.setBlendMode(skia.BlendMode.kDstIn)

        canvas.drawPath(path, mask_paint)

    canvas.restore()
