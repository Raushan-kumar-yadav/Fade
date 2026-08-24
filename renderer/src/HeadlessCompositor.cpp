#include "HeadlessCompositor.hpp"
#include "core/api/Logger.hpp"
#include "engine/SchedulerBridge.hpp"
#include "napi/FrameDescriptor.hpp"
#include "rendering/DrawPen.hpp"
#include "rendering/DrawShape.hpp"
#include "rendering/DrawSvg.hpp"
#include "rendering/DrawText.hpp"

#include <core/SkBlendMode.h>
#include <core/SkCanvas.h>
#include <core/SkColorSpace.h>
#include <core/SkData.h>
#include <core/SkImage.h>
#include <core/SkM44.h>
#include <core/SkPaint.h>
#include <core/SkRect.h>
#include <core/SkSamplingOptions.h>
#include <cstdint>
#include <effects/SkRuntimeEffect.h>
#include <fstream>
#include <gpu/ganesh/GrDirectContext.h>
#include <gpu/ganesh/SkSurfaceGanesh.h>
#include <mutex>
#include <vector>

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>

#include <chrono>
#include <iostream>
#include <stdexcept>
#include <thread>

#ifndef LOG_INFO
#define LOG_INFO(m) std::cout << "[HeadlessCompositor] " << m << "\n"
#endif
#ifndef LOG_ERROR
#define LOG_ERROR(m) std::cerr << "[HeadlessCompositor][ERR] " << m << "\n"
#endif

//   Constructor

HeadlessCompositor::HeadlessCompositor(int width, int height, float fps,
                                       const std::string &effectsDir)
    : m_width(width), m_height(height), m_fps(fps), m_skslDir(effectsDir) {
  init(effectsDir);
}

HeadlessCompositor::~HeadlessCompositor() { shutdown(); }

void HeadlessCompositor::init(const std::string &effectsDir) {
  //  Vulkan device
  m_device = std::make_unique<DeviceContext>();
  if (!m_device->init())
    throw std::runtime_error(
        "HeadlessCompositor: DeviceContext::init() failed");

  //  Skia GPU context on top of Vulkan
  m_skia = std::make_unique<SkiaContext>(m_device.get());
  if (!m_skia->getDirectContext())
    throw std::runtime_error("HeadlessCompositor: SkiaContext init failed");

  //   Offscreen SkSurface backed
  SkImageInfo info =
      SkImageInfo::MakeN32Premul(m_width, m_height, SkColorSpace::MakeSRGB());
  m_surface = SkSurfaces::RenderTarget(m_skia->getDirectContext(),
                                       skgpu::Budgeted::kYes, info);
  if (!m_surface)
    throw std::runtime_error("HeadlessCompositor: SkSurface creation failed");

  //  Allocate front buffer
  m_bufferSize = static_cast<size_t>(m_width) * m_height * 4;
  m_buffer = std::make_unique<uint8_t[]>(m_bufferSize);
  std::memset(m_buffer.get(), 0, m_bufferSize);
  // Back buffer
  m_renderBuffer = std::make_unique<uint8_t[]>(m_bufferSize);
  std::memset(m_renderBuffer.get(), 0, m_bufferSize);

  schedSetDeviceContext(m_device.get());

  LOG_INFO("Initialized " << m_width << "x" << m_height << " @ " << m_fps
                          << "fps");
}

void HeadlessCompositor::shutdown() {
  // Stop play thread FIRST
  m_playing.store(false);
  if (m_playThread.joinable())
    m_playThread.join();

  // Flush all in-flight
  if (m_skia && m_skia->getDirectContext()) {
    m_skia->getDirectContext()->flushAndSubmit();
  }
  m_decoders.clear();
  m_surface.reset();
  m_skia.reset();
  m_device.reset();
  closeTcp();
}

// renderComp
// recursion.
sk_sp<SkImage>
HeadlessCompositor::renderComp(const ClipDesc &clip, int64_t frame,
                               std::unordered_set<std::string> &ancestorStack) {
  const std::string &compId = clip.comp.compId;

  // Cycle detection
  if (ancestorStack.count(compId)) {
    LOG_ERROR("[Comp] Cycle detected for compId=" + compId +
              " — returning red error frame");
    SkImageInfo errInfo =
        SkImageInfo::MakeN32Premul(m_width, m_height, SkColorSpace::MakeSRGB());
    auto errSurf = SkSurfaces::RenderTarget(m_skia->getDirectContext(),
                                            skgpu::Budgeted::kYes, errInfo);
    if (!errSurf)
      return nullptr;
    errSurf->getCanvas()->clear(SkColorSetARGB(255, 200, 30, 30));
    return errSurf->makeImageSnapshot();
  }

  if (!clip.comp.innerFd) {
    LOG_ERROR("[Comp] No innerFd for compId=" + compId);
    return nullptr;
  }

  ancestorStack.insert(compId);

  // Create offscreen surface for this comp
  SkImageInfo info =
      SkImageInfo::MakeN32Premul(m_width, m_height, SkColorSpace::MakeSRGB());
  auto compSurf = SkSurfaces::RenderTarget(m_skia->getDirectContext(),
                                           skgpu::Budgeted::kYes, info);
  if (!compSurf) {
    ancestorStack.erase(compId);
    return nullptr;
  }

  SkCanvas *compCanvas = compSurf->getCanvas();
  compCanvas->clear(SK_ColorTRANSPARENT);

  // Render each inner clip onto compCanvas
  const FrameDescriptor &innerFd = *clip.comp.innerFd;
  for (const auto &innerClip : innerFd.clips) {
    if (innerClip.type == ClipDesc::Type::Solid) {
      SkPaint p;
      p.setColor4f({innerClip.solidR, innerClip.solidG, innerClip.solidB,
                    innerClip.solidA});
      p.setAlphaf(innerClip.opacity);
      compCanvas->drawRect(SkRect::MakeWH(m_width, m_height), p);
      continue;
    }
    if (innerClip.type == ClipDesc::Type::Text) {
      fade::drawing::drawText(compCanvas, innerClip, m_width, m_height);
      continue;
    }
    if (innerClip.type == ClipDesc::Type::Shape) {
      fade::drawing::drawShape(compCanvas, innerClip, m_width, m_height);
      continue;
    }
    if (innerClip.type == ClipDesc::Type::Pen) {
      fade::drawing::drawPen(compCanvas, innerClip, m_width, m_height);
      continue;
    }
    if (innerClip.type == ClipDesc::Type::Svg) {
      fade::drawing::drawSvg(compCanvas, innerClip, m_width, m_height);
      continue;
    }
    // Recursive nested composition
    if (innerClip.type == ClipDesc::Type::Comp) {
      auto nestedImg = renderComp(innerClip, innerFd.frame, ancestorStack);
      if (nestedImg) {
        SkPaint p;
        p.setAlphaf(innerClip.opacity);
        auto img = innerClip.effects.empty()
                       ? nestedImg
                       : applyEffects(nestedImg, innerClip, innerFd.frame);
        compCanvas->drawImageRect(img,
                                  SkRect::MakeWH(static_cast<float>(m_width),
                                                 static_cast<float>(m_height)),
                                  SkSamplingOptions(SkFilterMode::kLinear), &p);
      }
      continue;
    }
    // Video / Image
    if (innerClip.file.empty())
      continue;

    CachedFrameData cfd =
        tryGetCachedFrame(innerClip.file, innerClip.sourceFrame);
    std::vector<uint8_t> rgba;
    int imgW = 0, imgH = 0;
    if (cfd.valid) {
      rgba.assign(cfd.data, cfd.data + cfd.dataSize);
      imgW = static_cast<int>(cfd.width);
      imgH = static_cast<int>(cfd.height);
      releaseCachedFrame(cfd);
    } else {
      auto &dec = m_decoders[innerClip.file];
      if (!dec)
        dec =
            std::make_unique<ClipDecoder>(innerClip.file, m_device.get(), 1.0f);
      auto res = dec->decodeFrame(innerClip.sourceFrame);
      rgba = std::move(res.rgba);
      imgW = res.width;
      imgH = res.height;
    }
    if (!rgba.empty())
      drawClipOnCanvas(compCanvas, innerClip, rgba.data(), imgW, imgH,
                       /*useGpu=*/true, innerFd.frame);
  }

  // Flush the composition surface before snapshotting
  m_skia->getDirectContext()->flushAndSubmit();

  ancestorStack.erase(compId);

  sk_sp<SkImage> result = compSurf->makeImageSnapshot();
  LOG_INFO("[Comp] Rendered compId=" + compId +
           " frame=" + std::to_string(innerFd.frame));
  return result;
}

