// DrawSvg.cpp — SVG clip rendering for Fade's HeadlessCompositor.
// Pattern from Qteee-Vulkan: SvgAssest (SkSVGDOM) + SvgDrawNode (canvas ops).

#include "rendering/DrawSvg.hpp"

// Skia core
#include "include/core/SkColorFilter.h"
#include "include/core/SkPaint.h"
#include "include/core/SkStream.h"
#include "include/effects/SkColorMatrix.h"

// Skia SVG module (compiled into skia.lib)
#include "modules/svg/include/SkSVGDOM.h"

#include <mutex>
#include <string>
#include <unordered_map>

namespace fade::drawing {

// ── DOM cache ────────────────────────────────────────────────────────────────
// SVG files are parsed once and cached by absolute file path.
// Thread-safe via a shared mutex (compositor and export threads may both call).
static std::unordered_map<std::string, sk_sp<SkSVGDOM>> s_svgCache;
static std::mutex                                        s_svgMutex;

static sk_sp<SkSVGDOM> loadSvg(const std::string& path) {
    std::lock_guard<std::mutex> lk(s_svgMutex);
    auto it = s_svgCache.find(path);
    if (it != s_svgCache.end())
        return it->second;

    auto stream = SkStream::MakeFromFile(path.c_str());
    if (!stream) return nullptr;

    SkSVGDOM::Builder builder;
    // Note: setFontManager could be added here for SVGs with <text> nodes.
    auto dom = builder.make(*stream);
    s_svgCache[path] = dom;
    return dom;
}

void clearSvgCache() {
    std::lock_guard<std::mutex> lk(s_svgMutex);
    s_svgCache.clear();
}

// ── drawSvg ──────────────────────────────────────────────────────────────────
// Mirrors Qteee-Vulkan SvgDrawNode::execute():
//   1. Load / cache the SVG DOM
//   2. Determine render size (svgStyle.displayW/H or canvas size)
//   3. Apply clip transform (same code as drawClipOnCanvas: translate/rotate/scale)
//   4. saveLayer for opacity + blend mode  (exactly as SvgDrawNode)
//   5. Optional tint via SkColorFilter
//   6. Call dom->setContainerSize(w, h) then dom->render(canvas)
void drawSvg(SkCanvas* canvas, const ClipDesc& clip, int canvasW, int canvasH) {
    if (!canvas || clip.file.empty()) return;

    auto dom = loadSvg(clip.file);
    if (!dom) return;

    const auto& sv = clip.svg;

    // Render size — use svgStyle override or fall back to full canvas
    float w = sv.displayW > 0.f ? sv.displayW : static_cast<float>(canvasW);
    float h = sv.displayH > 0.f ? sv.displayH : static_cast<float>(canvasH);
    if (w <= 0.f || h <= 0.f) return;

    // ── Apply clip transform (same as drawClipOnCanvas) ───────────────────────
    const auto& t  = clip.transform;
    float cx = t.anchorX * w;
    float cy = t.anchorY * h;

    canvas->save();
    canvas->translate(t.x + cx, t.y + cy);
    canvas->rotate(t.rotation);
    canvas->scale(t.scaleX, t.scaleY);
    canvas->translate(-cx, -cy);

    // ── saveLayer: opacity + blend mode (Qteee-Vulkan SvgDrawNode pattern) ────
    SkPaint layerPaint;
    layerPaint.setAlphaf(clip.opacity);
    switch (clip.blendMode) {
        case 1:  layerPaint.setBlendMode(SkBlendMode::kScreen);    break;
        case 2:  layerPaint.setBlendMode(SkBlendMode::kMultiply);  break;
        case 3:  layerPaint.setBlendMode(SkBlendMode::kOverlay);   break;
        case 4:  layerPaint.setBlendMode(SkBlendMode::kDarken);    break;
        case 5:  layerPaint.setBlendMode(SkBlendMode::kLighten);   break;
        case 6:  layerPaint.setBlendMode(SkBlendMode::kColorDodge);break;
        case 7:  layerPaint.setBlendMode(SkBlendMode::kColorBurn); break;
        case 8:  layerPaint.setBlendMode(SkBlendMode::kHardLight); break;
        case 9:  layerPaint.setBlendMode(SkBlendMode::kSoftLight);  break;
        case 10: layerPaint.setBlendMode(SkBlendMode::kDifference); break;
        case 11: layerPaint.setBlendMode(SkBlendMode::kExclusion);  break;
        default: layerPaint.setBlendMode(SkBlendMode::kSrcOver);    break;
    }

    // Optional tint color filter
    if (sv.tintEnabled) {
        SkColorMatrix cm;
        cm.setScale(sv.tintR, sv.tintG, sv.tintB, sv.tintA);
        layerPaint.setColorFilter(SkColorFilters::Matrix(cm));
    }

    canvas->saveLayer(nullptr, &layerPaint);

    // ── Render SVG (Qteee-Vulkan SvgAssest::renderToCanvas pattern) ──────────
    dom->setContainerSize(SkSize::Make(w, h));
    dom->render(canvas);

    canvas->restore(); // pop saveLayer
    canvas->restore(); // pop transform
}

} // namespace fade::drawing
