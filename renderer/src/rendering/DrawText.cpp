

#include "rendering/DrawText.hpp"

#include "core/SkBlurTypes.h"
#include "core/SkFont.h"
#include "core/SkFontMgr.h"
#include "core/SkM44.h"
#include "core/SkMaskFilter.h"
#include "core/SkTypeface.h"
#include "include/ports/SkTypeface_win.h"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <sstream>
#include <string>
#include <vector>

namespace fade::drawing {

// Font manager
static SkFontMgr *getRawFontMgr() {
  static SkFontMgr *s_mgr = []() -> SkFontMgr * {
#ifdef _WIN32
    sk_sp<SkFontMgr> mgr = SkFontMgr_New_DirectWrite();
    if (mgr) {
      mgr->ref();
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

static sk_sp<SkFontMgr> getFontMgr() {
  SkFontMgr *raw = getRawFontMgr();
  return raw ? sk_sp<SkFontMgr>(SkRef(raw)) : nullptr;
}

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
  auto cl = [](float v) -> uint8_t {
    return static_cast<uint8_t>(std::max(0.f, std::min(1.f, v)) * 255.f + 0.5f);
  };
  return SkColorSetARGB(cl(a), cl(r), cl(g), cl(b));
}

// Easing functions
static float applyEasing(float t, int easing) {
  t = std::max(0.f, std::min(1.f, t));
  switch (easing) {
  case 1:
    return t * t; // ease_in
  case 2:
    return t * (2.f - t); // ease_out
  case 3:
    return t < 0.5f // ease_both
               ? 2.f * t * t
               : -1.f + (4.f - 2.f * t) * t;
  default:
    return t; // linear
  }
}

// Split UTF-8 string into individual characters
static std::vector<std::string> splitChars(const std::string &s) {
  std::vector<std::string> out;
  size_t i = 0;
  while (i < s.size()) {
    unsigned char c = (unsigned char)s[i];
    size_t len = 1;
    if (c >= 0xF0)
      len = 4;
    else if (c >= 0xE0)
      len = 3;
    else if (c >= 0xC0)
      len = 2;
    out.push_back(s.substr(i, std::min(len, s.size() - i)));
    i += len;
  }
  return out;
}

static std::vector<std::string> splitWords(const std::string &s) {
  std::vector<std::string> out;
  std::istringstream ss(s);
  std::string word;
  while (ss >> word)
    out.push_back(word + " ");
  return out;
}

// Draw a single string unit
static void drawUnit(SkCanvas *canvas, const std::string &unit, float x,
                     float y, float opacity, float offX, float offY,
                     float scale, const SkFont &font,
                     const ClipDesc::TextDesc &ts, float clipOpacity) {
  canvas->save();
  canvas->translate(x + offX, y + offY);
  if (scale != 1.f)
    canvas->scale(scale, scale);

  const float finalAlpha = clipOpacity * opacity;

  if (ts.shadowEnabled && ts.shadowBlur > 0.f) {
    SkPaint sp;
    sp.setColor(
        toSkColor(ts.shadowR, ts.shadowG, ts.shadowB, ts.shadowA * finalAlpha));
    sp.setAntiAlias(true);
    sp.setMaskFilter(
        SkMaskFilter::MakeBlur(kNormal_SkBlurStyle, ts.shadowBlur * 0.5f));
    canvas->drawString(unit.c_str(), ts.shadowOffsetX - offX,
                       ts.shadowOffsetY - offY +
                           (scale != 1.f ? (y * (1.f - scale)) : 0.f),
                       font, sp);
    // Simpler
    sp.setMaskFilter(
        SkMaskFilter::MakeBlur(kNormal_SkBlurStyle, ts.shadowBlur * 0.5f));
    canvas->drawString(unit.c_str(), ts.shadowOffsetX, ts.shadowOffsetY, font,
                       sp);
  }

  if (ts.strokeWidth > 0.f) {
    SkPaint stroke;
    stroke.setStyle(SkPaint::kStroke_Style);
    stroke.setStrokeWidth(ts.strokeWidth);
    stroke.setColor(
        toSkColor(ts.strokeR, ts.strokeG, ts.strokeB, ts.strokeA * finalAlpha));
    stroke.setAntiAlias(true);
    canvas->drawString(unit.c_str(), 0.f, 0.f, font, stroke);
  }

  SkPaint fill;
  fill.setColor(toSkColor(ts.fillR, ts.fillG, ts.fillB, ts.fillA * finalAlpha));
  fill.setAntiAlias(true);
  canvas->drawString(unit.c_str(), 0.f, 0.f, font, fill);

  canvas->restore();
}

void drawText(SkCanvas *canvas, const ClipDesc &clip, int canvasW,
              int canvasH) {
  const ClipDesc::TextDesc &ts = clip.text;
  const float opacity = clip.opacity;

  const std::string displayText = ts.allCaps ? toAllCaps(ts.text) : ts.text;
  const std::vector<std::string> lines = splitLines(displayText);

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

  const float originX = static_cast<float>(canvasW) * 0.5f;
  const float originY =
      static_cast<float>(canvasH) * 0.5f - totalH * 0.5f + ts.fontSize;

  // Background box
  if (ts.bgEnabled) {
    const float bx = originX - maxLineW * 0.5f - ts.bgPaddingX;
    const float by = originY - ts.fontSize - ts.bgPaddingY;
    const float bw = maxLineW + ts.bgPaddingX * 2.f;
    const float bh = totalH + ts.bgPaddingY * 2.f;
    SkPaint bgp;
    bgp.setColor(toSkColor(ts.bgR, ts.bgG, ts.bgB, ts.bgA * opacity));
    bgp.setAntiAlias(true);
    if (ts.bgCornerRadius > 0.f)
      canvas->drawRoundRect(SkRect::MakeXYWH(bx, by, bw, bh), ts.bgCornerRadius,
                            ts.bgCornerRadius, bgp);
    else
      canvas->drawRect(SkRect::MakeXYWH(bx, by, bw, bh), bgp);
  }

  // Build a flat lis
  const bool useAnimator = ts.animEnabled;

  // Collect all units
  struct UnitInfo {
    int lineIdx;
    std::string text;
    float preX;
    float preY;
  };
  std::vector<UnitInfo> allUnits;

  if (useAnimator && ts.animMode < 2) {
    // char or word mode
    for (int li = 0; li < (int)lines.size(); ++li) {
      const std::string &ln = lines[li];
      if (ln.empty())
        continue;
      float lineW =
          font.measureText(ln.c_str(), ln.size(), SkTextEncoding::kUTF8);
      float lx = (ts.alignment == "center")  ? originX - lineW * 0.5f
                 : (ts.alignment == "right") ? originX - lineW
                                             : originX - maxLineW * 0.5f;
      float ly = originY + static_cast<float>(li) * lineH;

      std::vector<std::string> units =
          (ts.animMode == 1) ? splitWords(ln) : splitChars(ln);
      float cx2 = lx;
      for (auto &u : units) {
        float uw = font.measureText(u.c_str(), u.size(), SkTextEncoding::kUTF8);
        allUnits.push_back({li, u, cx2, ly});
        cx2 += uw + ts.letterSpacing;
      }
    }
  }

  // Per-line rendering
  for (int li = 0; li < (int)lines.size(); ++li) {
    const std::string &ln = lines[li];
    if (ln.empty())
      continue;

    const float lineW =
        font.measureText(ln.c_str(), ln.size(), SkTextEncoding::kUTF8);
    float lx = (ts.alignment == "center")  ? originX - lineW * 0.5f
               : (ts.alignment == "right") ? originX - lineW
                                           : originX - maxLineW * 0.5f;
    const float ly = originY + static_cast<float>(li) * lineH;

    if (!useAnimator) {
      // Fast path
      if (ts.shadowEnabled && ts.shadowBlur > 0.f) {
        SkPaint sp;
        sp.setColor(toSkColor(ts.shadowR, ts.shadowG, ts.shadowB,
                              ts.shadowA * opacity));
        sp.setAntiAlias(true);
        sp.setMaskFilter(
            SkMaskFilter::MakeBlur(kNormal_SkBlurStyle, ts.shadowBlur * 0.5f));
        canvas->drawString(ln.c_str(), lx + ts.shadowOffsetX,
                           ly + ts.shadowOffsetY, font, sp);
      }
      if (ts.strokeWidth > 0.f) {
        SkPaint sp;
        sp.setStyle(SkPaint::kStroke_Style);
        sp.setStrokeWidth(ts.strokeWidth);
        sp.setColor(toSkColor(ts.strokeR, ts.strokeG, ts.strokeB,
                              ts.strokeA * opacity));
        sp.setAntiAlias(true);
        canvas->drawString(ln.c_str(), lx, ly, font, sp);
      }
      SkPaint fp;
      fp.setColor(toSkColor(ts.fillR, ts.fillG, ts.fillB, ts.fillA * opacity));
      fp.setAntiAlias(true);
      canvas->drawString(ln.c_str(), lx, ly, font, fp);

    } else if (ts.animMode == 2) {
      // Line mode
      int total = (int)lines.size();
      float t0 = total > 1 ? (float)li / (float)(total - 1) : 0.f;
      // Map into
      float span = ts.animEndOff - ts.animStartOff;
      float localT = (span > 0.f) ? (t0 - ts.animStartOff) / span : 1.f;
      float easedT = applyEasing(localT, ts.animEasing);
      float val = ts.animFrom + (ts.animTo - ts.animFrom) * easedT;

      float aOpacity = 1.f, aOffY = 0.f, aOffX = 0.f, aScale = 1.f;
      switch (ts.animProperty) {
      case 0:
        aOpacity = std::max(0.f, std::min(1.f, val));
        break;
      case 1:
        aOffY = val;
        break;
      case 2:
        aOffX = val;
        break;
      case 3:
        aScale = val;
        break;
      }
      drawUnit(canvas, ln, lx, ly, aOpacity, aOffX, aOffY, aScale, font, ts,
               opacity);

    } else {
      // Char/word mode
      const int total = (int)allUnits.size();
      float cx2 = lx;
      std::vector<std::string> lineUnits =
          (ts.animMode == 1) ? splitWords(ln) : splitChars(ln);
      // Find global start index for this line
      int unitBase = 0;
      for (auto &u : allUnits) {
        if (u.lineIdx == li)
          break;
        ++unitBase;
      }

      for (int ui = 0; ui < (int)lineUnits.size(); ++ui) {
        const std::string &unit = lineUnits[ui];
        float uw =
            font.measureText(unit.c_str(), unit.size(), SkTextEncoding::kUTF8);

        float t0 = (total > 1) ? float(unitBase + ui) / float(total - 1) : 0.f;
        float span = ts.animEndOff - ts.animStartOff;
        float localT = (span > 0.f) ? (t0 - ts.animStartOff) / span : 1.f;
        float easedT = applyEasing(localT, ts.animEasing);
        float val = ts.animFrom + (ts.animTo - ts.animFrom) * easedT;

        float aOpacity = 1.f, aOffY = 0.f, aOffX = 0.f, aScale = 1.f;
        switch (ts.animProperty) {
        case 0:
          aOpacity = std::max(0.f, std::min(1.f, val));
          break;
        case 1:
          aOffY = val;
          break;
        case 2:
          aOffX = val;
          break;
        case 3:
          aScale = val;
          break;
        }

        drawUnit(canvas, unit, cx2, ly, aOpacity, aOffX, aOffY, aScale, font,
                 ts, opacity);
        cx2 += uw + ts.letterSpacing;
      }
    }
  }

  canvas->restore();
}

} // namespace fade::drawing