//   Render entry

void HeadlessCompositor::renderFrame(const FrameDescriptor &fd) {
  if (!fd.valid || !m_surface)
    return;
  std::lock_guard<std::mutex> lock(m_renderMutex);
  doRender(fd);
}

void HeadlessCompositor::doRender(const FrameDescriptor &fd) {

  // ULTRA-FAST PATH

  if (fd.clips.size() == 1) {
    const auto &clip = fd.clips[0];
    const bool isGenerative = (clip.type == ClipDesc::Type::Solid ||
                               clip.type == ClipDesc::Type::Text ||
                               clip.type == ClipDesc::Type::Shape ||
                               clip.type == ClipDesc::Type::Pen);
    if (!isGenerative && clip.effects.empty()) {
      const auto &t = clip.transform;
      bool isIdentity =
          (t.x == 0 && t.y == 0 && t.rotation == 0 && t.scaleX == 1.0f &&
           t.scaleY == 1.0f && clip.opacity >= 0.99f && clip.blendMode == 0);
      if (isIdentity) {
        //  Try scheduler cache first
        CachedFrameData cfd = tryGetCachedFrame(clip.file, clip.sourceFrame);
        if (cfd.valid && (int)cfd.width == m_width &&
            (int)cfd.height == m_height) {
          // Dimensions match project
          std::memcpy(m_renderBuffer.get(), cfd.data, m_bufferSize);
          std::memcpy(m_buffer.get(), m_renderBuffer.get(), m_bufferSize);
          releaseCachedFrame(cfd);
          if (m_onFrameReady)
            m_onFrameReady(fd.frame);
          return;
        }
        if (cfd.valid)
          releaseCachedFrame(cfd);

        //  Cache miss
        auto &decoder = m_decoders[clip.file];
        if (!decoder)
          decoder =
              std::make_unique<ClipDecoder>(clip.file, m_device.get(), 1.0f);

        // Direct decode
        if (decoder->decodeFrameDirect(clip.sourceFrame, m_renderBuffer.get(),
                                       m_width, m_height)) {
          // Flip
          std::memcpy(m_buffer.get(), m_renderBuffer.get(), m_bufferSize);
          if (m_onFrameReady)
            m_onFrameReady(fd.frame);
          return;
        }
      }
    }
  }

  //   Standard path
  bool needsGpu = false;
  struct ClipPixels {
    const ClipDesc *clip;
    std::vector<uint8_t> rgba;
    int imgW;
    int imgH;
  };
  std::vector<ClipPixels> decoded;

  for (const auto &clip : fd.clips) {
    // Skip video/image
    if (clip.type == ClipDesc::Type::Solid ||
        clip.type == ClipDesc::Type::Text ||
        clip.type == ClipDesc::Type::Shape ||
        clip.type == ClipDesc::Type::Pen || clip.type == ClipDesc::Type::Svg ||
        clip.type == ClipDesc::Type::Comp) {
      decoded.push_back({&clip, {}, 0, 0});
      continue;
    }
    // Safety
    if (clip.file.empty()) {
      decoded.push_back({&clip, {}, 0, 0});
      continue;
    }

    // Try scheduler cache first
    CachedFrameData cfd = tryGetCachedFrame(clip.file, clip.sourceFrame);
    if (cfd.valid) {
      if (!clip.effects.empty())
        needsGpu = true;
      //  cached RGBA data into a local vector
      std::vector<uint8_t> rgbaCopy(cfd.data, cfd.data + cfd.dataSize);
      decoded.push_back(
          {&clip, std::move(rgbaCopy), (int)cfd.width, (int)cfd.height});
      releaseCachedFrame(cfd);
      continue;
    }

    //   Cache miss
    auto &decoder = m_decoders[clip.file];
    if (!decoder)
      decoder = std::make_unique<ClipDecoder>(clip.file, m_device.get(), 1.0f);

    auto result = decoder->decodeFrame(clip.sourceFrame);
    if (!clip.effects.empty())
      needsGpu = true;
    decoded.push_back(
        {&clip, std::move(result.rgba), result.width, result.height});
  }

  // Any generative clip
  for (const auto &cp : decoded) {
    if (!cp.clip->effects.empty()) {
      needsGpu = true;
      break;
    }
  }

  if (decoded.size() > 1)
    needsGpu = true;

  if (!needsGpu) {

    SkImageInfo cpuInfo = SkImageInfo::MakeN32Premul(m_width, m_height);
    auto cpuSurface = SkSurfaces::Raster(cpuInfo);

    if (cpuSurface) {
      SkCanvas *canvas = cpuSurface->getCanvas();
      canvas->clear(SK_ColorBLACK);

      for (const auto &cp : decoded) {
        if (cp.clip->type == ClipDesc::Type::Solid) {
          SkPaint p;
          p.setColor4f({cp.clip->solidR, cp.clip->solidG, cp.clip->solidB,
                        cp.clip->solidA});
          p.setAlphaf(cp.clip->opacity);
          canvas->drawRect(SkRect::MakeWH(m_width, m_height), p);
          continue;
        }
        if (cp.clip->type == ClipDesc::Type::Text) {
          fade::drawing::drawText(canvas, *cp.clip, m_width, m_height);
          continue;
        }
        if (cp.clip->type == ClipDesc::Type::Shape) {
          fade::drawing::drawShape(canvas, *cp.clip, m_width, m_height);
          continue;
        }
        if (cp.clip->type == ClipDesc::Type::Pen) {
          fade::drawing::drawPen(canvas, *cp.clip, m_width, m_height);
          continue;
        }
        if (cp.clip->type == ClipDesc::Type::Svg) {
          fade::drawing::drawSvg(canvas, *cp.clip, m_width, m_height);
          continue;
        }
        if (cp.rgba.empty())
          continue;
        drawClipOnCanvas(canvas, *cp.clip, cp.rgba.data(), cp.imgW, cp.imgH,
                         /*useGpu=*/false);
      }

      // Read composed frame from Raster surface
      SkImageInfo readInfo = SkImageInfo::Make(
          m_width, m_height, kRGBA_8888_SkColorType, kOpaque_SkAlphaType);
      cpuSurface->readPixels(readInfo, m_renderBuffer.get(),
                             static_cast<size_t>(m_width) * 4, 0, 0);
      // cpuSurface destructs here
    }
    std::memcpy(m_buffer.get(), m_renderBuffer.get(), m_bufferSize);
    if (m_onFrameReady)
      m_onFrameReady(fd.frame);
    return;
  }

  //   GPU path
  m_gpuKeepAliveSurfaces.clear();
  m_gpuKeepAliveImages.clear();
  SkCanvas *canvas = m_surface->getCanvas();
  canvas->clear(SK_ColorBLACK);

  std::string transClipA, transClipB;
  if (fd.transition.valid) {
    transClipA = fd.transition.clipA_id;
    transClipB = fd.transition.clipB_id;
  }

  // Helper
  auto clipToImage = [&](const ClipPixels &cp) -> sk_sp<SkImage> {
    const ClipDesc &cl = *cp.clip;
    const bool isGenerative =
        (cl.type == ClipDesc::Type::Solid || cl.type == ClipDesc::Type::Text ||
         cl.type == ClipDesc::Type::Shape || cl.type == ClipDesc::Type::Pen ||
         cl.type == ClipDesc::Type::Svg);
    if (isGenerative)
      return renderGenerativeToImage(cl);
    if (cp.rgba.empty())
      return nullptr;
    const size_t rowBytes =
        static_cast<size_t>(cp.imgW > 0 ? cp.imgW : m_width) * 4;
    const size_t dataBytes = rowBytes * (cp.imgH > 0 ? cp.imgH : m_height);
    SkImageInfo ii = SkImageInfo::Make(
        cp.imgW > 0 ? cp.imgW : m_width, cp.imgH > 0 ? cp.imgH : m_height,
        kRGBA_8888_SkColorType, kPremul_SkAlphaType, SkColorSpace::MakeSRGB());
    sk_sp<SkData> px = SkData::MakeWithCopy(cp.rgba.data(), dataBytes);
    return SkImages::RasterFromData(ii, px, rowBytes);
  };

  // Normal per-clip draw
  for (const auto &cp : decoded) {
    const ClipDesc &cl = *cp.clip;
    if (fd.transition.valid &&
        (cl.clipId == transClipA || cl.clipId == transClipB))
      continue;

    const bool hasEffects = !cl.effects.empty();
    const bool isGenerative =
        (cl.type == ClipDesc::Type::Solid || cl.type == ClipDesc::Type::Text ||
         cl.type == ClipDesc::Type::Shape || cl.type == ClipDesc::Type::Pen ||
         cl.type == ClipDesc::Type::Svg);

    if (isGenerative && hasEffects) {
      auto genImg = renderGenerativeToImage(cl);
      if (genImg) {
        genImg = applyEffects(genImg, cl, fd.frame);
        SkPaint p;
        p.setAlphaf(cl.opacity);
        canvas->drawImage(genImg, 0, 0,
                          SkSamplingOptions(SkFilterMode::kLinear), &p);
      }
      continue;
    }

    if (cl.type == ClipDesc::Type::Solid) {
      SkPaint p;
      p.setColor4f({cl.solidR, cl.solidG, cl.solidB, cl.solidA});
      p.setAlphaf(cl.opacity);
      canvas->drawRect(SkRect::MakeWH(m_width, m_height), p);
      continue;
    }
    if (cl.type == ClipDesc::Type::Text) {
      fade::drawing::drawText(canvas, cl, m_width, m_height);
      continue;
    }
    if (cl.type == ClipDesc::Type::Shape) {
      fade::drawing::drawShape(canvas, cl, m_width, m_height);
      continue;
    }
    if (cl.type == ClipDesc::Type::Pen) {
      fade::drawing::drawPen(canvas, cl, m_width, m_height);
      continue;
    }
    if (cl.type == ClipDesc::Type::Svg) {
      fade::drawing::drawSvg(canvas, cl, m_width, m_height);
      continue;
    }
    // Nested composition
    if (cl.type == ClipDesc::Type::Comp) {
      std::unordered_set<std::string> ancestors;
      auto compImg = renderComp(cl, fd.frame, ancestors);
      if (compImg) {
        SkPaint p;
        p.setAlphaf(cl.opacity);
        auto img =
            cl.effects.empty() ? compImg : applyEffects(compImg, cl, fd.frame);
        canvas->drawImageRect(img,
                              SkRect::MakeWH(static_cast<float>(m_width),
                                             static_cast<float>(m_height)),
                              SkSamplingOptions(SkFilterMode::kLinear), &p);
      }
      continue;
    }
    if (cp.rgba.empty())
      continue;
    drawClipOnCanvas(canvas, cl, cp.rgba.data(), cp.imgW, cp.imgH,
                     /*useGpu=*/true, fd.frame);
  }

  //   Transition blend
  if (fd.transition.valid) {
    std::cerr << "[TRANS] BEGIN transition clipA=" << transClipA
              << " clipB=" << transClipB
              << " progress=" << fd.transition.progress << "\n";
    const ClipPixels *dpA = nullptr;
    const ClipPixels *dpB = nullptr;
    for (const auto &dp : decoded) {
      if (dp.clip->clipId == transClipA)
        dpA = &dp;
      if (dp.clip->clipId == transClipB)
        dpB = &dp;
    }
    std::cerr << "[TRANS] dpA=" << (dpA ? "found" : "NULL")
              << " dpB=" << (dpB ? "found" : "NULL") << "\n";
    if (dpA && dpB) {
      std::cerr << "[TRANS] clipToImage(A)...\n";
      sk_sp<SkImage> imgA = clipToImage(*dpA);
      std::cerr << "[TRANS] clipToImage(A) done: " << (imgA ? "OK" : "NULL")
                << (imgA ? (" " + std::to_string(imgA->width()) + "x" +
                            std::to_string(imgA->height()))
                         : "")
                << "\n";
      std::cerr << "[TRANS] clipToImage(B)...\n";
      sk_sp<SkImage> imgB = clipToImage(*dpB);
      std::cerr << "[TRANS] clipToImage(B) done: " << (imgB ? "OK" : "NULL")
                << (imgB ? (" " + std::to_string(imgB->width()) + "x" +
                            std::to_string(imgB->height()))
                         : "")
                << "\n";

      // Apply per-clip effects before blending
      if (imgA && !dpA->clip->effects.empty()) {
        std::cerr << "[TRANS] applyEffects(A)...\n";
        imgA = applyEffects(imgA, *dpA->clip, fd.frame);
        std::cerr << "[TRANS] applyEffects(A) done\n";
      }
      if (imgB && !dpB->clip->effects.empty()) {
        std::cerr << "[TRANS] applyEffects(B)...\n";
        imgB = applyEffects(imgB, *dpB->clip, fd.frame);
        std::cerr << "[TRANS] applyEffects(B) done\n";
      }

      std::cerr << "[TRANS] applyTransition()...\n";
      sk_sp<SkImage> blended = applyTransition(imgA, imgB, fd.transition);
      std::cerr << "[TRANS] applyTransition done: " << (blended ? "OK" : "NULL")
                << "\n";
      if (blended) {
        SkPaint p;
        std::cerr << "[TRANS] drawImage blended...\n";

        const float cw = static_cast<float>(m_width);
        const float ch = static_cast<float>(m_height);
        canvas->drawImageRect(blended, SkRect::MakeWH(cw, ch),
                              SkSamplingOptions(SkFilterMode::kLinear), &p);
        std::cerr << "[TRANS] drawImage blended done\n";
      }
    }
    std::cerr << "[TRANS] END transition block\n";
  }

  // GPU sync
  std::cerr << "[RENDER] final flushAndSubmit (sync)...\n";
  m_skia->getDirectContext()->flushAndSubmit(GrSyncCpu::kYes); // SYNC

  // NOW safe
  m_gpuKeepAliveSurfaces.clear();
  m_gpuKeepAliveImages.clear();

  std::cerr << "[RENDER] readPixels...\n";
  SkImageInfo readInfo = SkImageInfo::Make(
      m_width, m_height, kRGBA_8888_SkColorType, kOpaque_SkAlphaType);
  bool ok = m_surface->readPixels(readInfo, m_renderBuffer.get(),
                                  static_cast<size_t>(m_width) * 4, 0, 0);
  std::cerr << "[RENDER] readPixels: " << (ok ? "OK" : "FAILED") << "\n";
  if (!ok) {
    LOG_ERROR("readPixels failed for frame " << fd.frame);
    return;
  }
  // Flip: JS reads m_buffer
  std::memcpy(m_buffer.get(), m_renderBuffer.get(), m_bufferSize);
  if (m_onFrameReady)
    m_onFrameReady(fd.frame);
}

