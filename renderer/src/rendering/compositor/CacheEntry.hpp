#pragma once

#include <memory>
#include <glm/glm.hpp>

#include "core/gpu/vulkan/data/RenderableTexture.hpp"
#include "core/media/BaseAsset.hpp"
#include "include/core/SkImage.h"

struct CacheEntry {
  std::shared_ptr<RenderableTexture> texture;
  MediaType type;
  glm::mat4 scaledModel{1.0f};
  sk_sp<SkImage> skiaImage;
  int64_t skiaImageGPUFrame = -1000;
};
