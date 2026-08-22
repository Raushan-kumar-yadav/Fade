#pragma once
#include "core/SkBlendMode.h"
#include "core/SkBlurTypes.h"
#include "core/SkCanvas.h"
#include "core/SkColor.h"
#include "core/SkMaskFilter.h"
#include "core/SkMatrix.h"
#include "core/SkPaint.h"
#include "core/SkPath.h"
#include "core/SkRect.h"
#include "core/rendering/clips/BaseClip.hpp"
#include "core/rendering/compositor/graph/RenderNode.hpp"
#include "core/rendering/clips/mask/MaskGroupComponent.hpp"
#include "core/rendering/clips/mask/clipMask.hpp"
#include <cstdlib>
#include <memory>

struct MaskNode : RenderNode {
  std::shared_ptr<baseClip> clip;

  const char *typeName() const override { return "Mask"; }

  void prepare(RenderContext &ctx) override {

    if (clip) {
      clip->evaluateAll(ctx.currentFrame);
    }
  }

  void execute(RenderContext &ctx) override {
    if (!clip || !ctx.canvas)
      return;

    const MaskGroupComponent *masks = clip->getMaskGroup();
    if (!masks)
      return;

    bool hasValid = false;
    for (const auto &mask : masks->getMasks())
      if (mask->vertexCount() >= 2) {
        hasValid = true;
        break;
      }
    if (!hasValid)
      return;

    SkPaint maskLayerPaint;
    maskLayerPaint.setBlendMode(SkBlendMode::kDstIn);
    ctx.canvas->saveLayer(nullptr, &maskLayerPaint);

    for (const auto &mask : masks->getMasks()) {
      if (mask->vertexCount() < 2)
        continue;
      SkPath path = mask->buildPath();
      if (path.isEmpty())
        continue;

      float scale = mask->size.get() / 100.f;
      if (std::abs(scale - 1.f) > 0.001f) {
        SkRect b = path.getBounds();
        SkMatrix t;
        t.setTranslate(-b.centerX(), -b.centerY());
        t.postScale(scale, scale);
        t.postTranslate(b.centerX(), b.centerY());
        path = path.makeTransform(t);
      }

      SkPaint paint;
      paint.setAntiAlias(true);
      paint.setColor(SK_ColorWHITE);
      paint.setAlphaf(mask->opacity.get());

      float f = mask->feather.get();
      if (f > 0.f)
        paint.setMaskFilter(
            SkMaskFilter::MakeBlur(kNormal_SkBlurStyle, f / 3.f));

      if (mask->m_mode == MaskMode::Subtract)
        paint.setBlendMode(SkBlendMode::kClear);
      else
        paint.setBlendMode(SkBlendMode::kSrcOver);

      ctx.canvas->drawPath(path, paint);
    }

    ctx.canvas->restore();
  }
};
