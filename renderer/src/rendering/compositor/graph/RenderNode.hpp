
#pragma once
#include <functional>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

#include "core/gpu/vulkan/data/RenderableTexture.hpp"
#include "core/rendering/FrameSnapshot.hpp"
#include "core/rendering/compositor/CacheEntry.hpp"
#include <glm/glm.hpp>

class SkCanvas;
class GrDirectContext;
class SkTypeface;
class LottieAnimationInstance;
template <typename T> class sk_sp;

struct RenderContext {
  SkCanvas *canvas = nullptr;
  GrDirectContext *grCtx = nullptr;
  int64_t currentFrame = 0;

  // Viewport / camera
  float width = 0.f;
  float height = 0.f;
  float panX = 0.f;
  float panY = 0.f;
  float zoom = 1.f;

  std::unordered_map<std::string, CacheEntry> *gpuTextureCache = nullptr;

  std::string clipIdPrefix;

  std::function<sk_sp<SkTypeface>(const std::string &)> getTypeface;

  // Lottie animation cache
  std::unordered_map<std::string, std::unique_ptr<LottieAnimationInstance>>
      *lottieAnimCache = nullptr;
};

struct RenderNode {
  std::string nodeId;
  std::vector<std::string> dependsOn;
  int priority = 0;

  virtual void prepare(RenderContext &ctx) {}

  virtual void execute(RenderContext &ctx) = 0;

  virtual const char *typeName() const = 0;
  virtual ~RenderNode() = default;

  RenderNode(const RenderNode &) = delete;
  RenderNode &operator=(const RenderNode &) = delete;

protected:
  RenderNode() = default;
};
