#include "Compositor.hpp"
#include "core/EngineCore.hpp"
#include "core/SkAlphaType.h"
#include "core/SkBlurTypes.h"
#include "core/SkCanvas.h"
#include "core/SkColorSpace.h"
#include "core/SkColorType.h"
#include "core/SkData.h"
#include "core/SkFont.h"
#include "core/SkImage.h"
#include "core/SkImageInfo.h"
#include "core/SkM44.h"
#include "core/SkMaskFilter.h"
#include "core/SkPaint.h"
#include "core/SkPath.h"
#include "core/SkRect.h"
#include "core/SkSamplingOptions.h"
#include "core/api/Logger.hpp"
#include "core/gpu/vulkan/command/CommandPool.hpp"
#include "core/gpu/vulkan/data/DecodedFrame.hpp"
#include "core/gpu/vulkan/data/Vertex.hpp"
#include "core/media/LottieAsset.hpp"
#include "core/project/Project.hpp"
#include "core/rendering/FrameSnapshot.hpp"
#include "core/rendering/clips/AudioClip.hpp"
#include "core/rendering/clips/ShapeClip.hpp"
#include "core/rendering/clips/TextClip.hpp"
#include "core/rendering/clips/solidClip.hpp"
#include "core/rendering/compositor/graph/GraphBuilder.hpp"
#include "core/rendering/compositor/graph/RenderGraph.hpp"
#include "core/rendering/effects/EffectInstance.hpp"
#include "core/rendering/text/TextEngine.hpp"
#include "core/rendering/timeline/TimelineConfig.hpp"
#include "effects/SkImageFilters.h"
#include "include/core/SkFontMgr.h"
#include "include/core/SkTypeface.h"
#include <functional>
#include <shared_mutex>

#ifdef _WIN32
#include "include/ports/SkTypeface_win.h"
#endif
#include "gpu/GpuTypes.h"
#include "gpu/ganesh/GrBackendSemaphore.h"
#include "gpu/ganesh/GrBackendSurface.h"
#include "gpu/ganesh/GrDirectContext.h"
#include "gpu/ganesh/GrTypes.h"
#include "gpu/ganesh/GrYUVABackendTextures.h"
#include "gpu/ganesh/SkImageGanesh.h"
#include "gpu/ganesh/SkSurfaceGanesh.h"
#include "gpu/ganesh/vk/GrVkBackendSemaphore.h"
#include "gpu/ganesh/vk/GrVkBackendSurface.h"
#include "gpu/ganesh/vk/GrVkTypes.h"
#include "gpu/vk/VulkanTypes.h"
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <glm/gtc/matrix_transform.hpp>
#include <memory>
#include <string>
#include <unordered_set>

FrameSnapshot Compositor::buildSnapshotMetadata(int64_t frame) {

  FrameSnapshot snap;
  snap.frame = frame;
  // From timline config
  const TimelineConfig &cfg = m_timeline->getConfig();
  snap.fps = static_cast<float>(cfg.fps());
  snap.compWidth = cfg.width();
  snap.compHeight = cfg.height();

  for (int i = 0; i < m_timeline->getTrackCount(); ++i) {
    BaseTrack *track = m_timeline->getTrack(i);
    if (!track || track->isAudio())
      continue;

    for (const auto &clipPtr : track->getClips()) {
      baseClip *clip = clipPtr.get();
      if (frame < clip->getStartFrame() || frame >= clip->getEndFrame())
        continue;

      ClipSnapshot cs;
      cs.clipId = clip->getId();
      cs.localFrame = frame - clip->getStartFrame();
      cs.clipOwner = clipPtr;

      // VideoClip / ImageClip

      if (auto *vc = dynamic_cast<VideoClip *>(clip)) {
        cs.type = SnapshotClipType::Video;
        cs.masks = vc->getMaskGroup();
        const auto &pc = vc->getPushConstants();
        cs.model = pc.model;
        cs.opacity = pc.opacity;
        cs.size = glm::vec2{0.f, 0.f};
        if (auto asset = vc->getSourceAsset())
          cs.assetId = asset->getId();

        // LottieClip

      } else if (auto *lc = dynamic_cast<lottieClip *>(clip)) {
        cs.type = SnapshotClipType::Lottie;
        cs.masks = lc->getMaskGroup();
        const auto &pc = lc->getPushConstants();
        cs.model = pc.model;
        cs.opacity = pc.opacity;
        cs.size = pc.size;
        if (auto asset = lc->getSourceAsset())
          cs.assetId = asset->getId();

        // TextClip

      } else if (auto *tc = dynamic_cast<TextClip *>(clip)) {
        cs.type = SnapshotClipType::Text;
        cs.masks = tc->getMaskGroup();
        const auto &pc = tc->getPushConstants();
        cs.model = pc.model;
        cs.opacity = pc.opacity;
        cs.size = glm::vec2{0.f, 0.f};
        cs.text = tc->getCurrentText();
        cs.fontName = tc->getFontName();
        cs.fontSize = tc->getLayout().fontSize;
        cs.textColor = pc.textColor;

        // SolidClip

      } else if (auto *sc = dynamic_cast<solidClip *>(clip)) {
        cs.type = SnapshotClipType::Solid;
        cs.masks = sc->getMaskGroup();
        const auto &pc = sc->getPushConstants();
        cs.model = pc.model;
        cs.opacity = pc.opacity;
        cs.size = pc.size;
        cs.solidColor = pc.solidColor;

        // ShapeClip

      } else if (auto *shc = dynamic_cast<ShapeClip *>(clip)) {
        cs.type = SnapshotClipType::Shape;
        cs.masks = shc->getMaskGroup();
        const auto &pc = shc->getPushConstants();
        cs.model = pc.model;
        cs.opacity = pc.opacity;
        cs.size = glm::vec2{0.f, 0.f};

        for (const auto &shape : shc->getShapes()) {
          ShapeLayerSnapshot sls;
          sls.path = shape->generatePath(cs.localFrame);
          sls.shapeModel = shape->getShapeModelMatrix();
          sls.fillColor = shape->getFillColor();
          sls.strokeColor = shape->getStrokeColor();
          sls.fillOpacity = shape->getFillOpacity();
          sls.strokeWidth = shape->getStrokeWidth();
          sls.hasShadow = shape->isShadowEnabled();
          if (sls.hasShadow) {
            sls.shadowColor = shape->getShadowColor();
            sls.shadowAngle = shape->getShadowAngle();
            sls.shadowDistance = shape->getShadowDistance();
            sls.shadowBlur = shape->getShadowBlur();
          }
          cs.shapes.push_back(std::move(sls));
        }

        // SvgClip

      } else if (auto *svg = dynamic_cast<svgClip *>(clip)) {
        cs.type = SnapshotClipType::Svg;
        cs.masks = svg->getMaskGroup();
        const auto &pc = svg->getPushConstants();
        cs.model = pc.model;
        cs.opacity = pc.opacity;
        cs.size = pc.size;
      }

      snap.clips.push_back(std::move(cs));
    }
  }
  return snap;
}

void Compositor::enrichSnapshot(FrameSnapshot &snap) {

  for (auto &cs : snap.clips) {
    if (cs.type != SnapshotClipType::Video &&
        cs.type != SnapshotClipType::Lottie)
      continue;

    auto it = m_gpuTextureCache.find(cs.clipId);
    if (it == m_gpuTextureCache.end())
      continue;

    auto &ce = it->second;

    if (!ce.skiaImage ||
        ce.skiaImageGPUFrame != ce.texture->currentFrameOnGPU) {
      ce.skiaImage = wrapVkImageToSkImage(ce.texture);
      ce.skiaImageGPUFrame = ce.texture->currentFrameOnGPU;
    }

    cs.gpuImage = ce.skiaImage;
    cs.model = ce.scaledModel;
  }
}

