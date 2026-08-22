#pragma once
#include "core/rendering/compositor/graph/RenderNode.hpp"
#include "core/media/MediaAsset.hpp"

struct TextureUploadNode : RenderNode {
  std::string clipId;
  int64_t localFrame = 0;
  std::shared_ptr<MediaAsset> asset;
  std::shared_ptr<DecodedFrame> decodedFrame;
  std::unordered_map<std::string, CacheEntry> *gpuTextureCache = nullptr;

  // The actual upload work
  std::function<void()> uploadFn;
  const char *typeName() const override { return "TextureUpload"; }

  void execute(RenderContext &ctx) override {
    if (uploadFn)
      uploadFn();
  }
};
