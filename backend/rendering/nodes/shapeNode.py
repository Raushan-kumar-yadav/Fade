"""
shapeNode.py — Skia shape rendering.

Covers all Qteee-Vulkan ShapeType variants:
  Rect, Circle, Ellipse, Star, Polygon, Line, Arc
Plus drop shadow via saveLayer + blur.
"""
from __future__ import annotations
import math
import skia
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.timeline.clips.shapeClip import ShapeClip


def _rgba(color: list, alpha: float = 1.0) -> int:
    r, g, b = [int(c * 255) for c in color[:3]]
    a = int(color[3] * alpha * 255) if len(color) > 3 else int(alpha * 255)
    return skia.ColorSetARGB(a, r, g, b)


def _shadow_offset(angle_deg: float, distance: float):
    """Convert Qteee shadowAngle + shadowDistance to (dx, dy)."""
    rad = math.radians(angle_deg)
    return math.cos(rad) * distance, math.sin(rad) * distance


def _build_path(s) -> skia.Path:
    """Build SkPath from ShapeStyle — mirrors Qteee ShapeData.generatePath()."""
    t = s.shapeType

    if t == "rect":
        if s.cornerRadius > 0:
            path = skia.Path()
            path.addRoundRect(
                skia.Rect.MakeXYWH(-s.width / 2, -s.height / 2, s.width, s.height),
                s.cornerRadius, s.cornerRadius,
            )
        else:
            path = skia.Path()
            path.addRect(skia.Rect.MakeXYWH(-s.width / 2, -s.height / 2, s.width, s.height))
        return path

    if t == "circle":
        path = skia.Path()
        path.addCircle(0, 0, s.radiusX)
        return path

    if t == "ellipse":
        path = skia.Path()
        path.addOval(skia.Rect.MakeLTRB(-s.radiusX, -s.radiusY, s.radiusX, s.radiusY))
        return path

    if t == "star":
        return _star_path(s.outerRadius, s.innerRadius, s.numPoints)

    if t == "polygon":
        return _polygon_path(s.polygonRadius, s.numSides)

    if t == "line":
        path = skia.Path()
        path.moveTo(s.x1, s.y1)
        path.lineTo(s.x2, s.y2)
        return path

    if t == "arc":
        path = skia.Path()
        path.addArc(
            skia.Rect.MakeLTRB(-s.arcRadius, -s.arcRadius, s.arcRadius, s.arcRadius),
            s.arcStartAngle, s.arcSweepAngle,
        )
        return path

    # fallback: rect
    path = skia.Path()
    path.addRect(skia.Rect.MakeXYWH(-50, -50, 100, 100))
    return path


def _star_path(outer: float, inner: float, num_points: int) -> skia.Path:
    path = skia.Path()
    step = math.pi / num_points
    first = True
    for i in range(num_points * 2):
        r     = outer if i % 2 == 0 else inner
        angle = i * step - math.pi / 2
        x, y  = r * math.cos(angle), r * math.sin(angle)
        if first:
            path.moveTo(x, y)
            first = False
        else:
            path.lineTo(x, y)
    path.close()
    return path


def _polygon_path(radius: float, num_sides: int) -> skia.Path:
    path = skia.Path()
    for i in range(num_sides):
        angle = 2 * math.pi * i / num_sides - math.pi / 2
        x, y  = radius * math.cos(angle), radius * math.sin(angle)
        if i == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    path.close()
    return path


def _draw_shadow(canvas: skia.Canvas, path: skia.Path, s) -> None:
    dx, dy = _shadow_offset(s.shadowAngle, s.shadowDistance)
    blur = skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, max(0.1, s.shadowBlur * 0.5))
    shadow_paint = skia.Paint()
    shadow_paint.setAntiAlias(True)
    shadow_paint.setColor(_rgba(s.shadowColor))
    shadow_paint.setMaskFilter(blur)
    canvas.save()
    canvas.translate(dx, dy)
    canvas.drawPath(path, shadow_paint)
    canvas.restore()


def _draw_shape_path(canvas: skia.Canvas, path: skia.Path, s) -> None:
    """Draw fill + stroke with correct style (center/inside/outside)."""
    if s.fillOpacity > 0.0:
        fill_paint = skia.Paint()
        fill_paint.setAntiAlias(True)
        fill_paint.setStyle(skia.Paint.kFill_Style)
        fill_paint.setColor(_rgba(s.fillColor, s.fillOpacity))
        canvas.drawPath(path, fill_paint)

    if s.strokeWidth > 0:
        sw     = s.strokeWidth
        stroke = skia.Paint()
        stroke.setAntiAlias(True)
        stroke.setStyle(skia.Paint.kStroke_Style)
        stroke.setStrokeWidth(sw)
        stroke.setColor(_rgba(s.strokeColor))

        if s.strokeStyle == "inside":
            canvas.save()
            canvas.clipPath(path)
            stroke.setStrokeWidth(sw * 2)
            canvas.drawPath(path, stroke)
            canvas.restore()
        elif s.strokeStyle == "outside":
            # exclude inside — clip inverted
            clip = skia.Path(path)
            clip.toggleInverseFillType()
            canvas.save()
            canvas.clipPath(clip)
            stroke.setStrokeWidth(sw * 2)
            canvas.drawPath(path, stroke)
            canvas.restore()
        else:
            # center (default)
            canvas.drawPath(path, stroke)


def draw_shape(canvas: skia.Canvas, clip: "ShapeClip", frame: int) -> None:
    s    = clip.style
    path = _build_path(s)

    canvas.save()
    clip.transform.applyToCanvas(canvas)

    if s.shadowEnabled:
        _draw_shadow(canvas, path, s)

    _draw_shape_path(canvas, path, s)

    canvas.restore()