static void convertYUV420pToRGBA(const uint8_t *dataY, const uint8_t *dataU,
                                 const uint8_t *dataV, int width, int height,
                                 std::vector<uint8_t> &outRGBA) {
  outRGBA.resize(static_cast<size_t>(width) * height * 4);
  const int halfW = (width + 1) / 2;
  for (int y = 0; y < height; ++y) {
    for (int x = 0; x < width; ++x) {
      const int yIdx = y * width + x;
      const int uvIdx = (y / 2) * halfW + (x / 2);

      const int Y = dataY[yIdx];
      const int U = dataU[uvIdx] - 128;
      const int V = dataV[uvIdx] - 128;

      const int R = std::clamp(Y + ((359 * V) >> 8), 0, 255);
      const int G = std::clamp(Y - ((88 * U + 183 * V) >> 8), 0, 255);
      const int B = std::clamp(Y + ((454 * U) >> 8), 0, 255);

      const size_t outIdx = static_cast<size_t>(yIdx) * 4;
      outRGBA[outIdx + 0] = static_cast<uint8_t>(R);
      outRGBA[outIdx + 1] = static_cast<uint8_t>(G);
      outRGBA[outIdx + 2] = static_cast<uint8_t>(B);
      outRGBA[outIdx + 3] = 255;
    }
  }
}

static void convertNV12ToRGBA(const uint8_t *dataY, const uint8_t *dataUV,
                              int width, int height,
                              std::vector<uint8_t> &outRGBA) {
  outRGBA.resize(static_cast<size_t>(width) * height * 4);
  const int halfW = (width + 1) / 2;
  for (int y = 0; y < height; ++y) {
    for (int x = 0; x < width; ++x) {
      const int yIdx = y * width + x;
      const int uvIdx = (y / 2) * halfW * 2 + (x / 2) * 2;

      const int Y = dataY[yIdx];
      const int U = dataUV[uvIdx] - 128;
      const int V = dataUV[uvIdx + 1] - 128;

      const int R = std::clamp(Y + ((359 * V) >> 8), 0, 255);
      const int G = std::clamp(Y - ((88 * U + 183 * V) >> 8), 0, 255);
      const int B = std::clamp(Y + ((454 * U) >> 8), 0, 255);

      const size_t outIdx = static_cast<size_t>(yIdx) * 4;
      outRGBA[outIdx + 0] = static_cast<uint8_t>(R);
      outRGBA[outIdx + 1] = static_cast<uint8_t>(G);
      outRGBA[outIdx + 2] = static_cast<uint8_t>(B);
      outRGBA[outIdx + 3] = 255;
    }
  }
}

Compositor::Compositor(QWindow *window, DeviceContext *context,
                       Timeline *initialTimeline)
    : m_context(context), m_timeline(initialTimeline) {
  m_renderer = std::make_unique<Renderer>(window, m_context);
  m_skiaContext = std::make_unique<SkiaContext>(m_context);
  m_audioPrefetcher = std::make_unique<AudioPrefetcher>(m_timeline);
  m_audioPrefetcher->bindToTimeline(m_timeline);

  m_transferCommandPool =
      new CommandPool(m_context, m_context->getTransferQueueFamilyIndex(),
                      VK_COMMAND_POOL_CREATE_TRANSIENT_BIT);

  VkFenceCreateInfo fenceCI{};
  fenceCI.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO;
  fenceCI.flags = 0;
  vkCreateFence(m_context->getLogicalDevice(), &fenceCI, nullptr,
                &m_transferFence);

  m_timeline->addVideoTrack("T1");
  m_timeline->addVideoTrack("T2");
  m_timeline->addVideoTrack("T3");
  m_timeline->addVideoTrack("T4");
  m_timeline->addVideoTrack("T5");
  m_timeline->addAudioTrack("A1");
  m_timeline->addAudioTrack("A2");
  m_timeline->addAudioTrack("A3");
  m_timeline->addAudioTrack("A4");

  DecodeScheduler::get().getDecoderPool()->setDeviceContext(m_context);

  m_renderer->setSwapchainRecreateCallback([this]() {
    m_SkiaSurface.clear();
    initSkiaSurfaces();
  });

  initSkiaSurfaces();
  LOG_INFO("Compositor initialized.");

  // TEMPORARY
  {
    auto diagAsset = std::make_shared<MediaAsset>(
        "diag_img_asset",
        "D:/Qteee-Vulkan/src/ui/resources/assets/icons/blades.png",
        "blades.png");
    diagAsset->setType(MediaType::image);
    diagAsset->setHasVideoStream(true);
    diagAsset->setWidth(256);
    diagAsset->setHeight(256);
    diagAsset->setFrameRate(30.0);
    std::string diagClipId = m_timeline->addClipToTrack(diagAsset, 0, 0, 300);
    LOG_INFO("[DIAG] Added image diagnostic clip: " << diagClipId);
  }
}

Compositor::~Compositor() {
  m_gpuTextureCache.clear();
  m_activeClipIds.clear();
  m_SkiaSurface.clear();
  m_skiaTypefaceCache.clear();
  m_skiaFontMgr.reset();

  if (m_transferFence != VK_NULL_HANDLE) {
    vkWaitForFences(m_context->getLogicalDevice(), 1, &m_transferFence, VK_TRUE,
                    UINT64_MAX);
    vkDestroyFence(m_context->getLogicalDevice(), m_transferFence, nullptr);
    m_transferFence = VK_NULL_HANDLE;
  }
  delete m_transferCommandPool;
  m_transferCommandPool = nullptr;

  LOG_INFO("Compositor destroyed.");
}

void Compositor::drawSkiaFrame(
    uint32_t imageIndex, VkSemaphore imageAvailSem, VkSemaphore presentSem,
    int64_t currentFrame, const std::vector<Timeline::ActiveClip> &activeClips,
    float width, float height, float panX, float panY, float zoom,
    std::vector<VkSemaphore> uploadSems) {

  if (imageIndex >= m_SkiaSurface.size() || !m_SkiaSurface[imageIndex]) {
    LOG_WARN("[drawSkiaFrame] No valid SkSurface for imageIndex=" +
             std::to_string(imageIndex));
    return;
  }

  GrDirectContext *grCtx = m_skiaContext->getDirectContext();
  if (!grCtx) {
    LOG_WARN("[drawSkiaFrame] GrDirectContext is null");
    return;
  }

  m_context->lockGraphicsQueue();

  std::vector<GrBackendSemaphore> waitSems;
  waitSems.reserve(1 + uploadSems.size());
  GrBackendSemaphore imageAvailBackend =
      GrBackendSemaphores::MakeVk(imageAvailSem);
  waitSems.push_back(imageAvailBackend);
  for (VkSemaphore s : uploadSems) {
    GrBackendSemaphore uploadBackend = GrBackendSemaphores::MakeVk(s);
    waitSems.push_back(uploadBackend);
  }
  grCtx->wait(static_cast<int>(waitSems.size()), waitSems.data(), false);

  SkCanvas *canvas = m_SkiaSurface[imageIndex]->getCanvas();
  canvas->clear(SK_ColorBLACK);

  RenderContext ctx;
  ctx.canvas = canvas;
  ctx.grCtx = grCtx;
  ctx.currentFrame = currentFrame;
  ctx.width = width;
  ctx.height = height;
  ctx.panX = panX;
  ctx.panY = panY;
  ctx.zoom = zoom;
  ctx.gpuTextureCache = &m_gpuTextureCache;
  ctx.lottieAnimCache = &m_lottieAnimCache;
  ctx.getTypeface = [this](const std::string &name) {
    return getSkiaTypeface(name);
  };

  RenderGraph graph = GraphBuilder::build(activeClips, currentFrame,
                                          &m_gpuTextureCache, m_project);
  graph.compile();
  graph.execute(ctx);

  //  PRESENT_SRC_KHR.
  GrFlushInfo flushInfo;
  GrBackendSemaphore signalBackendSem = GrBackendSemaphores::MakeVk(presentSem);
  flushInfo.fNumSemaphores = 1;
  flushInfo.fSignalSemaphores = &signalBackendSem;

  grCtx->flush(m_SkiaSurface[imageIndex].get(),
               SkSurfaces::BackendSurfaceAccess::kPresent, flushInfo);
  grCtx->submit(GrSyncCpu::kNo);

  m_context->unlockGraphicsQueue();
}

