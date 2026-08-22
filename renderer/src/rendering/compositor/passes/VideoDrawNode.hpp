#pragma once
#include "core/SkBlendMode.h"
#include "core/SkImage.h"
#include "core/SkM44.h"
#include "core/SkPaint.h"
#include "core/SkRect.h"
#include "core/SkSamplingOptions.h"
#include "core/rendering/clips/VideoClip.hpp"
#include "core/rendering/compositor/CacheEntry.hpp"
#include "core/rendering/compositor/graph/RenderNode.hpp"
#include "core/rendering/data/BlendModeMap.hpp"


struct VideoDrawNode : RenderNode {
  VideoClip *clip = nullptr;

  const char *typeName() const override { return "VideoDraw"; }

  void prepare(RenderContext &ctx) override {
    if (clip)
      clip->evaluateAll(ctx.currentFrame);
  }

  void execute(RenderContext &ctx) override {
    if (!ctx.canvas || !clip)
      return;

    const std::string cacheKey = ctx.clipIdPrefix + clip->getId();
    auto it = ctx.gpuTextureCache->find(cacheKey);
    if (it == ctx.gpuTextureCache->end() || !it->second.skiaImage)
      return;

    const CacheEntry &ce = it->second;
    sk_sp<SkImage> frame = ce.skiaImage;

    const ClipPushConstants &pc = clip->getPushConstants();
    ctx.canvas->save();

    const glm::mat4 &m = ce.scaledModel;
    SkM44 skModel(m[0][0], m[1][0], m[2][0], m[3][0], m[0][1], m[1][1], m[2][1],
                  m[3][1], m[0][2], m[1][2], m[2][2], m[3][2], m[0][3], m[1][3],
                  m[2][3], m[3][3]);
    ctx.canvas->concat(skModel);

    SkRect dst = SkRect::MakeLTRB(-0.5f, -0.5f, 0.5f, 0.5f);
    SkPaint paint;
    paint.setAntiAlias(true);
    paint.setAlphaf(pc.opacity);
    paint.setBlendMode(BlendModeMap::fromIndex(pc.blendMode));

    SkSamplingOptions sampling(SkFilterMode::kLinear, SkMipmapMode::kLinear);
    ctx.canvas->drawImageRect(frame, dst, sampling, &paint);

    ctx.canvas->restore();
  }
};
