#include "rendering/DrawText.hpp"

// Skia includes — same set as Qteee-Vulkan/Compositor.cpp
#include "core/SkBlurTypes.h"
#include "core/SkFont.h"
#include "core/SkFontMgr.h"
#include "core/SkMaskFilter.h"
#include "core/SkTypeface.h"
#include "include/ports/SkTypeface_win.h"   // SkFontMgr_New_DirectWrite

#include <algorithm>
#include <cctype>
#include <sstream>
#include <string>
#include <vector>

namespace fade::drawing {

// ─── Font manager (lazy init — identical to Qteee-Vulkan getSkiaTypeface) ────
static sk_sp<SkFontMgr> s_fontMgr;

static sk_sp<SkFontMgr> getFontMgr() {
    if (!s_fontMgr) {
#ifdef _WIN32
        s_fontMgr = SkFontMgr_New_DirectWrite();
#endif
        if (!s_fontMgr)
            s_fontMgr = SkFontMgr::RefEmpty();
    }
    return s_fontMgr;
}

static sk_sp<SkTypeface> resolveTypeface(const std::string& family, bool bold, bool italic) {
    sk_sp<SkFontMgr> mgr = getFontMgr();
    if (!mgr) return nullptr;

    const std::string lookupName = family.empty() ? "Arial" : family;

    SkFontStyle style(
        bold   ? SkFontStyle::kBold_Weight   : SkFontStyle::kNormal_Weight,
        SkFontStyle::kNormal_Width,
        italic ? SkFontStyle::kItalic_Slant  : SkFontStyle::kUpright_Slant);

    // 1. Try exact family match (Qteee-Vulkan: matchFamilyStyle)
    sk_sp<SkTypeface> tf = mgr->matchFamilyStyle(lookupName.c_str(), style);

    // 2. Fallback: Arial
    if (!tf && lookupName != "Arial")
        tf = mgr->matchFamilyStyle("Arial", style);

    // 3. Fallback: system default family
    if (!tf)
        tf = mgr->matchFamilyStyle(nullptr, style);

    return tf;
}

// ─── Internal helpers ─────────────────────────────────────────────────────────

static std::vector<std::string> splitLines(const std::string& text) {
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
    for (auto& c : s)
        c = (char)std::toupper((unsigned char)c);
    return s;
}

// ─── Public API ──────────────────────────────────────────────────────────────

void drawText(SkCanvas* canvas, const ClipDesc& clip, int canvasW, int canvasH) {
    const ClipDesc::TextDesc& ts = clip.text;
    const float opacity           = clip.opacity;

    // ── Content prep ─────────────────────────────────────────────────────────
    const std::string displayText =
        ts.allCaps ? toAllCaps(ts.text) : ts.text;

    const std::vector<std::string> lines = splitLines(displayText);

    // ── Font (Qteee-Vulkan pattern: resolveTypeface → SkFont) ────────────────
    sk_sp<SkTypeface> tf = resolveTypeface(ts.fontFamily, ts.bold, ts.italic);
    SkFont font(tf, ts.fontSize);
    font.setEdging(SkFont::Edging::kAntiAlias);
    font.setSubpixel(true);

    // ── Measure ──────────────────────────────────────────────────────────────
    const float lineH  = ts.fontSize * ts.lineHeight;
    const float totalH = lineH * (float)lines.size();

    float maxLineW = 0.f;
    for (const auto& ln : lines) {
        float w = font.measureText(ln.c_str(), ln.size(), SkTextEncoding::kUTF8);
        maxLineW = std::max(maxLineW, w);
    }

    // ── Apply clip transform ──────────────────────────────────────────────────
    canvas->save();
    {
        const auto& t  = clip.transform;
        const float cx = t.anchorX * (float)canvasW;
        const float cy = t.anchorY * (float)canvasH;
        canvas->translate(t.x + cx, t.y + cy);
        canvas->rotate(t.rotation);
        canvas->scale(t.scaleX, t.scaleY);
        canvas->translate(-cx, -cy);
    }

    // Default text origin: centered on canvas
    const float originX = (float)canvasW * 0.5f;
    const float originY = (float)canvasH * 0.5f - totalH * 0.5f + ts.fontSize;

    // ── Background box ────────────────────────────────────────────────────────
    if (ts.bgEnabled) {
        const float bx = originX - maxLineW * 0.5f - ts.bgPaddingX;
        const float by = originY - ts.fontSize       - ts.bgPaddingY;
        const float bw = maxLineW + ts.bgPaddingX * 2.f;
        const float bh = totalH   + ts.bgPaddingY * 2.f;

        SkPaint bgPaint;
        bgPaint.setColor4f({ts.bgR, ts.bgG, ts.bgB, ts.bgA * opacity});
        bgPaint.setAntiAlias(true);

        if (ts.bgCornerRadius > 0.f)
            canvas->drawRoundRect(SkRect::MakeXYWH(bx, by, bw, bh),
                                  ts.bgCornerRadius, ts.bgCornerRadius, bgPaint);
        else
            canvas->drawRect(SkRect::MakeXYWH(bx, by, bw, bh), bgPaint);
    }

    // ── Per-line rendering (Qteee-Vulkan TextDrawNode pattern) ───────────────
    for (size_t i = 0; i < lines.size(); ++i) {
        const std::string& ln = lines[i];
        if (ln.empty()) continue;

        const float lineW = font.measureText(ln.c_str(), ln.size(),
                                             SkTextEncoding::kUTF8);
        float lx;
        if      (ts.alignment == "center") lx = originX - lineW    * 0.5f;
        else if (ts.alignment == "right" ) lx = originX - lineW;
        else                               lx = originX - maxLineW * 0.5f;

        const float ly = originY + (float)i * lineH;

        auto blob = SkTextBlob::MakeFromString(ln.c_str(), font);
        if (!blob) continue;

        // Shadow pass (Qteee-Vulkan: edgeSoftness + MakeBlur)
        if (ts.shadowEnabled) {
            SkPaint shadowPaint;
            shadowPaint.setColor4f(
                {ts.shadowR, ts.shadowG, ts.shadowB, ts.shadowA * opacity});
            shadowPaint.setAntiAlias(true);
            shadowPaint.setMaskFilter(
                SkMaskFilter::MakeBlur(kNormal_SkBlurStyle, ts.shadowBlur * 0.5f));
            canvas->drawTextBlob(blob.get(),
                                 lx + ts.shadowOffsetX,
                                 ly + ts.shadowOffsetY,
                                 shadowPaint);
        }

        // Stroke pass (Qteee-Vulkan: kStroke_Style before fill)
        if (ts.strokeWidth > 0.f) {
            SkPaint sp;
            sp.setStyle(SkPaint::kStroke_Style);
            sp.setStrokeWidth(ts.strokeWidth);
            sp.setColor4f(
                {ts.strokeR, ts.strokeG, ts.strokeB, ts.strokeA * opacity});
            sp.setAntiAlias(true);
            canvas->drawTextBlob(blob.get(), lx, ly, sp);
        }

        // Fill pass
        SkPaint fillPaint;
        fillPaint.setColor4f(
            {ts.fillR, ts.fillG, ts.fillB, ts.fillA * opacity});
        fillPaint.setAntiAlias(true);
        canvas->drawTextBlob(blob.get(), lx, ly, fillPaint);
    }

    canvas->restore();
}

} // namespace fade::drawing