void HeadlessCompositor::drawClipOnCanvas(SkCanvas *canvas,
                                          const ClipDesc &clip,
                                          const uint8_t *rgba, int imgW,
                                          int imgH, bool useGpu,
                                          int64_t frame) {
  // Use actual decoded dimensions
  if (imgW <= 0 || imgH <= 0) {
    imgW = m_width;
    imgH = m_height;
  }

  const size_t rowBytes = static_cast<size_t>(imgW) * 4;
  const size_t dataBytes = rowBytes * imgH;
  SkImageInfo info = SkImageInfo::Make(imgW, imgH, kRGBA_8888_SkColorType,
                                       kPremul_SkAlphaType);

  sk_sp<SkData> pixData = SkData::MakeWithCopy(rgba, dataBytes);
  sk_sp<SkImage> img = SkImages::RasterFromData(info, pixData, rowBytes);
  if (!img)
    return;

  // Apply SkSL effects
  if (!clip.effects.empty()) {
    img = applyEffects(img, clip, frame);
  }

  // Build transform matrix
  canvas->save();

  const auto &t = clip.transform;
  float cx = t.anchorX * m_width;
  float cy = t.anchorY * m_height;
  canvas->translate(t.x + cx, t.y + cy);
  canvas->rotate(t.rotation);
  canvas->scale(t.scaleX, t.scaleY);
  canvas->translate(-cx, -cy);

  // Scale decoded image to fill canvas
  if (imgW != m_width || imgH != m_height) {
    float sx = static_cast<float>(m_width) / imgW;
    float sy = static_cast<float>(m_height) / imgH;
    canvas->scale(sx, sy);
  }

  // videoClip.py
  SkPaint paint;
  paint.setAlphaf(clip.opacity);
  switch (clip.blendMode) {
  case 1:
    paint.setBlendMode(SkBlendMode::kMultiply);
    break; // Multiply
  case 2:
    paint.setBlendMode(SkBlendMode::kScreen);
    break; // Screen
  case 3:
    paint.setBlendMode(SkBlendMode::kOverlay);
    break; // Overlay
  case 4:
    paint.setBlendMode(SkBlendMode::kDarken);
    break; // Darken
  case 5:
    paint.setBlendMode(SkBlendMode::kLighten);
    break; // Lighten
  case 6:
    paint.setBlendMode(SkBlendMode::kColorDodge);
    break; // Color Dodge
  case 7:
    paint.setBlendMode(SkBlendMode::kColorBurn);
    break; // Color Burn
  case 8:
    paint.setBlendMode(SkBlendMode::kHardLight);
    break; // Hard Light
  case 9:
    paint.setBlendMode(SkBlendMode::kSoftLight);
    break; // Soft Light
  case 10:
    paint.setBlendMode(SkBlendMode::kDifference);
    break; // Difference
  case 11:
    paint.setBlendMode(SkBlendMode::kExclusion);
    break; // Exclusion
  default:
    paint.setBlendMode(SkBlendMode::kSrcOver);
    break; // Normal
  }

  canvas->drawImage(img, 0, 0, SkSamplingOptions(SkFilterMode::kLinear),
                    &paint);
  canvas->restore();
}