sk_sp<SkTypeface> Compositor::getSkiaTypeface(const std::string &fontName) {
  if (!m_skiaFontMgr) {
#ifdef _WIN32
    m_skiaFontMgr = SkFontMgr_New_DirectWrite();
#endif
    if (!m_skiaFontMgr) {
      m_skiaFontMgr = SkFontMgr::RefEmpty();
    }
  }
  if (!m_skiaFontMgr)
    return nullptr;

  std::string lookupName = fontName.empty() ? "Arial" : fontName;
  auto it = m_skiaTypefaceCache.find(lookupName);
  if (it != m_skiaTypefaceCache.end() && it->second) {
    return it->second;
  }

  sk_sp<SkTypeface> tf = nullptr;
  if (EngineCore::get().getTextEngine()) {
    const auto &systemFonts =
        EngineCore::get().getTextEngine()->getSystemFonts();
    auto fontIt = systemFonts.find(lookupName);
    if (fontIt != systemFonts.end()) {
      tf = m_skiaFontMgr->makeFromFile(fontIt->second.c_str());
    }
  }
  if (!tf) {
    tf = m_skiaFontMgr->matchFamilyStyle(lookupName.c_str(), SkFontStyle());
  }
  if (!tf && lookupName != "Arial") {
    tf = getSkiaTypeface("Arial");
  }

  if (tf) {
    m_skiaTypefaceCache[lookupName] = tf;
  }
  return tf;
}

