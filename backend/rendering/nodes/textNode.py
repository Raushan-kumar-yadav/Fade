 
from __future__ import annotations
import math
import skia
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.timeline.clips.textClip import TextClip


def _rgba(color: list, alpha_override: float = 1.0) -> int:
     
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


# Text Animator helpers  

def _ease(t: float, mode: str) -> float:
    """Apply the named easing function to a normalised t ∈ [0, 1]."""
    t = max(0.0, min(1.0, t))
    if mode == "linear":
        return t
    if mode == "ease_in":
        return t * t
    if mode == "ease_out":
        return t * (2.0 - t)
    if mode == "ease_both":                          # smooth-step
        return t * t * (3.0 - 2.0 * t)
    if mode == "ease_in_cubic":
        return t * t * t
    if mode == "ease_out_cubic":
        t = 1.0 - t
        return 1.0 - t * t * t
    if mode == "elastic":
        if t == 0 or t == 1:
            return t
        p, a = 0.3, 1.0
        s = p / 4
        return a * math.pow(2, -10 * t) * math.sin((t - s) * (2 * math.pi) / p) + 1
    # fallback → ease_both
    return t * t * (3.0 - 2.0 * t)


def _char_alpha(
    char_idx: int,
    total_chars: int,
    clip_t: float,           
    anim: dict,
) -> float:
    """
    Return the opacity [0, 1] for a single character given the animator config.

    The animator sweeps a window across the characters over the range
    [startOffset, endOffset] of the clip duration (0-1 fractions).
    Each character's personal time within that sweep is eased independently.
    """
    if total_chars == 0:
        return 1.0

    start_off: float = anim.get("startOffset", 0.0)
    end_off: float = anim.get("endOffset",   1.0)
    easing: str   = anim.get("easing", "ease_both")
    from_val: float = anim.get("from", 0.0)
    to_val: float = anim.get("to",   1.0)

    sweep = end_off - start_off
    if sweep <= 0:
        return to_val

    # Normalised time within the  
    local_t = (clip_t - start_off) / sweep
    local_t = max(0.0, min(1.0, local_t))

    # Each character gets  
    char_norm = char_idx / max(total_chars - 1, 1)

    # Character  
    char_t = local_t - char_norm   
    char_local = char_t * total_chars
    char_local = max(0.0, min(1.0, char_local))

    alpha_factor = _ease(char_local, easing)
    return from_val + (to_val - from_val) * alpha_factor


#   Main draw function  

def draw_text(canvas: skia.Canvas, clip: "TextClip", frame: int) -> None:
     
    # Evaluate all animatable properties for this frame
    clip.evaluateAll(frame)

    s = clip.style

    #   Transform opacity  
    transform_opacity: float = max(0.0, min(1.0, float(clip.transform.opacity.get())))

    # Early-out if completely invisible
    if transform_opacity < 1.0 / 255:
        return

    typeface = _make_typeface(s.fontFamily, s.bold, s.italic)
    font = skia.Font(typeface, s.fontSize)
    font.setSubpixel(True)
    font.setEdging(skia.Font.Edging.kAntiAlias)

    # Letter spacing
    if s.letterSpacing != 0.0:
        font.setScaleX(1.0)   
    letter_extra = s.letterSpacing

    lines = _layout_lines(s.text, s, font, s.maxWidth)
    line_height = s.fontSize * s.lineHeight

    #   Text Animator  
    anim = s.animator
    use_anim  = anim.get("enabled", False)
    anim_prop = anim.get("property", "opacity")

    # Flatten all  
    all_chars: list[str] = []
    if use_anim and anim.get("mode", "characters") == "characters":
        for ln in lines:
            all_chars.extend(ln)
    total_chars = len(all_chars)

    # Clip-local time  
    clip_duration = max(clip.duration, 1)
    local_frame   = max(0, min(clip_duration - 1, frame - clip.startFrame))
    clip_t = local_frame / clip_duration

    canvas.save()
    clip.transform.applyToCanvas(canvas)

    char_counter = 0
    for i, line in enumerate(lines):
        baseline_y = (i + 1) * line_height

        # Measure line width for alignment
        line_w = _measure_text_with_spacing(font, line, letter_extra)
        if s.alignment == "center":
            ox = -line_w / 2
        elif s.alignment == "right":
            ox = -line_w
        else:
            ox = 0.0

        if not use_anim or anim_prop != "opacity" or total_chars == 0:
            # Standard  
            effective_alpha = transform_opacity

            # Shadow
            if s.shadowEnabled:
                _draw_line_shadow(canvas, font, line, ox, baseline_y, s,
                                  letter_extra, alpha=effective_alpha)
            # Background box
            if s.bgEnabled:
                _draw_bg_box(canvas, font, line, ox, baseline_y, s,
                             letter_extra, line_h=s.fontSize, alpha=effective_alpha)
            # Stroke
            if s.strokeWidth > 0:
                _draw_line_text(canvas, font, line, ox, baseline_y, s.strokeColor,
                                stroke=True, stroke_width=s.strokeWidth,
                                letter_extra=letter_extra, alpha=effective_alpha)
            # Fill
            _draw_line_text(canvas, font, line, ox, baseline_y, s.color,
                            stroke=False, letter_extra=letter_extra, alpha=effective_alpha)
        else:
            #   Per-character animated rendering  
            cx = ox
            for ch in line:
                char_alpha = _char_alpha(char_counter, total_chars, clip_t, anim)
                effective_alpha = transform_opacity * max(0.0, min(1.0, char_alpha))
                char_counter += 1

                ch_w = font.measureText(ch) + (letter_extra if ch != line[-1] else 0)

                if s.shadowEnabled:
                    _draw_line_shadow(canvas, font, ch, cx, baseline_y, s,
                                      0.0, alpha=effective_alpha)
                if s.bgEnabled:
                    _draw_bg_box(canvas, font, ch, cx, baseline_y, s,
                                 0.0, line_h=s.fontSize, alpha=effective_alpha)
                if s.strokeWidth > 0:
                    _draw_line_text(canvas, font, ch, cx, baseline_y, s.strokeColor,
                                    stroke=True, stroke_width=s.strokeWidth,
                                    letter_extra=0.0, alpha=effective_alpha)
                _draw_line_text(canvas, font, ch, cx, baseline_y, s.color,
                                stroke=False, letter_extra=0.0, alpha=effective_alpha)

                cx += ch_w

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
    alpha: float = 1.0,
) -> None:
    paint = skia.Paint()
    paint.setAntiAlias(True)
    paint.setColor(_rgba(color, alpha))

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
    alpha: float = 1.0,
) -> None:
    blur_paint = skia.Paint()
    blur_paint.setAntiAlias(True)
    blur_paint.setColor(_rgba(s.shadowColor, alpha))
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
    alpha: float = 1.0,
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
    bg_paint.setColor(_rgba(s.bgColor, alpha))
    canvas.drawRRect(rect, bg_paint)