// SkSL effect chain
sk_sp<SkRuntimeEffect>
HeadlessCompositor::getOrCompileEffect(const std::string &typeId) {
  auto it = m_effectCache.find(typeId);
  if (it != m_effectCache.end())
    return it->second;

  std::string manifestPath = m_skslDir + "/" + typeId + ".json";
  std::string shaderFile = typeId + ".sksl"; // fallback
  {
    std::ifstream mf(manifestPath);
    if (mf.good()) {
      std::string content((std::istreambuf_iterator<char>(mf)),
                          std::istreambuf_iterator<char>());
      // Minimal JSON parse: look for "shader":
      auto pos = content.find("\"shader\"");
      if (pos != std::string::npos) {
        auto c1 = content.find('"', pos + 9);
        auto c2 = content.find('"', c1 + 1);
        if (c1 != std::string::npos && c2 != std::string::npos)
          shaderFile = content.substr(c1 + 1, c2 - c1 - 1);
      }
    }
  }

  std::string skslPath = m_skslDir + "/" + shaderFile;
  std::ifstream f(skslPath);
  if (!f.good()) {
    LOG_ERROR("SkSL file not found: " << skslPath);
    return nullptr;
  }
  std::string src((std::istreambuf_iterator<char>(f)),
                  std::istreambuf_iterator<char>());

  auto [effect, err] = SkRuntimeEffect::MakeForShader(SkString(src.c_str()));
  if (!effect) {
    LOG_ERROR("SkSL compile error [" << typeId << "]: " << err.c_str());
    m_effectCache[typeId] = nullptr;
    return nullptr;
  }
  LOG_INFO("Compiled SkSL: " << typeId);
  m_effectCache[typeId] = effect;
  return effect;
}