sk_sp<SkImage>
Compositor::wrapVkImageToSkImage(std::shared_ptr<RenderableTexture> texture) {
  if (!texture || !m_skiaContext || !m_skiaContext->getDirectContext()) {
    return nullptr;
  }

  if (texture->texRGBA) {
    return wrapRGBAToSkImage(*texture->texRGBA);
  }

  LOG_WARN("[wrapVkImage] No texRGBA on renderable â€” this frame type was not "
           "converted during upload. type=" +
           std::to_string(static_cast<int>(texture->type)));
  return nullptr;
}
void Compositor::tick(float width, float height, float panX, float panY,
                      float zoom) {

  applyPendingTimeline();

  auto tickStart = std::chrono::steady_clock::now();

  if (m_transferCommandPool && m_transferFence != VK_NULL_HANDLE &&
      m_transferFenceActive) {
    VkResult fenceStatus =
        vkGetFenceStatus(m_context->getLogicalDevice(), m_transferFence);
    if (fenceStatus == VK_SUCCESS) {
      vkResetFences(m_context->getLogicalDevice(), 1, &m_transferFence);
      vkResetCommandPool(m_context->getLogicalDevice(),
                         m_transferCommandPool->getHandle(), 0);
      m_transferFenceActive = false;
    }
  }

  bool hasTimeline = false;
  int64_t currentFrame = 0;
  std::vector<Timeline::ActiveClip> activeClips;
  FrameSnapshot snap;

  {
    std::lock_guard<std::mutex> lk(m_snapMutex);

    hasTimeline = (m_timeline != nullptr);
    if (hasTimeline) {
      std::shared_lock tlLk(m_timeline->rwLock());

      // Advance the playhead
      m_timeline->tick();
      currentFrame = m_timeline->getCurrentFrame();

      auto &scheduler = DecodeScheduler::get();
      constexpr int64_t WAKE_RADIUS = 120;

      // Register/unregister clips near the playhead
      for (int i = 0; i < m_timeline->getTrackCount(); ++i) {
        BaseTrack *track = m_timeline->getTrack(i);
        if (!track)
          continue;

        for (const auto &clip : track->getClips()) {
          const std::string &clipId = clip->getId();
          bool isNear = (currentFrame >= clip->getStartFrame() - WAKE_RADIUS &&
                         currentFrame <= clip->getEndFrame() + WAKE_RADIUS);

          if (isNear) {
            if (!m_activeClipIds.count(clipId)) {
              auto asset = clip->getSourceAsset();
              if (asset) {
                if (track->isAudio()) {
                  auto audioClip = std::dynamic_pointer_cast<AudioClip>(clip);
                  if (audioClip)
                    m_audioPrefetcher->registerClip(
                        clipId, asset->getFilepath(),
                        audioClip->getRingBuffer(), audioClip->getStartFrame(),
                        audioClip->getInPoint());
                } else {
                  auto lottieAsset =
                      std::dynamic_pointer_cast<LottieAsset>(asset);
                  if (lottieAsset) {
                    double fps = m_timeline->getConfig().fps();
                    int w =
                        static_cast<int>(lottieAsset->getNaturalW() > 0
                                             ? lottieAsset->getNaturalW()
                                             : m_timeline->getConfig().width());
                    int h = static_cast<int>(
                        lottieAsset->getNaturalH() > 0
                            ? lottieAsset->getNaturalH()
                            : m_timeline->getConfig().height());
                    scheduler.registerLottieClip(clipId, lottieAsset, w, h,
                                                 fps);
                  } else {
                    auto mediaAsset =
                        std::dynamic_pointer_cast<MediaAsset>(asset);
                    if (mediaAsset)
                      scheduler.registerClip(clipId, *mediaAsset);
                  }
                }
                m_activeClipIds.insert(clipId);
              }
            }
          } else {
            if (m_activeClipIds.count(clipId)) {
              if (track->isAudio())
                m_audioPrefetcher->unregisterClip(clipId);
              else {
                scheduler.unregisterLottieClip(clipId);
                scheduler.unregisterClip(clipId);
              }
              m_activeClipIds.erase(clipId);
              m_gpuTextureCache.erase(clipId);
            }
          }
        }
      }

      activeClips = m_timeline->getActiveClips();
      for (const auto &active : activeClips)
        active.clip->evaluateAll(currentFrame);

      snap = buildSnapshotMetadata(currentFrame);
    }
  }

  if (!hasTimeline) {
    m_renderer->updateCanvasUBO(width, height, panX, panY, zoom);
    m_renderer->render(width, height, panX, panY, zoom, {}, {}, {});
    return;
  }

  auto &scheduler = DecodeScheduler::get();

  for (const auto &active : activeClips) {
    // Videos clip
    if (auto videoClip = std::dynamic_pointer_cast<VideoClip>(active.clip)) {
      const std::string &clipId = videoClip->getId();
      auto asset = videoClip->getSourceAssetAs<MediaAsset>();
      int64_t localFrame = videoClip->getLocalFrame(currentFrame);

      if (asset && asset->getType() == MediaType::image) {
        localFrame = 0;
        videoClip->setIsRgba();
        scheduler.prefetchAround(clipId, 0, 0);
      } else {
        scheduler.prefetchAround(clipId, localFrame, 5);
      }

      auto cpuFrame = scheduler.tryGetFrameFromCache(clipId, localFrame);
      auto renderable = uploadFrame(clipId, localFrame, nullptr, cpuFrame);

      if (renderable) {
        CacheEntry &entry = m_gpuTextureCache[clipId];
        entry.texture = renderable;
        entry.type = asset ? asset->getType() : MediaType::video;
        entry.scaledModel = videoClip->getPushConstants().model;
        if (asset) {
          entry.scaledModel = glm::scale(
              entry.scaledModel,
              glm::vec3(asset->getWidth(), asset->getHeight(), 1.0f));
        }
      }
    }

    // Lottie clip
    if (auto *lc = dynamic_cast<lottieClip *>(active.clip.get())) {
      const std::string &clipId = lc->getId();
      const lottiePushConstants &pc = lc->getPushConstants();

      scheduler.prefetchLottieAround(clipId, pc.lottieTime, 12);

      double projectFps = snap.fps > 0.f ? static_cast<double>(snap.fps) : 30.0;
      int64_t lottieFrame = static_cast<int64_t>(pc.lottieTime * projectFps);

      auto cpuFrame = scheduler.tryGetFrameFromCache(clipId, lottieFrame);
      if (!cpuFrame || cpuFrame->isEmpty()) {

        auto staleIt = m_gpuTextureCache.find(clipId);
        if (staleIt != m_gpuTextureCache.end())
          staleIt->second.skiaImage = nullptr;
        continue;
      }

      CacheEntry &entry = m_gpuTextureCache[clipId];

      if (!entry.texture) {
        auto renderable = std::make_shared<RenderableTexture>();
        renderable->type = FrameType::SOFTWARE_RGBA;
        renderable->context = m_context;
        renderable->currentFrameOnGPU = lottieFrame;
        entry.texture = renderable;
        entry.type = MediaType::video;
      }

      entry.scaledModel = pc.model;

      if (entry.texture->currentFrameOnGPU != lottieFrame || !entry.skiaImage) {
        entry.texture->currentFrameOnGPU = lottieFrame;

        const uint8_t *pixels =
            reinterpret_cast<const uint8_t *>(cpuFrame->dataRGBA.data());
        VkDeviceSize imageSize =
            static_cast<VkDeviceSize>(cpuFrame->dataRGBA.size());

        if (!entry.texture->texRGBA) {
          entry.texture->texRGBA = std::make_shared<Texture>(
              m_context, *m_renderer->getCommandPool(),
              m_context->getGraphicQueue(), const_cast<uint8_t *>(pixels),
              imageSize, cpuFrame->width, cpuFrame->height, 4);
        } else {
          if (entry.texture->texRGBA->getWidth() != cpuFrame->width ||
              entry.texture->texRGBA->getHeight() != cpuFrame->height) {
            entry.texture->texRGBA = std::make_shared<Texture>(
                m_context, *m_renderer->getCommandPool(),
                m_context->getGraphicQueue(), const_cast<uint8_t *>(pixels),
                imageSize, cpuFrame->width, cpuFrame->height, 4);
          } else {
            VkSemaphore sem = entry.texture->texRGBA->updatePixelsAsync(
                *m_transferCommandPool, m_context->getTransferQueue(),
                const_cast<uint8_t *>(pixels), imageSize);
            if (sem != VK_NULL_HANDLE)
              m_pendingUploadSems.push_back(sem);
          }
        }

        if (m_pendingUploadSems.empty()) {
          entry.skiaImage = wrapVkImageToSkImage(entry.texture);
          entry.skiaImageGPUFrame = lottieFrame;
        }
      }
    }
  }

  // Process nested comp clips at all depths.
  {
    std::unordered_set<std::string> visitedComps;
    for (const auto &active : activeClips) {
      auto *cc = dynamic_cast<compClip *>(active.clip.get());
      if (!cc || !m_project)
        continue;
      const std::string &nestedId = cc->getNestedTimelineId();
      Timeline *nested = m_project->getTimelineById(nestedId);
      if (!nested)
        continue;

      int64_t compLocalFrame =
          std::max<int64_t>(0, currentFrame - cc->getStartFrame());

      std::vector<Timeline::ActiveClip> nestedClips;
      {
        std::shared_lock lk(nested->rwLock());
        nestedClips = nested->getActiveClipsAt(compLocalFrame);
        for (auto &nc : nestedClips)
          if (nc.clip)
            nc.clip->evaluateAll(compLocalFrame);
      }

      visitedComps.insert(nestedId);
      uploadNestedClips(nestedClips, compLocalFrame, cc->getId() + "_",
                        visitedComps, scheduler);
    }
  }

  enrichSnapshot(snap);
  auto uploadEnd = std::chrono::steady_clock::now();

  std::vector<VkSemaphore> uploadSemsForFrame = std::move(m_pendingUploadSems);
  m_pendingUploadSems.clear();

  if (!uploadSemsForFrame.empty() && m_transferFence != VK_NULL_HANDLE &&
      !m_transferFenceActive) {
    VkSubmitInfo fenceSubmit{};
    fenceSubmit.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
    m_context->lockTransferQueue();
    vkQueueSubmit(m_context->getTransferQueue(), 1, &fenceSubmit,
                  m_transferFence);
    m_context->unlockTransferQueue();
    m_transferFenceActive = true;
  }

  m_renderer->setSkiaCallback([this, activeClipsCopy = activeClips,
                               currentFrame, width, height, panX, panY, zoom,
                               uploadSemsForFrame](uint32_t imageIndex,
                                                   VkSemaphore imageAvailSem,
                                                   VkSemaphore presentSem) {
    drawSkiaFrame(imageIndex, imageAvailSem, presentSem, currentFrame,
                  activeClipsCopy, width, height, panX, panY, zoom,
                  uploadSemsForFrame);
  });

  m_renderer->render(width, height, panX, panY, zoom, {}, {}, {});

  auto tickEnd = std::chrono::steady_clock::now();
  float totalMs =
      std::chrono::duration<float, std::milli>(tickEnd - tickStart).count();
  float uplMs =
      std::chrono::duration<float, std::milli>(uploadEnd - tickStart).count();
  float renMs = totalMs - uplMs;

  m_perfStats.tickMs.store(totalMs, std::memory_order_relaxed);
  m_perfStats.uploadMs.store(uplMs, std::memory_order_relaxed);
  m_perfStats.renderMs.store(renMs, std::memory_order_relaxed);
  m_perfStats.activeClips.store(static_cast<int>(activeClips.size()),
                                std::memory_order_relaxed);
  m_perfStats.gpuCacheSize.store(static_cast<int>(m_gpuTextureCache.size()),
                                 std::memory_order_relaxed);

  ++m_fpsFrameCount;
  auto elapsed = std::chrono::duration<float>(tickEnd - m_fpsLastTime).count();
  if (elapsed >= 1.0f) {
    m_perfStats.fps.store(m_fpsFrameCount / elapsed, std::memory_order_relaxed);
    m_fpsFrameCount = 0;
    m_fpsLastTime = tickEnd;
  }
}

