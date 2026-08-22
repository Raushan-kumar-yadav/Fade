#pragma once
#include "core/SkCanvas.h"
#include "core/rendering/compositor/graph/RenderNode.hpp"

struct ClipEndNode : RenderNode {
  bool needsRestore = false; // mirrors ClipBeginNode::hasMasks

  const char *typeName() const override { return "ClipEnd"; }

  void prepare(RenderContext &ctx) override {}

  void execute(RenderContext &ctx) override {
    if (!ctx.canvas || !needsRestore)
      return;
    ctx.canvas->restore();
  }
};