//   Apply a single effect pass
sk_sp<SkImage> HeadlessCompositor::applyOneEffect(sk_sp<SkImage> src,
                                                  const EffectParam &ep,
                                                  int64_t frame) {
  if (!src)
    return src;

  // Strip optional "sksl:" prefix
  std::string tid = ep.typeId;
  if (tid.rfind("sksl:", 0) == 0)
    tid = tid.substr(5);

  std::cerr << "[FX] applyOneEffect: " << tid << " frame=" << frame
            << " src=" << src->width() << "x" << src->height() << "\n";

  sk_sp<SkRuntimeEffect> effect = getOrCompileEffect(tid);
  if (!effect)
    return src;

  const int w = src->width();
  const int h = src->height();

  // Build shader builder once
  SkRuntimeShaderBuilder builder(effect);

  // Bind source image as child shader
  auto srcShader = src->makeShader(SkSamplingOptions(SkFilterMode::kLinear));
  if (!srcShader)
    return src;

  for (const auto &ch : effect->children())
    builder.child(std::string(ch.name)) = srcShader;

  // User uniforms
  for (const auto &uv : ep.uniforms) {
    if (!effect->findUniform(uv.id.c_str()))
      continue;
    const size_t n = uv.values.size();
    if (n == 1)
      builder.uniform(uv.id.c_str()) = uv.values[0];
    else if (n == 2)
      builder.uniform(uv.id.c_str()) = SkV2{uv.values[0], uv.values[1]};
    else if (n == 3)
      builder.uniform(uv.id.c_str()) =
          SkV3{uv.values[0], uv.values[1], uv.values[2]};
    else if (n >= 4)
      builder.uniform(uv.id.c_str()) =
          SkV4{uv.values[0], uv.values[1], uv.values[2], uv.values[3]};
  }

  // System uniforms
  auto tryFloat = [&](const char *name, float val) {
    if (effect->findUniform(name))
      builder.uniform(name) = val;
  };
  auto tryVec2 = [&](const char *name, float x, float y) {
    if (effect->findUniform(name))
      builder.uniform(name) = SkV2{x, y};
  };
  const float t = static_cast<float>(frame) / std::max(m_fps, 1.f);
  tryFloat("_frame", static_cast<float>(frame));
  tryFloat("frame", static_cast<float>(frame));
  tryFloat("time", t);
  tryFloat("iTime", t);
  tryFloat("_clipWidth", static_cast<float>(w));
  tryFloat("_clipHeight", static_cast<float>(h));
  tryVec2("iResolution", static_cast<float>(w), static_cast<float>(h));
  tryVec2("resolution", static_cast<float>(w), static_cast<float>(h));

  auto shader = builder.makeShader();
  if (!shader) {
    LOG_ERROR("makeShader() failed for [" << tid << "]");
    return src;
  }

  // GPU offscreen via GrDirectContext
  SkImageInfo info =
      SkImageInfo::Make(w, h, kRGBA_8888_SkColorType, kPremul_SkAlphaType,
                        SkColorSpace::MakeSRGB());
  sk_sp<SkSurface> offscreen;
  if (m_skia && m_skia->getDirectContext()) {
    offscreen = SkSurfaces::RenderTarget(m_skia->getDirectContext(),
                                         skgpu::Budgeted::kYes, info);
  }
  // CPU fallback
  if (!offscreen) {
    offscreen = SkSurfaces::Raster(info);
  }
  if (!offscreen) {
    LOG_ERROR("Cannot create offscreen for effect [" << tid << "]");
    return src;
  }

  SkPaint paint;
  paint.setShader(std::move(shader));
  offscreen->getCanvas()->clear(SK_ColorTRANSPARENT);
  offscreen->getCanvas()->drawPaint(paint);

  // Flush GPU work then snapshot
  if (m_skia && m_skia->getDirectContext())
    m_skia->getDirectContext()->flushAndSubmit();

  auto result = offscreen->makeImageSnapshot();
  std::cerr << "[FX] DONE: " << (result ? "OK" : "NULL") << "\n";
  return result;
}