void Compositor::uploadNestedClips(
    const std::vector<Timeline::ActiveClip> &clips, int64_t parentLocalFrame,
    const std::string &pumpPrefix, std::unordered_set<std::string> &visited,
    DecodeScheduler &scheduler) {

  for (const auto &ac : clips) {
    if (!ac.clip)
      continue;

    // VideoClip leaf
    if (auto videoClip = std::dynamic_pointer_cast<VideoClip>(ac.clip)) {
      const std::string contentId = videoClip->getId();
      const std::string pumpId = pumpPrefix + contentId;
      auto asset = videoClip->getSourceAssetAs<MediaAsset>();

      if (!m_activeClipIds.count(pumpId) && asset) {
        scheduler.registerClip(pumpId, *asset, contentId);
        m_activeClipIds.insert(pumpId);
      }

      int64_t vcLocalFrame = videoClip->getLocalFrame(parentLocalFrame);
      if (asset && asset->getType() == MediaType::image) {
        vcLocalFrame = 0;
        videoClip->setIsRgba();
        scheduler.prefetchAround(pumpId, 0, 0);
      } else {
        scheduler.prefetchAround(pumpId, vcLocalFrame, 5);
      }

      auto cpuFrame = scheduler.tryGetFrameFromCache(contentId, vcLocalFrame);
      auto renderable = uploadFrame(pumpId, vcLocalFrame, nullptr, cpuFrame);

      if (renderable) {
        CacheEntry &entry = m_gpuTextureCache[pumpId];
        entry.texture = renderable;
        entry.type = asset ? asset->getType() : MediaType::video;
        entry.scaledModel = videoClip->getPushConstants().model;
        if (asset) {
          entry.scaledModel =
              glm::scale(entry.scaledModel,
                         glm::vec3(asset->getWidth(), asset->getHeight(), 1.f));
        }
        const bool gpuFrameChanged =
            entry.skiaImageGPUFrame != renderable->currentFrameOnGPU;
        if ((!entry.skiaImage || gpuFrameChanged) &&
            m_pendingUploadSems.empty()) {
          entry.skiaImage = wrapVkImageToSkImage(renderable);
          entry.skiaImageGPUFrame = renderable->currentFrameOnGPU;
        }
      }
      continue;
    }

    // CompClip inner node ,recurse one level deeper
    auto *innerCC = dynamic_cast<compClip *>(ac.clip.get());
    if (!innerCC || !m_project)
      continue;

    const std::string &nestedId = innerCC->getNestedTimelineId();
    if (nestedId.empty() || visited.count(nestedId))
      continue; // cycle guard

    Timeline *nested = m_project->getTimelineById(nestedId);
    if (!nested)
      continue;

    // Compute local frame inside this level
    int64_t innerLocalFrame =
        std::max<int64_t>(0, parentLocalFrame - innerCC->getStartFrame());

    std::vector<Timeline::ActiveClip> innerClips;
    {
      std::shared_lock lk(nested->rwLock());
      innerClips = nested->getActiveClipsAt(innerLocalFrame);
      for (auto &ic : innerClips)
        if (ic.clip)
          ic.clip->evaluateAll(innerLocalFrame);
    }

    // The prefix for the next level
    const std::string innerPrefix = pumpPrefix + innerCC->getId() + "_";
    visited.insert(nestedId);
    uploadNestedClips(innerClips, innerLocalFrame, innerPrefix, visited,
                      scheduler);
  }
}

std::shared_ptr<RenderableTexture>
Compositor::uploadFrame(const std::string &clipId, int64_t localFrame,
                        std::shared_ptr<MediaAsset> asset,
                        std::shared_ptr<DecodedFrame> decodedFrame) {
  auto it = m_gpuTextureCache.find(clipId);

  if (it == m_gpuTextureCache.end()) {
    if (!decodedFrame || decodedFrame->isEmpty())
      return nullptr;

    auto renderable = std::make_shared<RenderableTexture>();
    renderable->type = decodedFrame->type;
    renderable->context = m_context;

    auto descriptor =
        std::make_shared<Descriptor>(m_context, m_renderer->getDescriptorPool(),
                                     m_renderer->getClipDescriptorSetLayout());

    if (decodedFrame->type == FrameType::SOFTWARE_YUV) {

      std::vector<uint8_t> rgbaData;
      convertYUV420pToRGBA(decodedFrame->dataY.data(),
                           decodedFrame->dataU.data(),
                           decodedFrame->dataV.data(), decodedFrame->width,
                           decodedFrame->height, rgbaData);

      renderable->type = FrameType::SOFTWARE_RGBA;
      renderable->texRGBA = std::make_shared<Texture>(
          m_context, *m_renderer->getCommandPool(),
          m_context->getGraphicQueue(), rgbaData.data(), rgbaData.size(),
          decodedFrame->width, decodedFrame->height, 4);

      descriptor->updateImageDescriptor(renderable->texRGBA->getImageView(),
                                        m_renderer->getDefaultSampler(), 0);
      auto dummyTex = m_renderer->getDummyTexture();
      descriptor->updateImageDescriptor(dummyTex->getImageView(),
                                        m_renderer->getDefaultSampler(), 1);
      descriptor->updateImageDescriptor(dummyTex->getImageView(),
                                        m_renderer->getDefaultSampler(), 2);

    } else if (decodedFrame->type == FrameType::SOFTWARE_RGBA) {

      renderable->texRGBA = std::make_shared<Texture>(
          m_context, *m_renderer->getCommandPool(),
          m_context->getGraphicQueue(), decodedFrame->dataRGBA.data(),
          decodedFrame->dataRGBA.size(), decodedFrame->width,
          decodedFrame->height, 4);

      descriptor->updateImageDescriptor(renderable->texRGBA->getImageView(),
                                        m_renderer->getDefaultSampler(), 0);

      auto dummyTex = m_renderer->getDummyTexture();
      descriptor->updateImageDescriptor(dummyTex->getImageView(),
                                        m_renderer->getDefaultSampler(), 1);
      descriptor->updateImageDescriptor(dummyTex->getImageView(),
                                        m_renderer->getDefaultSampler(), 2);

    } else if (decodedFrame->type == FrameType::HARDWARE_CACHED) {
      std::vector<uint8_t> rgbaData;
      convertNV12ToRGBA(decodedFrame->dataNV12Y.data(),
                        decodedFrame->dataNV12UV.data(), decodedFrame->width,
                        decodedFrame->height, rgbaData);

      renderable->type = FrameType::SOFTWARE_RGBA;
      renderable->texRGBA = std::make_shared<Texture>(
          m_context, *m_renderer->getCommandPool(),
          m_context->getGraphicQueue(), rgbaData.data(), rgbaData.size(),
          decodedFrame->width, decodedFrame->height, 4);

      descriptor->updateImageDescriptor(renderable->texRGBA->getImageView(),
                                        m_renderer->getDefaultSampler(), 0);
      auto dummyTex = m_renderer->getDummyTexture();
      descriptor->updateImageDescriptor(dummyTex->getImageView(),
                                        m_renderer->getDefaultSampler(), 1);
      descriptor->updateImageDescriptor(dummyTex->getImageView(),
                                        m_renderer->getDefaultSampler(), 2);
    }

    renderable->descriptor = descriptor;
    renderable->currentFrameOnGPU = localFrame;
    m_gpuTextureCache[clipId].texture = renderable;
    m_gpuTextureCache[clipId].type =
        asset ? asset->getType() : MediaType::video;
    return renderable;
  }

  auto renderable = it->second.texture;
  if (renderable->currentFrameOnGPU == localFrame || !decodedFrame ||
      decodedFrame->isEmpty()) {
    return renderable;
  }

  if (decodedFrame->type == FrameType::SOFTWARE_YUV) {
    if (!decodedFrame->isStatic && renderable->texRGBA) {
      std::vector<uint8_t> rgbaData;
      convertYUV420pToRGBA(decodedFrame->dataY.data(),
                           decodedFrame->dataU.data(),
                           decodedFrame->dataV.data(), decodedFrame->width,
                           decodedFrame->height, rgbaData);
      renderable->texRGBA->updatePixels(*m_renderer->getCommandPool(),
                                        m_context->getGraphicQueue(),
                                        rgbaData.data(), rgbaData.size());
    }
  } else if (decodedFrame->type == FrameType::SOFTWARE_RGBA) {
    if (!decodedFrame->isStatic && renderable->texRGBA &&
        !decodedFrame->dataRGBA.empty()) {
      VkSemaphore sem = renderable->texRGBA->updatePixelsAsync(
          *m_transferCommandPool, m_context->getTransferQueue(),
          decodedFrame->dataRGBA.data(), decodedFrame->dataRGBA.size());
      if (sem != VK_NULL_HANDLE)
        m_pendingUploadSems.push_back(sem);
    }
  } else if (decodedFrame->type == FrameType::HARDWARE_CACHED) {
    if (!decodedFrame->isStatic && renderable->texRGBA) {
      std::vector<uint8_t> rgbaData;
      convertNV12ToRGBA(decodedFrame->dataNV12Y.data(),
                        decodedFrame->dataNV12UV.data(), decodedFrame->width,
                        decodedFrame->height, rgbaData);
      VkSemaphore sem = renderable->texRGBA->updatePixelsAsync(
          *m_transferCommandPool, m_context->getTransferQueue(),
          rgbaData.data(), rgbaData.size());
      if (sem != VK_NULL_HANDLE)
        m_pendingUploadSems.push_back(sem);
    }
  }

  renderable->currentFrameOnGPU = localFrame;
  return renderable;
}

