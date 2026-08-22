#include "rendering/DrawText.hpp"

#include <core/SkRRect.h>
#include <core/SkTypeface.h>
#include <effects/SkMaskFilter.h>

#include <algorithm>
#include <cctype>
#include <sstream>
#include <string>
#include <vector>

namespace fade::drawing {

//   helpers

static std::vector<std::string> splitLines(const std::string &text) {
  std::vector<std::string> lines;
  std::istringstream ss(text);
  std::string line;
  while (std::getline(ss, line))
    lines.push_back(line);
  if (lines.empty())
    lines.push_back("");
  return lines;
}

static std::string toAllCaps(std::string s) {
  for (auto &c : s)
    c = (char)std::toupper((unsigned char)c);
  return s;
}

// Build SkFont from the TextDesc style
static SkFont buildFont(const ClipDesc::TextDesc &ts) {
  SkFontStyle style(
      ts.bold ? SkFontStyle::kBold_Weight : SkFontStyle::kNormal_Weight,
      SkFontStyle::kNormal_Width,
      ts.italic ? SkFontStyle::kItalic_Slant : SkFontStyle::kUpright_Slant);

  sk_sp<SkFontMgr> mgr = SkFontMgr::RefDefault();
  sk_sp<SkTypeface> tf = mgr->matchFamilyStyle(ts.fontFamily.c_str(), style);
  if (!tf)
    tf = mgr->matchFamilyStyle("Arial", style);
  if (!tf)
    tf = SkTypeface::MakeDefault();

  SkFont font(tf, ts.fontSize);
  font.setSubpixel(true);
  font.setEdging(SkFont::Edging::kSubpixelAntiAlias);
  return font;
}

//   Public API

void drawText(SkCanvas *canvas, const ClipDesc &clip, int canvasW,
              int canvasH) {
  const ClipDesc::TextDesc &ts = clip.text;

  //   Content prep
  const std::string displayText = ts.allCaps ? toAllCaps(ts.text) : ts.text;

  const std::vector<std::string> lines = splitLines(displayText);

  //   Font
  const SkFont font = buildFont(ts);

  //   Measure
  const float lineH = ts.fontSize * ts.lineHeight;
  const float totalH = lineH * (float)lines.size();

  float maxLineW = 0.f;
  for (const auto &ln : lines) {
    float w = font.measureText(ln.c_str(), ln.size(), SkTextEncoding::kUTF8);
    maxLineW = std::max(maxLineW, w);
  }

  // Apply clip transform

  canvas->save();
  {
    const auto &t = clip.transform;
    const float cx = t.anchorX * (float)canvasW;
    const float cy = t.anchorY * (float)canvasH;
    canvas->translate(t.x + cx, t.y + cy);
    canvas->rotate(t.rotation);
    canvas->scale(t.scaleX, t.scaleY);
    canvas->translate(-cx, -cy);
  }

  // Default text origin
  const float originX = (float)canvasW * 0.5f;
  const float originY = (float)canvasH * 0.5f - totalH * 0.5f + ts.fontSize;

  //   Background box
  if (ts.bgEnabled) {
    const float bx = originX - maxLineW * 0.5f - ts.bgPaddingX;
    const float by = originY - ts.fontSize - ts.bgPaddingY;
    const float bw = maxLineW + ts.bgPaddingX * 2.f;
    const float bh = totalH + ts.bgPaddingY * 2.f;

    SkPaint bgPaint;
    bgPaint.setColor4f({ts.bgR, ts.bgG, ts.bgB, ts.bgA * clip.opacity});
    bgPaint.setAntiAlias(true);

    if (ts.bgCornerRadius > 0.f) {
      canvas->drawRoundRect(SkRect::MakeXYWH(bx, by, bw, bh), ts.bgCornerRadius,
                            ts.bgCornerRadius, bgPaint);
    } else {
      canvas->drawRect(SkRect::MakeXYWH(bx, by, bw, bh), bgPaint);
    }
  }

  //   Per-line rendering
  for (size_t i = 0; i < lines.size(); ++i) {
    const std::string &ln = lines[i];
    if (ln.empty())
      continue;

    // X position based on alignment
    const float lineW =
        font.measureText(ln.c_str(), ln.size(), SkTextEncoding::kUTF8);
    float lx;
    if (ts.alignment == "center")
      lx = originX - lineW * 0.5f;
    else if (ts.alignment == "right")
      lx = originX - lineW;
    else
      lx = originX - maxLineW * 0.5f; // left

    const float ly = originY + (float)i * lineH;

    auto blob = SkTextBlob::MakeFromString(ln.c_str(), font);
    if (!blob)
      continue;

    //   Shadow pass
    if (ts.shadowEnabled) {
      SkPaint shadowPaint;
      shadowPaint.setColor4f(
          {ts.shadowR, ts.shadowG, ts.shadowB, ts.shadowA * clip.opacity});
      shadowPaint.setAntiAlias(true);
      // SkMaskFilter blur provides a proper soft shadow
      shadowPaint.setMaskFilter(
          SkMaskFilter::MakeBlur(kNormal_SkBlurStyle, ts.shadowBlur * 0.5f));
      canvas->drawTextBlob(blob.get(), lx + ts.shadowOffsetX,
                           ly + ts.shadowOffsetY, shadowPaint);
    }

    //   Stroke pass
    if (ts.strokeWidth > 0.f) {
      SkPaint strokePaint;
      strokePaint.setColor4f(
          {ts.strokeR, ts.strokeG, ts.strokeB, ts.strokeA * clip.opacity});
      strokePaint.setStyle(SkPaint::kStroke_Style);
      strokePaint.setStrokeWidth(ts.strokeWidth);
      strokePaint.setStrokeJoin(SkPaint::kRound_Join);
      strokePaint.setAntiAlias(true);
      canvas->drawTextBlob(blob.get(), lx, ly, strokePaint);
    }

    //   Fill pass
    SkPaint fillPaint;
    fillPaint.setColor4f(
        {ts.fillR, ts.fillG, ts.fillB, ts.fillA * clip.opacity});
    fillPaint.setAntiAlias(true);
    canvas->drawTextBlob(blob.get(), lx, ly, fillPaint);
  }

  canvas->restore();
}

} // namespace fade::drawing
