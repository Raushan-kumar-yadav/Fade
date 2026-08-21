 
from __future__ import annotations
import skia
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.timeline.clips.penClip import PenClip


def build_skpath(points: list, is_closed: bool) -> skia.Path:
     
    n = len(points)
    if n == 0:
        return skia.Path()

    path = skia.Path()
    path.moveTo(points[0].x, points[0].y)

    for i in range(1, n):
        prev = points[i - 1]
        curr = points[i]

        prev_out_x = prev.x + prev.outX
        prev_out_y = prev.y + prev.outY
        curr_in_x  = curr.x + curr.inX
        curr_in_y  = curr.y + curr.inY

        has_tangent = (
            (prev.outX ** 2 + prev.outY ** 2) > 1e-6 or
            (curr.inX  ** 2 + curr.inY  ** 2) > 1e-6
        )
        if has_tangent:
            path.cubicTo(prev_out_x, prev_out_y, curr_in_x, curr_in_y, curr.x, curr.y)
        else:
            path.lineTo(curr.x, curr.y)

    if is_closed and n >= 2:
        # Close 
        last  = points[-1]
        first = points[0]
        last_out_x = last.x  + last.outX
        last_out_y = last.y  + last.outY
        first_in_x = first.x + first.inX
        first_in_y = first.y + first.inY
        has_tangent = (
            (last.outX  ** 2 + last.outY  ** 2) > 1e-6 or
            (first.inX  ** 2 + first.inY  ** 2) > 1e-6
        )
        if has_tangent:
            path.cubicTo(last_out_x, last_out_y, first_in_x, first_in_y,
                         first.x, first.y)
        path.close()

    return path


def draw_pen(canvas: skia.Canvas, clip: "PenClip", frame: int) -> None:
    from backend.rendering.nodes.shapeNode import _draw_shadow, _draw_shape_path

    # Evaluate all animatable params so _anim_params  
    clip.evaluateAll(frame)

    if len(clip.points) < 2:
        return

    path = build_skpath(clip.points, clip.isClosed)
    s    = clip.style

    canvas.save()
    clip.transform.applyToCanvas(canvas)

    if s.shadowEnabled:
        _draw_shadow(canvas, path, s)

    _draw_shape_path(canvas, path, s)

    canvas.restore()