void Compositor::evictGPUCache(
    const std::vector<Timeline::ActiveClip> &activeClips,
    int64_t currentFrame) {}

// CACHE KEY
std::string Compositor::makeCacheKey(const std::string &assetId,
                                     int64_t frame) const {
  return assetId + "_frame_" + std::to_string(frame);
}

// SWAPCHAIN
void Compositor::recreateSwapchain() {
  std::lock_guard<std::mutex> lock(m_snapMutex);
  m_renderer->recreateSwapchain();
}

// PLAYBACK CONTROLS
void Compositor::play() {
  std::lock_guard<std::mutex> lock(m_snapMutex);
  m_timeline->play();
}
void Compositor::pause() {
  std::lock_guard<std::mutex> lock(m_snapMutex);
  m_timeline->pause();
}
void Compositor::stop() {
  std::lock_guard<std::mutex> lock(m_snapMutex);
  m_timeline->stop();
}
void Compositor::seekToFrame(int64_t frame) {
  std::lock_guard<std::mutex> lock(m_snapMutex);
  m_timeline->seekToFrame(frame);
  double fps = m_timeline->getConfig().fps();
  m_audioPrefetcher->onSeek(frame, fps);
}

// ACCESSORS
Timeline *Compositor::getTimeline() const { return m_timeline; }
Renderer *Compositor::getRenderer() const { return m_renderer.get(); }

void Compositor::setTimeline(Timeline *newTimeline) {

  m_pendingTimeline.store(newTimeline, std::memory_order_release);

  {
    std::lock_guard<std::mutex> lock(m_snapMutex);
    m_audioPrefetcher = std::make_unique<AudioPrefetcher>(newTimeline);
    m_audioPrefetcher->bindToTimeline(newTimeline);
  }
}

void Compositor::applyPendingTimeline() {
  Timeline *pending =
      m_pendingTimeline.exchange(nullptr, std::memory_order_acquire);
  if (!pending)
    return;

  std::lock_guard<std::mutex> lock(m_snapMutex);
  m_timeline = pending;
  m_SkiaSurface.clear();
  m_gpuTextureCache.clear();
  m_activeClipIds.clear();
  initSkiaSurfaces();
  LOG_INFO("Compositor swapped to new Timeline.");
}

/* bool Compositor::addClipToTrack(const std::string &assetId, int trackIndex,
int64_t startFrame, int64_t durationFrames)
{
    auto asset = m_mediaPool->getAssetById(assetId);

    if (!asset) {
        LOG_ERROR("Cannot add clip: Asset ID " + assetId + " not found in Media
Pool."); return false;
    }

    std::string clipId = assetId + "_" + std::to_string(startFrame);
    auto toatlFrame = asset->getTotalFrames();
    auto clip = std::make_shared<VideoClip>(
asset,clipId,assetId,startFrame,startFrame + durationFrames,trackIndex,0);

    //  HECK THE RESULT
    bool success = m_timeline->addClip(trackIndex,clip);

    if (success) {
        LOG_INFO("Clip added to Track: " + clipId);
    } else {
        LOG_ERROR("Failed to add clip! Does track " + std::to_string(trackIndex)
+ " exist?");
    }

    return success;
} */

