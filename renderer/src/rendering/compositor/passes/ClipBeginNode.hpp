#pragma once
#include "core/SkBlendMode.h"
#include "core/SkPaint.h"
#include "core/rendering/clips/BaseClip.hpp"
#include "core/rendering/compositor/graph/RenderNode.hpp"
#include <memory>

struct ClipBeginNode : RenderNode {
  std::shared_ptr<baseClip> clip;
  bool hasMasks = false;

  const char *typeName() const override { return "ClipBegin"; }

  void prepare(RenderContext &ctx) override {}

  void execute(RenderContext &ctx) override {
    if (!ctx.canvas)
      return;

    if (!hasMasks)
      return;

    SkPaint layerPaint;
    layerPaint.setBlendMode(static_cast<SkBlendMode>(clip->getBlendMode()));
    ctx.canvas->saveLayer(nullptr, &layerPaint);
  }
};