//   Chain all effects on a clip
sk_sp<SkImage> HeadlessCompositor::applyEffects(sk_sp<SkImage> src,
                                                const ClipDesc &clip,
                                                int64_t frame) {
  if (clip.effects.empty())
    return src;
  sk_sp<SkImage> img = src;
  for (const auto &ep : clip.effects)
    img = applyOneEffect(img, ep, frame);
  return img;
}

sk_sp<SkImage>
HeadlessCompositor::renderGenerativeToImage(const ClipDesc &clip) {
  SkImageInfo info =
      SkImageInfo::MakeN32Premul(m_width, m_height, SkColorSpace::MakeSRGB());
  sk_sp<SkSurface> surf;
  if (m_skia && m_skia->getDirectContext())
    surf = SkSurfaces::RenderTarget(m_skia->getDirectContext(),
                                    skgpu::Budgeted::kYes, info);
  if (!surf)
    surf = SkSurfaces::Raster(info);
  if (!surf)
    return nullptr;

  SkCanvas *cv = surf->getCanvas();
  cv->clear(SK_ColorTRANSPARENT);

  switch (clip.type) {
  case ClipDesc::Type::Solid: {
    SkPaint p;
    p.setColor4f({clip.solidR, clip.solidG, clip.solidB, clip.solidA});
    cv->drawRect(SkRect::MakeWH(m_width, m_height), p);
    break;
  }
  case ClipDesc::Type::Text:
    fade::drawing::drawText(cv, clip, m_width, m_height);
    break;
  case ClipDesc::Type::Shape:
    fade::drawing::drawShape(cv, clip, m_width, m_height);
    break;
  case ClipDesc::Type::Pen:
    fade::drawing::drawPen(cv, clip, m_width, m_height);
    break;
  case ClipDesc::Type::Svg:
    fade::drawing::drawSvg(cv, clip, m_width, m_height);
    break;
  default:
    break;
  }

  if (m_skia && m_skia->getDirectContext())
    m_skia->getDirectContext()->flushAndSubmit();

  return surf->makeImageSnapshot();
}