int Compositor::addTrack(std::string TrackName) {
  if (!m_timeline->addVideoTrack(TrackName)) {
    throw std::runtime_error("unable to create track with name: " + TrackName);
  }

  int index = m_timeline->getTrackIndexByName(TrackName);

  return index;
}
void Compositor::initSkiaSurfaces() {
  const auto &images = m_renderer->getSwapchainImages();
  auto extent = m_renderer->getSwapchainExtent();
  VkFormat format = m_renderer->getSwapchain()->getImageFormat();
  GrDirectContext *grCtx = m_skiaContext->getDirectContext();

  LOG_INFO("[initSkiaSurfaces] images="
           << images.size() << " extent=" << extent.width << "x"
           << extent.height << " format=" << format
           << " grCtx=" << (grCtx ? "OK" : "NULL"));

  if (grCtx) {
    LOG_INFO("[initSkiaSurfaces] grCtx->abandoned()=" << grCtx->abandoned());
  }

  m_SkiaSurface.resize(images.size());
  for (size_t i = 0; i < images.size(); i++) {
    GrVkImageInfo imageInfo{};
    imageInfo.fImage = images[i];
    imageInfo.fImageTiling = VK_IMAGE_TILING_OPTIMAL;
    imageInfo.fImageLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    imageInfo.fFormat = format;
    imageInfo.fImageUsageFlags =
        m_renderer->getSwapchain()->getImageUsageFlags();
    imageInfo.fSampleCount = 1;
    imageInfo.fLevelCount = 1;
    GrBackendRenderTarget backendRT = GrBackendRenderTargets::MakeVk(
        (int)extent.width, (int)extent.height, imageInfo);
    SkColorType colorType = (format == VK_FORMAT_B8G8R8A8_UNORM)
                                ? kBGRA_8888_SkColorType
                                : kRGBA_8888_SkColorType;

    m_SkiaSurface[i] = SkSurfaces::WrapBackendRenderTarget(
        grCtx, backendRT, kTopLeft_GrSurfaceOrigin, colorType, nullptr,
        nullptr);
    if (!m_SkiaSurface[i]) {
      LOG_WARN("[initSkiaSurfaces] WrapBackendRenderTarget FAILED for image "
               << i << " (image=" << images[i]
               << ", backendRT.isValid=" << backendRT.isValid() << ")");

      if (i == 0) {
        SkImageInfo info =
            SkImageInfo::Make((int)extent.width, (int)extent.height, colorType,
                              kPremul_SkAlphaType);
        sk_sp<SkSurface> ownedSurface =
            SkSurfaces::RenderTarget(grCtx, skgpu::Budgeted::kNo, info);
        LOG_WARN("[initSkiaSurfaces] DIAGNOSTIC: Skia-owned RenderTarget "
                 "(no VkImage wrap) = "
                 << (ownedSurface ? "OK" : "FAILED"));

        if (ownedSurface) {
          GrBackendRenderTarget ownedRT = SkSurfaces::GetBackendRenderTarget(
              ownedSurface.get(), SkSurfaces::BackendHandleAccess::kFlushRead);
          LOG_WARN("[initSkiaSurfaces] DIAGNOSTIC 3: ownedRT.isValid()="
                   << ownedRT.isValid());
          sk_sp<SkSurface> roundTripSurface =
              SkSurfaces::WrapBackendRenderTarget(grCtx, ownedRT,
                                                  kTopLeft_GrSurfaceOrigin,
                                                  colorType, nullptr, nullptr);
          LOG_WARN("[initSkiaSurfaces] DIAGNOSTIC 3: round-trip wrap of "
                   "Skia's OWN render target = "
                   << (roundTripSurface ? "OK" : "FAILED"));
        }

        VkDevice dev = m_context->getLogicalDevice();
        VkImageCreateInfo imgCI{};
        imgCI.sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO;
        imgCI.imageType = VK_IMAGE_TYPE_2D;
        imgCI.format = format;
        imgCI.extent = {64, 64, 1};
        imgCI.mipLevels = 1;
        imgCI.arrayLayers = 1;
        imgCI.samples = VK_SAMPLE_COUNT_1_BIT;
        imgCI.tiling = VK_IMAGE_TILING_OPTIMAL;
        imgCI.usage =
            VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | VK_IMAGE_USAGE_SAMPLED_BIT |
            VK_IMAGE_USAGE_TRANSFER_SRC_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT;
        imgCI.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
        imgCI.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;

        VkImage testImage = VK_NULL_HANDLE;
        VkDeviceMemory testMemory = VK_NULL_HANDLE;
        if (vkCreateImage(dev, &imgCI, nullptr, &testImage) == VK_SUCCESS) {
          VkMemoryRequirements memReq{};
          vkGetImageMemoryRequirements(dev, testImage, &memReq);

          VkPhysicalDeviceMemoryProperties memProps{};
          vkGetPhysicalDeviceMemoryProperties(m_context->getPhysicalDevice(),
                                              &memProps);

          uint32_t memTypeIndex = UINT32_MAX;
          for (uint32_t t = 0; t < memProps.memoryTypeCount; ++t) {
            if (memReq.memoryTypeBits & (1u << t)) {
              memTypeIndex = t;
              break;
            }
          }

          VkMemoryAllocateInfo allocInfo{};
          allocInfo.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
          allocInfo.allocationSize = memReq.size;
          allocInfo.memoryTypeIndex = memTypeIndex;

          if (memTypeIndex != UINT32_MAX &&
              vkAllocateMemory(dev, &allocInfo, nullptr, &testMemory) ==
                  VK_SUCCESS &&
              vkBindImageMemory(dev, testImage, testMemory, 0) == VK_SUCCESS) {
            GrVkImageInfo testInfo{};
            testInfo.fImage = testImage;
            testInfo.fImageTiling = VK_IMAGE_TILING_OPTIMAL;
            testInfo.fImageLayout = VK_IMAGE_LAYOUT_UNDEFINED;
            testInfo.fFormat = format;
            testInfo.fImageUsageFlags = VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT |
                                        VK_IMAGE_USAGE_SAMPLED_BIT |
                                        VK_IMAGE_USAGE_TRANSFER_SRC_BIT |
                                        VK_IMAGE_USAGE_TRANSFER_DST_BIT;
            testInfo.fSampleCount = 1;
            testInfo.fLevelCount = 1;

            GrBackendRenderTarget testRT =
                GrBackendRenderTargets::MakeVk(64, 64, testInfo);
            sk_sp<SkSurface> testSurface = SkSurfaces::WrapBackendRenderTarget(
                grCtx, testRT, kTopLeft_GrSurfaceOrigin, colorType, nullptr,
                nullptr);
            LOG_WARN("[initSkiaSurfaces] DIAGNOSTIC 2: wrap of a MANUALLY "
                     "created external VkImage = "
                     << (testSurface ? "OK" : "FAILED"));
            testSurface.reset();
          } else {
            LOG_WARN("[initSkiaSurfaces] DIAGNOSTIC 2: failed to allocate/"
                     "bind memory for manual test image");
          }

          vkDestroyImage(dev, testImage, nullptr);
          if (testMemory != VK_NULL_HANDLE)
            vkFreeMemory(dev, testMemory, nullptr);
        } else {
          LOG_WARN("[initSkiaSurfaces] DIAGNOSTIC 2: vkCreateImage FAILED for "
                   "manual test image");
        }
      }
    }
  }
}

VkImageView Compositor::createHardwarePlaneView(VkImage image,
                                                VkImageAspectFlagBits aspect,
                                                VkFormat format) {
  VkImageViewUsageCreateInfo usageInfo{};
  usageInfo.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_USAGE_CREATE_INFO;
  usageInfo.usage = VK_IMAGE_USAGE_SAMPLED_BIT;

  VkImageViewCreateInfo viewInfo{};
  viewInfo.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO;
  viewInfo.pNext = &usageInfo;
  viewInfo.image = image;
  viewInfo.viewType = VK_IMAGE_VIEW_TYPE_2D;
  viewInfo.format = format;

  viewInfo.subresourceRange.aspectMask = aspect;
  viewInfo.subresourceRange.baseMipLevel = 0;
  viewInfo.subresourceRange.levelCount = 1;
  viewInfo.subresourceRange.baseArrayLayer = 0;
  viewInfo.subresourceRange.layerCount = 1;

  VkImageView imageView;
  if (vkCreateImageView(m_context->getLogicalDevice(), &viewInfo, nullptr,
                        &imageView) != VK_SUCCESS) {
    LOG_ERROR("Failed to create ImageView for Hardware Frame!");
    return VK_NULL_HANDLE;
  }
  return imageView;
}
sk_sp<SkImage> Compositor::wrapRGBAToSkImage(const Texture &tex) {

  GrDirectContext *grCtx = m_skiaContext->getDirectContext();

  if (!grCtx) {
    return nullptr;
  }

  GrVkImageInfo info{};
  info.fImage = tex.getImage();
  info.fAlloc.fMemory = tex.getImageMemory();
  info.fAlloc.fOffset = 0;
  info.fAlloc.fSize = tex.getImageSize();
  info.fAlloc.fFlags = 0;
  info.fImageTiling = VK_IMAGE_TILING_OPTIMAL;
  info.fImageLayout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;
  info.fFormat = tex.getFormat(); // R8G8B8A8_UNORM
  info.fImageUsageFlags = VK_IMAGE_USAGE_SAMPLED_BIT |
                          VK_IMAGE_USAGE_TRANSFER_DST_BIT |
                          VK_IMAGE_USAGE_TRANSFER_SRC_BIT;
  info.fSampleCount = 1;
  info.fLevelCount = 1;
  info.fCurrentQueueFamily = VK_QUEUE_FAMILY_IGNORED;
  info.fProtected = skgpu::Protected::kNo;
  info.fSharingMode = VK_SHARING_MODE_EXCLUSIVE;

  GrBackendTexture backTex =
      GrBackendTextures::MakeVk(tex.getWidth(), tex.getHeight(), info);
  auto img = SkImages::BorrowTextureFrom(
      grCtx, backTex, kTopLeft_GrSurfaceOrigin, kRGBA_8888_SkColorType,
      kPremul_SkAlphaType, nullptr);
  if (!img) {
    LOG_WARN("[wrapRGBAToSkImage] BorrowTextureFrom returned null! w=" +
             std::to_string(tex.getWidth()) +
             " h=" + std::to_string(tex.getHeight()) +
             " format=" + std::to_string(tex.getFormat()) +
             " backTex.isValid=" + std::to_string(backTex.isValid()));
  }
  return img;
};

