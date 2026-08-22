#pragma once
#include <QWindow>
#include <atomic>
#include <chrono>
#include <glm/glm.hpp>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

struct PerfStats {
  std::atomic<float> tickMs{0.f};
  std::atomic<float> uploadMs{0.f};
  std::atomic<float> renderMs{0.f};
  std::atomic<float> fps{0.f};
  std::atomic<int> activeClips{0};
  std::atomic<int> droppedFrames{0};
  std::atomic<int> gpuCacheSize{0};
};

#include "core/audio/Prefetecher/AudioPrefetcher.hpp"
#include "core/engine/DecodeScheduler.hpp"
#include "core/gpu/vulkan/data/RenderableTexture.hpp"
#include "core/gpu/vulkan/device/DeviceContext.hpp"
#include "core/gpu/vulkan/memory/Texture.hpp"
#include "core/gpu/vulkan/skia/SkiaContext.hpp"
#include "core/media/MediaAsset.hpp"
#include "core/media/MediaPool.hpp"
#include "core/rendering/FrameSnapshot.hpp"
#include "core/rendering/Renderer.hpp"
#include "core/rendering/clips/ShapeClip.hpp"
#include "core/rendering/clips/TextClip.hpp"
#include "core/rendering/clips/VideoClip.hpp"
#include "core/rendering/clips/compClip.hpp"
#include "core/rendering/clips/lottieClip.hpp"
#include "core/rendering/clips/mask/MaskGroupComponent.hpp"
#include "core/rendering/clips/svgClip.hpp"
#include "core/rendering/compositor/CacheEntry.hpp"
#include "core/rendering/timeline/Timeline.hpp"
#include "include/core/SkImage.h"

class LottieAnimationInstance;

class SkFontMgr;
class SkTypeface;
class Project; // forward-declared for setProject() / drawComp()

class Compositor {
public:
  Compositor(QWindow *window, DeviceContext *context,
             Timeline *initialTimeline);
  ~Compositor();

  // non-copyable
  Compositor(const Compositor &) = delete;
  Compositor &operator=(const Compositor &) = delete;

  // MAIN LOOP
  void tick(float width, float height, float panX, float panY, float zoom);

  void recreateSwapchain();

  void play();
  void pause();
  void stop();
  void seekToFrame(int64_t frame);

  Timeline *getTimeline() const;
  MediaPool *getMediaPool() const;
  Renderer *getRenderer() const;

  void setTimeline(Timeline *newTimeline);
  void setProject(Project *project) { m_project = project; }

  int addTrack(std::string TrackName);
  void initSkiaSurfaces();

  void setSkiaPlumbingTestMode(bool enabled) {
    m_skiaPlumbingTestMode = enabled;
  }
  bool isSkiaPlumbingTestMode() const { return m_skiaPlumbingTestMode; }
  void runSkiaPlumbingTest();

  const PerfStats &getPerfStats() const { return m_perfStats; }

private:
  PerfStats m_perfStats;
  int m_fpsFrameCount = 0;
  std::chrono::steady_clock::time_point m_fpsLastTime =
      std::chrono::steady_clock::now();

  std::mutex m_snapMutex;

  void applyPendingTimeline();
  // timeline
  Timeline *m_timeline = nullptr;

  std::atomic<Timeline *> m_pendingTimeline{nullptr};
  Project *m_project = nullptr; // for nested-timeline lookup (drawComp)

  std::unique_ptr<Renderer> m_renderer;
  DeviceContext *m_context;

  std::unique_ptr<AudioPrefetcher> m_audioPrefetcher;
  std::unordered_set<std::string> m_activeClipIds;

  CommandPool *m_transferCommandPool = nullptr;
  VkFence m_transferFence = VK_NULL_HANDLE;
  bool m_transferFenceActive = false;
  std::vector<VkSemaphore> m_pendingUploadSems;

  // skia main instance
  std::unique_ptr<SkiaContext> m_skiaContext;

  // Cache skia surface
  std::vector<sk_sp<SkSurface>> m_SkiaSurface;

  sk_sp<SkFontMgr> m_skiaFontMgr;
  std::unordered_map<std::string, sk_sp<SkTypeface>> m_skiaTypefaceCache;
  sk_sp<SkTypeface> getSkiaTypeface(const std::string &fontName);

  bool m_skiaPlumbingTestMode = false;

  std::shared_ptr<RenderableTexture>
  uploadFrame(const std::string &clipId, int64_t localFrame,
              std::shared_ptr<MediaAsset> asset,
              std::shared_ptr<DecodedFrame> decodedFrame);

  void uploadNestedClips(const std::vector<Timeline::ActiveClip> &clips,
                         int64_t parentLocalFrame,
                         const std::string &pumpPrefix,
                         std::unordered_set<std::string> &visited,
                         DecodeScheduler &scheduler);

  // Store CacheEntry
  std::unordered_map<std::string, CacheEntry> m_gpuTextureCache;

  void evictGPUCache(const std::vector<Timeline::ActiveClip> &activeClips,
                     int64_t currentFrame);

  std::string makeCacheKey(const std::string &assetId, int64_t frame) const;
  FrameSnapshot buildSnapshotMetadata(int64_t frame);
  void enrichSnapshot(FrameSnapshot &snap);
  VkImageView createHardwarePlaneView(VkImage image,
                                      VkImageAspectFlagBits aspect,
                                      VkFormat format);

  sk_sp<SkImage> wrapRGBAToSkImage(const Texture &tex);
  sk_sp<SkImage>
  wrapVkImageToSkImage(std::shared_ptr<RenderableTexture> texture);
  void drawSolid(SkCanvas *canvas, solidClip *clip);
  void drawText(SkCanvas *canvas, TextClip *clip);
  void drawVideo(SkCanvas *canvas, VideoClip *clip, sk_sp<SkImage> frame);
  void drawShape(SkCanvas *canvas, ShapeClip *clip);
  void drawSvg(SkCanvas *canvas, svgClip *clip);
  void drawLottie(SkCanvas *canvas, lottieClip *clip);
  void drawComp(SkCanvas *canvas, compClip *clip, int64_t currentFrame,
                std::unordered_set<std::string> visited = {});

  void renderTimelineToCanvas(Timeline *tl, SkCanvas *canvas,
                              int64_t localFrame,
                              std::unordered_set<std::string> visited = {},
                              const std::string &compPrefix = "");

  void applyMasks(SkCanvas *canvas, const MaskGroupComponent *masks,
                  const glm::mat4 &clipModel,
                  const std::function<void()> &drawFn);

  void drawClipWithEffects(SkCanvas *canvas, baseClip *clip,
                           int64_t currentFrame,
                           const std::function<void(SkCanvas *)> &drawFn);

  sk_sp<SkImage> renderSelectedCharsOffscreen(GrDirectContext *grCtx,
                                              SkCanvas *refCanvas,
                                              TextClip *clip,
                                              const std::string &selectorId);

  std::unordered_map<std::string, std::unique_ptr<LottieAnimationInstance>>
      m_lottieAnimCache;

  void drawSkiaFrame(uint32_t imageIndex, VkSemaphore imageAvailSem,
                     VkSemaphore presentSem, int64_t currentFrame,
                     const std::vector<Timeline::ActiveClip> &activeClips,
                     float width, float height, float panX, float panY,
                     float zoom, std::vector<VkSemaphore> uploadSems);

  // lightweight debug HUD
  void drawDebugOverlay(SkCanvas *canvas, int64_t currentFrame,
                        size_t clipCount);
};