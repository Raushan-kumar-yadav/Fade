"""
textNode.py — Skia text rendering.

Replaces Qteee-Vulkan's font-atlas SDF approach with skia-python's
native text rendering (which handles anti-aliasing and sub-pixel rendering).
"""
from __future__ import annotations
import math
import skia
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.timeline.clips.textClip import TextClip


def _rgba(color: list, alpha_override: float = 1.0) -> int:
    """Convert [r,g,b,a] (0-1) list to Skia ARGB int."""
    r, g, b = [int(c * 255) for c in color[:3]]
    a = int(color[3] * alpha_override * 255) if len(color) > 3 else int(alpha_override * 255)
    return skia.ColorSetARGB(a, r, g, b)


def _make_typeface(family: str, bold: bool, italic: bool) -> skia.Typeface:
    style = skia.FontStyle(
        weight = skia.FontStyle.kBold_Weight   if bold   else skia.FontStyle.kNormal_Weight,
        width  = skia.FontStyle.kNormal_Width,
        slant  = skia.FontStyle.kItalic_Slant if italic else skia.FontStyle.kUpright_Slant,
    )
    tf = skia.Typeface(family, style)
    return tf or skia.Typeface("Arial", skia.FontStyle())


def _layout_lines(text: str, style, font: skia.Font, max_width: float) -> list[str]:
    """Wrap text into lines respecting max_width. Returns list of line strings."""
    if style.allCaps:
        text = text.upper()

    if max_width <= 0:
        return text.split("\n")

    lines: list[str] = []
    for para in text.split("\n"):
        words = para.split(" ")
        current = ""
        for word in words:
            test = (current + " " + word).strip()
            w = font.measureText(test)
            if w <= max_width or not current:
                current = test
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines


def draw_text(canvas: skia.Canvas, clip: "TextClip", frame: int) -> None:
    """Full text rendering pipeline — matches Qteee-Vulkan TextClip evaluation."""
    s = clip.style

    typeface = _make_typeface(s.fontFamily, s.bold, s.italic)
    font     = skia.Font(typeface, s.fontSize)
    font.setSubpixel(True)
    font.setEdging(skia.Font.Edging.kAntiAlias)

    # Letter spacing
    if s.letterSpacing != 0.0:
        font.setScaleX(1.0)  # no direct API; approximate via paint
    letter_extra = s.letterSpacing

    lines = _layout_lines(s.text, s, font, s.maxWidth)
    line_height = s.fontSize * s.lineHeight

    canvas.save()
    clip.transform.applyToCanvas(canvas)

    # Measure total block height for vertical centering (future use)
    total_h = line_height * len(lines)
    start_y = 0.0

    for i, line in enumerate(lines):
        baseline_y = start_y + (i + 1) * line_height

        # Measure line width for alignment
        line_w = _measure_text_with_spacing(font, line, letter_extra)
        if s.alignment == "center":
            ox = -line_w / 2
        elif s.alignment == "right":
            ox = -line_w
        else:
            ox = 0.0

        # --- Shadow pass ---
        if s.shadowEnabled:
            _draw_line_shadow(canvas, font, line, ox, baseline_y, s, letter_extra)

        # --- Background box ---
        if s.bgEnabled:
            _draw_bg_box(canvas, font, line, ox, baseline_y, s, letter_extra, line_h=s.fontSize)

        # --- Stroke pass ---
        if s.strokeWidth > 0:
            _draw_line_text(canvas, font, line, ox, baseline_y, s.strokeColor,
                            stroke=True, stroke_width=s.strokeWidth, letter_extra=letter_extra)

        # --- Fill pass ---
        _draw_line_text(canvas, font, line, ox, baseline_y, s.color,
                        stroke=False, letter_extra=letter_extra)

    canvas.restore()


def _measure_text_with_spacing(font: skia.Font, text: str, extra: float) -> float:
    w = font.measureText(text)
    if extra != 0.0:
        w += extra * max(0, len(text) - 1)
    return w


def _draw_line_text(
    canvas: skia.Canvas,
    font: skia.Font,
    text: str,
    x: float, y: float,
    color: list,
    stroke: bool = False,
    stroke_width: float = 2.0,
    letter_extra: float = 0.0,
) -> None:
    paint = skia.Paint()
    paint.setAntiAlias(True)
    paint.setColor(_rgba(color))

    if stroke:
        paint.setStyle(skia.Paint.kStroke_Style)
        paint.setStrokeWidth(stroke_width)
    else:
        paint.setStyle(skia.Paint.kFill_Style)

    if letter_extra == 0.0:
        canvas.drawSimpleText(text, x, y, font, paint)
    else:
        cx = x
        for ch in text:
            canvas.drawSimpleText(ch, cx, y, font, paint)
            cx += font.measureText(ch) + letter_extra


def _draw_line_shadow(
    canvas: skia.Canvas,
    font: skia.Font,
    text: str,
    x: float, y: float,
    s,
    letter_extra: float,
) -> None:
    blur_paint = skia.Paint()
    blur_paint.setAntiAlias(True)
    blur_paint.setColor(_rgba(s.shadowColor))
    blur_paint.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, s.shadowBlur * 0.5))

    if letter_extra == 0.0:
        canvas.drawSimpleText(
            text,
            x + s.shadowOffsetX,
            y + s.shadowOffsetY,
            font, blur_paint,
        )
    else:
        cx = x + s.shadowOffsetX
        for ch in text:
            canvas.drawSimpleText(ch, cx, y + s.shadowOffsetY, font, blur_paint)
            cx += font.measureText(ch) + letter_extra


def _draw_bg_box(
    canvas: skia.Canvas,
    font: skia.Font,
    text: str,
    x: float, y: float,
    s,
    letter_extra: float,
    line_h: float,
) -> None:
    line_w = _measure_text_with_spacing(font, text, letter_extra)
    rect = skia.RRect.MakeRectXY(
        skia.Rect.MakeLTRB(
            x - s.bgPaddingX,
            y - line_h - s.bgPaddingY,
            x + line_w + s.bgPaddingX,
            y + s.bgPaddingY,
        ),
        s.bgCornerRadius,
        s.bgCornerRadius,
    )
    bg_paint = skia.Paint()
    bg_paint.setAntiAlias(True)
    bg_paint.setColor(_rgba(s.bgColor))
    canvas.drawRRect(rect, bg_paint)