sk_sp<SkImage>
Compositor::renderSelectedCharsOffscreen(GrDirectContext *grCtx,
                                         SkCanvas *refCanvas, TextClip *clip,
                                         const std::string &selectorId) {

  if (!grCtx || !clip)
    return nullptr;

  auto info = SkImageInfo::Make(refCanvas->imageInfo().width(),
                                refCanvas->imageInfo().height(),
                                kRGBA_8888_SkColorType, kPremul_SkAlphaType);
  auto surf = SkSurfaces::RenderTarget(grCtx, skgpu::Budgeted::kYes, info);
  if (!surf)
    return nullptr;

  SkCanvas *oc = surf->getCanvas();
  oc->clear(SK_ColorTRANSPARENT);

  oc->setMatrix(refCanvas->getTotalMatrix());

  const std::vector<float> influence =
      clip->getMaskSelectorInfluence(selectorId, 0);

  const TextPushConstants &pc = clip->getPushConstants();
  const std::string &text = clip->getCurrentText();
  const TextLayoutSettings &layout = clip->getLayout();
  FontAtlas *atlas = clip->getFontAtlas();
  float fontSize = layout.fontSize;
  float baseOpacity = pc.opacity;
  glm::vec4 baseColor = pc.textColor;

  const auto &perCharStates = clip->getPerCharStates();

  sk_sp<SkTypeface> tf = getSkiaTypeface(clip->getFontName());

  // Apply clip model transform
  oc->save();
  SkM44 skModel(pc.model[0][0], pc.model[1][0], pc.model[2][0], pc.model[3][0],
                pc.model[0][1], pc.model[1][1], pc.model[2][1], pc.model[3][1],
                pc.model[0][2], pc.model[1][2], pc.model[2][2], pc.model[3][2],
                pc.model[0][3], pc.model[1][3], pc.model[2][3], pc.model[3][3]);
  oc->concat(skModel);

  float cursorX = 0.f;
  float cursorY = 0.f;
  float lineDrop = fontSize * layout.leading * 1.2f;
  if (atlas)
    lineDrop = atlas->getLineHeight() * fontSize * layout.leading;

  int charIdx = 0;

  for (char c : text) {
    if (c == '\n') {
      cursorX = 0.f;
      cursorY += lineDrop;
      continue;
    }

    PerCharacterState state;
    if (charIdx < (int)perCharStates.size())
      state = perCharStates[charIdx];

    // Space advance â€” mirror drawText exactly (
    if (c == ' ') {
      float spaceAdv = fontSize * 0.33f + layout.wordSpacing;
      if (atlas) {
        const GlyphMetrics *sg = atlas->getGlyph(static_cast<uint32_t>(' '));
        if (sg)
          spaceAdv = sg->advance * fontSize + layout.wordSpacing;
      }
      cursorX += spaceAdv;
      continue;
    }

    // Glyph advance (same formula as drawText, including trackingExtra)
    float advance = fontSize * 0.6f + layout.tracking;
    if (atlas) {
      const GlyphMetrics *gm = atlas->getGlyph(static_cast<uint32_t>(c));
      if (gm)
        advance =
            gm->advance * fontSize + layout.tracking + state.trackingExtra;
    }

    float inf = (charIdx < (int)influence.size()) ? influence[charIdx] : 0.f;

    if (inf > 0.001f) {
      float pivotX = cursorX + advance * 0.5f;
      float pivotY = cursorY;

      oc->save();

      oc->translate(pivotX + state.positionOffset.x,
                    pivotY + state.positionOffset.y);

      if (std::abs(state.rotationDeg) > 0.001f)
        oc->rotate(state.rotationDeg);

      if (std::abs(state.scale.x - 1.f) > 0.001f ||
          std::abs(state.scale.y - 1.f) > 0.001f)
        oc->scale(state.scale.x, state.scale.y);

      // 4. Skew
      if (std::abs(state.skewDeg) > 0.001f)
        oc->skew(std::tan(glm::radians(state.skewDeg)), 0.f);

      glm::vec4 charColor = glm::clamp(baseColor * state.colorMultiplier,
                                       glm::vec4(0.f), glm::vec4(1.f));
      float charOpacity =
          glm::clamp(baseOpacity * state.opacity * inf, 0.f, 1.f);

      SkFont skFont(tf, fontSize);
      skFont.setEdging(SkFont::Edging::kAntiAlias);

      SkPaint fillPaint;
      fillPaint.setAntiAlias(true);
      fillPaint.setColor(SkColorSetARGB(
          static_cast<uint8_t>(charColor.a * charOpacity * 255.f),
          static_cast<uint8_t>(charColor.r * 255.f),
          static_cast<uint8_t>(charColor.g * 255.f),
          static_cast<uint8_t>(charColor.b * 255.f)));

      // Per-char blur from animator
      float charBlur = pc.edgeSoftness + state.blur;
      if (charBlur > 0.f)
        fillPaint.setMaskFilter(
            SkMaskFilter::MakeBlur(kNormal_SkBlurStyle, charBlur));

      char buf[2] = {c, '\0'};
      oc->drawString(buf, -advance * 0.5f, 0.f, skFont, fillPaint);

      if (pc.strokeWidth > 0.f) {
        SkPaint sp;
        sp.setStyle(SkPaint::kStroke_Style);
        sp.setStrokeWidth(pc.strokeWidth);
        sp.setAntiAlias(true);
        sp.setColor(SkColorSetARGB(
            static_cast<uint8_t>(
                glm::clamp(pc.strokeColor.a * charOpacity, 0.f, 1.f) * 255.f),
            static_cast<uint8_t>(glm::clamp(pc.strokeColor.r, 0.f, 1.f) *
                                 255.f),
            static_cast<uint8_t>(glm::clamp(pc.strokeColor.g, 0.f, 1.f) *
                                 255.f),
            static_cast<uint8_t>(glm::clamp(pc.strokeColor.b, 0.f, 1.f) *
                                 255.f)));
        oc->drawString(buf, -advance * 0.5f, 0.f, skFont, sp);
      }

      oc->restore();
    }

    cursorX += advance;
    ++charIdx;
  }

  oc->restore();
  return surf->makeImageSnapshot();
}