sk_sp<SkImage> HeadlessCompositor::applyTransition(sk_sp<SkImage> srcA,
                                                   sk_sp<SkImage> srcB,
                                                   const TransitionDesc &td) {
  if (!srcA || !srcB)
    return srcA ? srcA : srcB;

  const std::string cacheKey = "transition:" + td.typeId;
  sk_sp<SkRuntimeEffect> effect;

  auto it = m_effectCache.find(cacheKey);
  if (it != m_effectCache.end()) {
    effect = it->second;
  } else {
    std::string path = m_skslDir + "/transitions/" + td.typeId + ".sksl";
    std::ifstream f(path);
    if (f.good()) {
      std::string src((std::istreambuf_iterator<char>(f)),
                      std::istreambuf_iterator<char>());
      auto [eff, err] = SkRuntimeEffect::MakeForShader(SkString(src.c_str()));
      if (eff) {
        LOG_INFO("Compiled transition: " << td.typeId);
        effect = eff;
      } else {
        LOG_ERROR("Transition shader compile error ["
                  << td.typeId << "]: " << (err.c_str() ? err.c_str() : "?"));
      }
    } else {
      LOG_ERROR("Transition shader not found: " << path);
    }
    m_effectCache[cacheKey] = effect;
  }

  if (!effect) {
    SkImageInfo info =
        SkImageInfo::Make(m_width, m_height, kRGBA_8888_SkColorType,
                          kPremul_SkAlphaType, SkColorSpace::MakeSRGB());
    GrDirectContext *grCtx = m_skia ? m_skia->getDirectContext() : nullptr;
    sk_sp<SkSurface> surf;
    if (grCtx)
      surf = SkSurfaces::RenderTarget(grCtx, skgpu::Budgeted::kYes, info);
    if (!surf)
      surf = SkSurfaces::Raster(info);
    if (!surf)
      return srcA;
    SkCanvas *cv = surf->getCanvas();
    cv->clear(SK_ColorBLACK);
    SkRect dst = SkRect::MakeWH(m_width, m_height);
    SkPaint pa;
    pa.setAlphaf(1.f - td.progress);
    cv->drawImageRect(srcA, dst, SkSamplingOptions(SkFilterMode::kLinear), &pa);
    SkPaint pb;
    pb.setAlphaf(td.progress);
    cv->drawImageRect(srcB, dst, SkSamplingOptions(SkFilterMode::kLinear), &pb);
    if (grCtx)
      grCtx->flushAndSubmit();
    return surf->makeImageSnapshot();
  }

  // GPU shader path
  std::cerr << "[TRANS-FN] GPU shader path begin\n";
  SkRuntimeShaderBuilder builder(effect);

  // Convert both sources to clean raster images
  auto toRaster = [](sk_sp<SkImage> img, const char *label) -> sk_sp<SkImage> {
    if (!img)
      return img;
    const int sw = img->width();
    const int sh = img->height();
    SkImageInfo ri =
        SkImageInfo::Make(sw, sh, kRGBA_8888_SkColorType, kPremul_SkAlphaType,
                          SkColorSpace::MakeSRGB());
    const size_t rb = static_cast<size_t>(sw) * 4;
    sk_sp<SkData> px = SkData::MakeUninitialized(rb * sh);
    bool ok = img->readPixels(ri, px->writable_data(), rb, 0, 0);
    if (ok) {
      std::cerr << "[TRANS-FN] toRaster(" << label << ") OK\n";
      return SkImages::RasterFromData(ri, px, rb);
    }
    std::cerr << "[TRANS-FN] toRaster(" << label << ") FAILED, using as-is\n";
    return img;
  };
  srcA = toRaster(srcA, "A");
  srcB = toRaster(srcB, "B");

  auto scaleToProject = [&](sk_sp<SkImage> img) -> sk_sp<SkImage> {
    if (!img || (img->width() == m_width && img->height() == m_height))
      return img;
    SkImageInfo si =
        SkImageInfo::Make(m_width, m_height, kRGBA_8888_SkColorType,
                          kPremul_SkAlphaType, SkColorSpace::MakeSRGB());
    GrDirectContext *gc = m_skia ? m_skia->getDirectContext() : nullptr;
    sk_sp<SkSurface> s;
    if (gc)
      s = SkSurfaces::RenderTarget(gc, skgpu::Budgeted::kYes, si);
    if (!s)
      s = SkSurfaces::Raster(si);
    if (!s)
      return img;
    SkCanvas *cv = s->getCanvas();
    cv->clear(SK_ColorBLACK);
    cv->drawImageRect(img, SkRect::MakeWH(m_width, m_height),
                      SkSamplingOptions(SkFilterMode::kLinear));
    if (gc)
      gc->flushAndSubmit(GrSyncCpu::kYes);
    return s->makeImageSnapshot();
  };
  srcA = scaleToProject(srcA);
  srcB = scaleToProject(srcB);

  std::cerr << "[TRANS-FN] makeShader(A)...\n";
  auto shaderA = srcA->makeShader(SkSamplingOptions(SkFilterMode::kLinear));
  std::cerr << "[TRANS-FN] makeShader(A): " << (shaderA ? "OK" : "NULL")
            << "\n";
  std::cerr << "[TRANS-FN] makeShader(B)...\n";
  auto shaderB = srcB->makeShader(SkSamplingOptions(SkFilterMode::kLinear));
  std::cerr << "[TRANS-FN] makeShader(B): " << (shaderB ? "OK" : "NULL")
            << "\n";

  // Bind named children
  std::cerr << "[TRANS-FN] binding children (" << effect->children().size()
            << ")...\n";
  for (const auto &ch : effect->children()) {
    std::string name(ch.name);
    std::cerr << "[TRANS-FN]   child: " << name << "\n";
    try {
      if (name == "srcA" || name == "source")
        builder.child(name) = shaderA;
      else if (name == "srcB")
        builder.child(name) = shaderB;
      else
        builder.child(name) = shaderA;
    } catch (...) {
      std::cerr << "[TRANS-FN]   child bind EXCEPTION\n";
    }
  }

  // Push uniforms from TransitionDesc
  std::cerr << "[TRANS-FN] pushing " << td.uniforms.size() << " uniforms...\n";
  for (const auto &uv : td.uniforms) {
    if (!effect->findUniform(uv.id.c_str()))
      continue;
    const size_t n = uv.values.size();
    std::cerr << "[TRANS-FN]   uniform " << uv.id << " n=" << n << "\n";
    if (n == 1)
      builder.uniform(uv.id.c_str()) = uv.values[0];
    else if (n == 2)
      builder.uniform(uv.id.c_str()) = SkV2{uv.values[0], uv.values[1]};
    else if (n == 3)
      builder.uniform(uv.id.c_str()) =
          SkV3{uv.values[0], uv.values[1], uv.values[2]};
    else if (n >= 4)
      builder.uniform(uv.id.c_str()) =
          SkV4{uv.values[0], uv.values[1], uv.values[2], uv.values[3]};
  }

  std::cerr << "[TRANS-FN] builder.makeShader()...\n";
  auto shader = builder.makeShader();
  std::cerr << "[TRANS-FN] shader: " << (shader ? "OK" : "NULL") << "\n";
  if (!shader)
    return srcA;

  SkImageInfo info =
      SkImageInfo::Make(m_width, m_height, kRGBA_8888_SkColorType,
                        kPremul_SkAlphaType, SkColorSpace::MakeSRGB());
  GrDirectContext *grCtx = m_skia ? m_skia->getDirectContext() : nullptr;
  sk_sp<SkSurface> offscreen;
  if (grCtx)
    offscreen = SkSurfaces::RenderTarget(grCtx, skgpu::Budgeted::kYes, info);
  if (!offscreen)
    offscreen = SkSurfaces::Raster(info);
  if (!offscreen)
    return srcA;

  SkPaint paint;
  paint.setShader(shader);
  std::cerr << "[TRANS-FN] drawing to offscreen...\n";
  offscreen->getCanvas()->clear(SK_ColorTRANSPARENT);
  offscreen->getCanvas()->drawRect(SkRect::MakeWH(m_width, m_height), paint);

  std::cerr << "[TRANS-FN] flushing (sync)...\n";
  if (grCtx)
    grCtx->flushAndSubmit(GrSyncCpu::kYes); // SYNC flush
  std::cerr << "[TRANS-FN] snapshot...\n";
  auto result = offscreen->makeImageSnapshot();
  std::cerr << "[TRANS-FN] DONE: " << (result ? "OK" : "NULL") << "\n";
  return result;
}

//   Playback

void HeadlessCompositor::play() {
  if (m_playing.exchange(true))
    return; // already playing

  // Join any previous thread
  if (m_playThread.joinable())
    m_playThread.join();

  m_playThread = std::thread([this]() {
    using clock = std::chrono::steady_clock;
    using ns = std::chrono::nanoseconds;

    const ns frameDur = std::chrono::duration_cast<ns>(
        std::chrono::duration<double>(1.0 / static_cast<double>(m_fps)));

    auto nextTick = clock::now() + frameDur;
    uint64_t lastSeekGen = m_seekGeneration.load();

    while (m_playing.load()) {
      // Check if a seek happened
      uint64_t curGen = m_seekGeneration.load();
      if (curGen != lastSeekGen) {
        lastSeekGen = curGen;
        nextTick = clock::now() + frameDur;
      }

      int64_t frame = m_currentFrame.load();

      // check pause before https
      if (!m_playing.load())
        break;

      // Fetch layout from Python
      auto t0 = clock::now();
      std::string json = fetchFrameJson(frame);
      auto t1 = clock::now();

      if (!m_playing.load())
        break;

      if (!json.empty()) {
        FrameDescriptor fd = parseFrameDescriptor(json);
        if (fd.valid) {
          //  Responsive pause check before expensive
          if (!m_playing.load())
            break;

          // Async prefetch
          for (const auto &clip : fd.clips) {
            if (clip.type == ClipDesc::Type::Video ||
                clip.type == ClipDesc::Type::Image) {
              if (!clip.file.empty()) {
                if (clip.type == ClipDesc::Type::Video)
                  schedRegisterVideo(clip.file, clip.file);
                else
                  schedRegisterImage(clip.file, clip.file);
                schedPrefetchAround(clip.file, clip.sourceFrame, 8);
              }
            }
          }

          auto t2 = clock::now();
          std::lock_guard<std::mutex> lock(m_renderMutex);
          doRender(fd);
          auto t3 = clock::now();

          auto httpMs =
              std::chrono::duration_cast<std::chrono::microseconds>(t1 - t0)
                  .count() /
              1000.0;
          auto renderMs =
              std::chrono::duration_cast<std::chrono::microseconds>(t3 - t2)
                  .count() /
              1000.0;
          std::cout << "[PLAY] frame=" << frame << " http=" << httpMs << "ms"
                    << " render=" << renderMs << "ms"
                    << " clips=" << fd.clips.size() << "\n";
        }
      }

      m_currentFrame.fetch_add(1);

      auto now = clock::now();
      if (now < nextTick) {
        // On time or ahead
        std::unique_lock<std::mutex> lk(m_sleepMutex);
        m_sleepCv.wait_until(lk, nextTick, [this, &lastSeekGen]() {
          return !m_playing.load() || m_seekGeneration.load() != lastSeekGen;
        });
      }

      nextTick = clock::now() + frameDur;
    }
  });
}

