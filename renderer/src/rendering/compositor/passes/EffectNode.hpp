#pragma once
#include "core/SkCanvas.h"
#include "core/SkColorSpace.h"
#include "core/SkImage.h"
#include "core/SkImageInfo.h"
#include "core/SkSurface.h"
#include "core/rendering/clips/BaseClip.hpp"
#include "core/rendering/compositor/graph/RenderNode.hpp"
#include "core/rendering/effects/EffectInstance.hpp"
#include "gpu/ganesh/GrDirectContext.h"
#include "gpu/ganesh/SkSurfaceGanesh.h"
#include <memory>

struct EffectNode : RenderNode {
  std::shared_ptr<baseClip> clip;
  int64_t currentFrame = 0;

  std::unique_ptr<RenderNode> drawNode;

  const char *typeName() const override { return "Effect"; }

  void prepare(RenderContext &ctx) override {
    if (drawNode)
      drawNode->prepare(ctx);
  }

  void execute(RenderContext &ctx) override {
    if (!ctx.canvas || !clip || !drawNode)
      return;

    // Check if any effects are actually
    bool hasActive = false;
    for (const auto &fx : clip->getEffects())
      if (fx->isEnabled()) {
        hasActive = true;
        break;
      }

    if (!hasActive || !ctx.grCtx) {

      drawNode->execute(ctx);
      return;
    }

    // Offscreen surface
    auto info = SkImageInfo::Make(ctx.canvas->imageInfo().width(),
                                  ctx.canvas->imageInfo().height(),
                                  kRGBA_8888_SkColorType, kPremul_SkAlphaType);
    auto offscreen =
        SkSurfaces::RenderTarget(ctx.grCtx, skgpu::Budgeted::kYes, info);
    if (!offscreen) {
      // GPU allocation failed
      drawNode->execute(ctx);
      return;
    }

    // Draw clip into offscreen
    RenderContext offCtx = ctx;
    offCtx.canvas = offscreen->getCanvas();
    offCtx.canvas->clear(SK_ColorTRANSPARENT);
    offCtx.canvas->setMatrix(ctx.canvas->getTotalMatrix());
    drawNode->execute(offCtx);

    // Snapshot offscreen → SkImage
    sk_sp<SkImage> result = offscreen->makeImageSnapshot();
    if (!result)
      return;

    sk_sp<SkImage> originalClipImage = result;

    // Compute clip origin
    glm::vec2 clipOrigin(0.f);
    glm::vec2 clipSize(0.f);

    const glm::vec2 intrinsic = clip->getIntrinsicSize();
    const bool hasIntrinsicSize = (intrinsic.x >= 1.f && intrinsic.y >= 1.f);

    if (hasIntrinsicSize) {
      const glm::mat4 wt = clip->getWorldTransform();
      std::array<SkPoint, 1> pts = {SkPoint::Make(wt[3][0], wt[3][1])};
      ctx.canvas->getTotalMatrix().mapPoints(SkSpan<SkPoint>(pts));
      clipOrigin.x = pts[0].x() - intrinsic.x * 0.5f;
      clipOrigin.y = pts[0].y() - intrinsic.y * 0.5f;

      const SkMatrix &cm = ctx.canvas->getTotalMatrix();
      clipSize.x = intrinsic.x * std::abs(cm.getScaleX());
      clipSize.y = intrinsic.y * std::abs(cm.getScaleY());
    }

    // Apply effect chain

    for (const auto &fx : clip->getEffects()) {
      if (!fx->isEnabled())
        continue;
      sk_sp<SkImage> processed =
          fx->apply(result, currentFrame, ctx.grCtx, clipOrigin,
                    originalClipImage, clipSize);
      if (processed)
        result = std::move(processed);
    }

    // Blit processed result to main canvas
    ctx.canvas->save();
    ctx.canvas->resetMatrix();
    ctx.canvas->drawImage(result, 0.f, 0.f);
    ctx.canvas->restore();
  }
};
