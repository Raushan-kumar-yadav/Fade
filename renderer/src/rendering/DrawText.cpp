// DrawText.cpp  —  mirrors Qteee-Vulkan TextDrawNode exactly
// Uses canvas->drawString (like TextDrawNode), SkM44 transform, SkColorSetARGB

#include "rendering/DrawText.hpp"

#include "core/SkBlurTypes.h"
#include "core/SkFont.h"
#include "core/SkFontMgr.h"
#include "core/SkM44.h"
#include "core/SkMaskFilter.h"
#include "core/SkTypeface.h"
#include "include/ports/SkTypeface_win.h" // SkFontMgr_New_DirectWrite

#include <algorithm>
#include <cctype>
#include <cmath>
#include <sstream>
#include <string>
#include <vector>

namespace fade::drawing {

// ─── Font manager
// ───────────────────────────────────────────────────────────── Meyers
// singleton: one permanent ref that is NEVER released. Avoids NVRefCnt
// teardown-order crash when the Node addon is unloaded.
static SkFontMgr *getRawFontMgr() {
  static SkFontMgr *s_mgr = []() -> SkFontMgr * {
#ifdef _WIN32
    sk_sp<SkFontMgr> mgr = SkFontMgr_New_DirectWrite();
    if (mgr) {
      mgr->ref(); // permanent ref — never released
      return mgr.get();
    }
#endif
    sk_sp<SkFontMgr> fallback = SkFontMgr::RefEmpty();
    if (fallback) {
      fallback->ref();
      return fallback.get();
    }
    return nullptr;
  }();
  return s_mgr;
}

// Wraps the raw ptr in an sk_sp for a safe
static sk_sp<SkFontMgr> getFontMgr() {
  SkFontMgr *raw = getRawFontMgr();
  if (!raw)
    return nullptr;
  return sk_sp<SkFontMgr>(SkRef(raw));
}

//   Typeface resolution
static sk_sp<SkTypeface> resolveTypeface(const std::string &family, bool bold,
                                         bool italic) {
  sk_sp<SkFontMgr> mgr = getFontMgr();
  if (!mgr)
    return nullptr;

  const std::string &name = family.empty() ? "Arial" : family;

  SkFontStyle style(
      bold ? SkFontStyle::kBold_Weight : SkFontStyle::kNormal_Weight,
      SkFontStyle::kNormal_Width,
      italic ? SkFontStyle::kItalic_Slant : SkFontStyle::kUpright_Slant);

  sk_sp<SkTypeface> tf = mgr->matchFamilyStyle(name.c_str(), style);
  if (!tf && name != "Arial")
    tf = mgr->matchFamilyStyle("Arial", style);
  if (!tf)
    tf = mgr->matchFamilyStyle(nullptr, style);
  return tf;
}

//   Helpers
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

static SkColor toSkColor(float r, float g, float b, float a) {
  auto clamp = [](float v) -> uint8_t {
    return static_cast<uint8_t>(std::max(0.f, std::min(1.f, v)) * 255.f + 0.5f);
  };
  return SkColorSetARGB(clamp(a), clamp(r), clamp(g), clamp(b));
}

//   Public API
void drawText(SkCanvas *canvas, const ClipDesc &clip, int canvasW,
              int canvasH) {
  const ClipDesc::TextDesc &ts = clip.text;
  const float opacity = clip.opacity;

  //   Content prep
  const std::string displayText = ts.allCaps ? toAllCaps(ts.text) : ts.text;
  const std::vector<std::string> lines = splitLines(displayText);

  //   Typeface
  sk_sp<SkTypeface> tf = resolveTypeface(ts.fontFamily, ts.bold, ts.italic);

  const auto &t = clip.transform;
  const float cx = t.anchorX * static_cast<float>(canvasW);
  const float cy = t.anchorY * static_cast<float>(canvasH);

  SkM44 model = SkM44::Translate(t.x + cx, t.y + cy, 0.f);
  model.preConcat(SkM44::Rotate({0, 0, 1}, t.rotation * (SK_ScalarPI / 180.f)));
  model.preConcat(SkM44::Scale(t.scaleX, t.scaleY, 1.f));
  model.preConcat(SkM44::Translate(-cx, -cy, 0.f));

  canvas->save();
  canvas->concat(model);

  //   Measure
  SkFont font(tf, ts.fontSize);
  font.setEdging(SkFont::Edging::kAntiAlias);
  font.setSubpixel(true);

  const float lineH = ts.fontSize * ts.lineHeight;
  const float totalH = lineH * static_cast<float>(lines.size());

  float maxLineW = 0.f;
  for (const auto &ln : lines) {
    float w = font.measureText(ln.c_str(), ln.size(), SkTextEncoding::kUTF8);
    maxLineW = std::max(maxLineW, w);
  }

  //   centered on canvas
  const float originX = static_cast<float>(canvasW) * 0.5f;
  const float originY =
      static_cast<float>(canvasH) * 0.5f - totalH * 0.5f + ts.fontSize;

  //   Background box
  if (ts.bgEnabled) {
    const float bx = originX - maxLineW * 0.5f - ts.bgPaddingX;
    const float by = originY - ts.fontSize - ts.bgPaddingY;
    const float bw = maxLineW + ts.bgPaddingX * 2.f;
    const float bh = totalH + ts.bgPaddingY * 2.f;

    SkPaint bgPaint;
    bgPaint.setColor(toSkColor(ts.bgR, ts.bgG, ts.bgB, ts.bgA * opacity));
    bgPaint.setAntiAlias(true);

    if (ts.bgCornerRadius > 0.f)
      canvas->drawRoundRect(SkRect::MakeXYWH(bx, by, bw, bh), ts.bgCornerRadius,
                            ts.bgCornerRadius, bgPaint);
    else
      canvas->drawRect(SkRect::MakeXYWH(bx, by, bw, bh), bgPaint);
  }

  //   Per-line rendering
  for (size_t i = 0; i < lines.size(); ++i) {
    const std::string &ln = lines[i];
    if (ln.empty())
      continue;

    const float lineW =
        font.measureText(ln.c_str(), ln.size(), SkTextEncoding::kUTF8);
    float lx;
    if (ts.alignment == "center")
      lx = originX - lineW * 0.5f;
    else if (ts.alignment == "right")
      lx = originX - lineW;
    else
      lx = originX - maxLineW * 0.5f;

    const float ly = originY + static_cast<float>(i) * lineH;

    // Shadow pass
    if (ts.shadowEnabled && ts.shadowBlur > 0.f) {
      SkPaint shadowPaint;
      shadowPaint.setColor(
          toSkColor(ts.shadowR, ts.shadowG, ts.shadowB, ts.shadowA * opacity));
      shadowPaint.setAntiAlias(true);
      shadowPaint.setMaskFilter(
          SkMaskFilter::MakeBlur(kNormal_SkBlurStyle, ts.shadowBlur * 0.5f));
      // drawString
      canvas->drawString(ln.c_str(), lx + ts.shadowOffsetX,
                         ly + ts.shadowOffsetY, font, shadowPaint);
    }

    // Stroke pass
    if (ts.strokeWidth > 0.f) {
      SkPaint sp;
      sp.setStyle(SkPaint::kStroke_Style);
      sp.setStrokeWidth(ts.strokeWidth);
      sp.setColor(
          toSkColor(ts.strokeR, ts.strokeG, ts.strokeB, ts.strokeA * opacity));
      sp.setAntiAlias(true);
      canvas->drawString(ln.c_str(), lx, ly, font, sp);
    }

    // Fill pass
    SkPaint fillPaint;
    fillPaint.setColor(
        toSkColor(ts.fillR, ts.fillG, ts.fillB, ts.fillA * opacity));
    fillPaint.setAntiAlias(true);
    canvas->drawString(ln.c_str(), lx, ly, font, fillPaint);
  }

  canvas->restore();
}

} // namespace fade::drawing