void HeadlessCompositor::pause() {
  m_playing.store(false);
  m_sleepCv.notify_all(); // wake play thread immediately
  if (m_playThread.joinable())
    m_playThread.join();
}

void HeadlessCompositor::seek(int64_t frame) {
  m_currentFrame.store(frame);
  // Bump generation
  m_seekGeneration.fetch_add(1);
  m_sleepCv.notify_all();

  if (m_playing.load())
    return;

  // Paused
  uint64_t myGen = m_seekGeneration.load();
  std::thread([this, frame, myGen]() {
    std::string json = fetchFrameJson(frame);
    if (json.empty())
      return;
    FrameDescriptor fd = parseFrameDescriptor(json);
    if (!fd.valid)
      return;
    if (m_seekGeneration.load() != myGen)
      return;
    std::lock_guard<std::mutex> lock(m_renderMutex);
    if (m_seekGeneration.load() != myGen)
      return;
    doRender(fd);
  }).detach();
}

//   TCP Frame Socket

static int tcpRecvAll(SOCKET s, char *buf, int needed) {
  int total = 0;
  while (total < needed) {
    int r = recv(s, buf + total, needed - total, 0);
    if (r <= 0)
      return total; // connection closed or error
    total += r;
  }
  return total;
}

bool HeadlessCompositor::connectTcp() {
  if (m_frameSock != INVALID_SOCKET)
    return true;

  // One-time Winsock init
  WSADATA wsaData;
  WSAStartup(MAKEWORD(2, 2), &wsaData);

  m_frameSock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
  if (m_frameSock == INVALID_SOCKET) {
    LOG_ERROR("TCP socket creation failed: " << WSAGetLastError());
    return false;
  }

  // Disable Nagle's algorithm
  int flag = 1;
  setsockopt(m_frameSock, IPPROTO_TCP, TCP_NODELAY,
             reinterpret_cast<char *>(&flag), sizeof(flag));

  // Python TCP frame server
  int tcpPort = m_pythonPort + 1;

  sockaddr_in addr{};
  addr.sin_family = AF_INET;
  addr.sin_port = htons(static_cast<u_short>(tcpPort));
  addr.sin_addr.s_addr = inet_addr("127.0.0.1"); // never DNS-resolve

  if (connect(m_frameSock, reinterpret_cast<sockaddr *>(&addr), sizeof(addr)) !=
      0) {
    LOG_ERROR("TCP connect to 127.0.0.1:" << tcpPort
                                          << " failed: " << WSAGetLastError());
    closesocket(m_frameSock);
    m_frameSock = INVALID_SOCKET;
    return false;
  }
  std::cout << "[TCP] Connected to frame server on 127.0.0.1:" << tcpPort
            << "\n";
  return true;
}

void HeadlessCompositor::closeTcp() {
  if (m_frameSock != INVALID_SOCKET) {
    closesocket(m_frameSock);
    m_frameSock = INVALID_SOCKET;
  }
  WSACleanup();
}

std::string HeadlessCompositor::fetchFrameJson(int64_t frameNum) {

  std::lock_guard<std::mutex> tcpLock(m_tcpMutex);

  // Lazy connect on first call
  if (m_frameSock == INVALID_SOCKET) {
    if (!connectTcp())
      return {};
  }

  // Send
  uint32_t req = static_cast<uint32_t>(frameNum);
  if (send(m_frameSock, reinterpret_cast<char *>(&req), 4, 0) != 4) {
    LOG_ERROR("TCP send failed — reconnecting next frame");
    closesocket(m_frameSock);
    m_frameSock = INVALID_SOCKET;
    return {};
  }

  // Receive
  uint32_t payLen = 0;
  if (tcpRecvAll(m_frameSock, reinterpret_cast<char *>(&payLen), 4) != 4) {
    closesocket(m_frameSock);
    m_frameSock = INVALID_SOCKET;
    return {};
  }
  if (payLen == 0 || payLen > 2u * 1024 * 1024)
    return {}; // sanity

  // Receive: JSON body
  std::string json(payLen, '\0');
  if (tcpRecvAll(m_frameSock, json.data(), static_cast<int>(payLen)) !=
      static_cast<int>(payLen)) {
    closesocket(m_frameSock);
    m_frameSock = INVALID_SOCKET;
    return {};
  }
  return json;
}

std::vector<uint8_t> HeadlessCompositor::exportFrameSync(int64_t frameNum) {

  std::string json = fetchFrameJson(frameNum);
  if (json.empty()) {

    return std::vector<uint8_t>(static_cast<size_t>(m_width) * m_height * 4, 0);
  }

  FrameDescriptor fd = parseFrameDescriptor(json);
  if (!fd.valid) {
    return std::vector<uint8_t>(static_cast<size_t>(m_width) * m_height * 4, 0);
  }

  {
    std::lock_guard<std::mutex> lk(m_renderMutex);
    doRender(fd);
  }

  std::vector<uint8_t> out(m_bufferSize);
  std::memcpy(out.data(), m_buffer.get(), m_bufferSize);
  return out;
}
