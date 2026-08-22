#include "HeadlessCompositor.hpp"
#include "core/api/Logger.hpp"
#include "napi/FrameDescriptor.hpp"
#include "rendering/DrawPen.hpp"
#include "rendering/DrawShape.hpp"
#include "rendering/DrawSvg.hpp"
#include "rendering/DrawText.hpp"

#include <core/SkBlendMode.h>
#include <core/SkCanvas.h>
#include <core/SkColorSpace.h>
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

// ── Constructor

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
        auto &decoder = m_decoders[clip.file];
        if (!decoder)
          decoder =
              std::make_unique<ClipDecoder>(clip.file, m_device.get(), 1.0f);

        // Direct decode: sws_scale
        if (decoder->decodeFrameDirect(clip.sourceFrame, m_renderBuffer.get(),
                                       m_width, m_height)) {
          // Flip: atomic copy to front buffer before signaling JS
          std::memcpy(m_buffer.get(), m_renderBuffer.get(), m_bufferSize);
          if (m_onFrameReady)
            m_onFrameReady(fd.frame);
          return;
        }
        // Fall through if direct decode not supported
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
    // Skip video/image decode for generative clip types
    if (clip.type == ClipDesc::Type::Solid ||
        clip.type == ClipDesc::Type::Text ||
        clip.type == ClipDesc::Type::Shape ||
        clip.type == ClipDesc::Type::Pen ||
        clip.type == ClipDesc::Type::Svg) {
      decoded.push_back({&clip, {}, 0, 0});
      continue;
    }
    // Safety: never try to open an empty path — would crash the decoder
    if (clip.file.empty()) {
      decoded.push_back({&clip, {}, 0, 0});
      continue;
    }
    auto &decoder = m_decoders[clip.file];
    if (!decoder)
      decoder = std::make_unique<ClipDecoder>(clip.file, m_device.get(), 1.0f);

    auto result = decoder->decodeFrame(clip.sourceFrame);
    if (!clip.effects.empty())
      needsGpu = true;
    decoded.push_back(
        {&clip, std::move(result.rgba), result.width, result.height});
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
  SkCanvas *canvas = m_surface->getCanvas();
  canvas->clear(SK_ColorBLACK);

  for (const auto &cp : decoded) {
    const ClipDesc &cl = *cp.clip;
    const bool hasEffects = !cl.effects.empty();

    // For generative clips with effects: render to an intermediate image first,
    // run the SkSL chain on it, then composite the result.
    const bool isGenerative = (cl.type == ClipDesc::Type::Solid  ||
                               cl.type == ClipDesc::Type::Text   ||
                               cl.type == ClipDesc::Type::Shape  ||
                               cl.type == ClipDesc::Type::Pen    ||
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
    if (cp.rgba.empty())
      continue;
    drawClipOnCanvas(canvas, cl, cp.rgba.data(), cp.imgW, cp.imgH,
                     /*useGpu=*/true, fd.frame);
  }

  // GPU sync
  m_skia->getDirectContext()->flushAndSubmit();
  SkImageInfo readInfo = SkImageInfo::Make(
      m_width, m_height, kRGBA_8888_SkColorType, kOpaque_SkAlphaType);
  bool ok = m_surface->readPixels(readInfo, m_renderBuffer.get(),
                                  static_cast<size_t>(m_width) * 4, 0, 0);
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
  SkBitmap bmp;
  bmp.allocPixels(info, rowBytes);
  std::memcpy(bmp.getPixels(), rgba, dataBytes);
  bmp.setImmutable();
  sk_sp<SkImage> img = bmp.asImage();
  if (!img)
    return;

  // Apply SkSL effects (GPU-side only)
  if (useGpu && !clip.effects.empty())
    img = applyEffects(img, clip, frame);

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

  // Blend mode
  SkPaint paint;
  paint.setAlphaf(clip.opacity);
  switch (clip.blendMode) {
  case 1:
    paint.setBlendMode(SkBlendMode::kPlus);
    break;
  case 2:
    paint.setBlendMode(SkBlendMode::kMultiply);
    break;
  case 3:
    paint.setBlendMode(SkBlendMode::kScreen);
    break;
  case 4:
    paint.setBlendMode(SkBlendMode::kOverlay);
    break;
  default:
    paint.setBlendMode(SkBlendMode::kSrcOver);
    break;
  }

  canvas->drawImage(img, 0, 0, SkSamplingOptions(SkFilterMode::kLinear),
                    &paint);
  canvas->restore();
}

//   SkSL effect chain

// ── Load and compile a single SkSL shader, with caching ──────────────────────
sk_sp<SkRuntimeEffect> HeadlessCompositor::getOrCompileEffect(const std::string& typeId) {
  auto it = m_effectCache.find(typeId);
  if (it != m_effectCache.end())
    return it->second;

  // Try to read  <skslDir>/<typeId>.sksl
  // First resolve the manifest to get the actual shader filename
  std::string manifestPath = m_skslDir + "/" + typeId + ".json";
  std::string shaderFile   = typeId + ".sksl";  // fallback
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

// ── Apply a single effect pass (Qteee SkRuntimeShaderBuilder pattern) ────────
sk_sp<SkImage> HeadlessCompositor::applyOneEffect(sk_sp<SkImage> src,
                                                  const EffectParam& ep,
                                                  int64_t frame) {
  if (!src) return src;

  // Strip optional "sksl:" prefix — typeId is e.g. "gaussian_blur"
  std::string tid = ep.typeId;
  if (tid.rfind("sksl:", 0) == 0) tid = tid.substr(5);

  sk_sp<SkRuntimeEffect> effect = getOrCompileEffect(tid);
  if (!effect) return src;

  // ── Qteee pattern: use SkRuntimeShaderBuilder ─────────────────────────────
  // (same as EffectInstance::apply in Qteee-Vulkan)
  SkRuntimeShaderBuilder builder(effect);

  // Bind "source" child (primary input)
  auto srcShader = src->makeShader(SkSamplingOptions(SkFilterMode::kLinear));
  // Bind every declared child to the source (handles "source", "_originalSource", etc.)
  for (const auto& ch : effect->children()) {
    // ch.name is std::string_view — convert to std::string for builder.child()
    try { builder.child(std::string(ch.name)) = srcShader; } catch (...) {}
  }

  // Push user-set uniform values from the frame descriptor
  for (const auto& uv : ep.uniforms) {
    if (!effect->findUniform(uv.id.c_str())) continue;
    const size_t n = uv.values.size();
    if      (n == 1) builder.uniform(uv.id.c_str()) = uv.values[0];
    else if (n == 2) builder.uniform(uv.id.c_str()) = SkV2{uv.values[0], uv.values[1]};
    else if (n == 3) builder.uniform(uv.id.c_str()) = SkV3{uv.values[0], uv.values[1], uv.values[2]};
    else if (n >= 4) builder.uniform(uv.id.c_str()) = SkV4{uv.values[0], uv.values[1], uv.values[2], uv.values[3]};
  }

  // Inject Qteee-style system uniforms (only if declared in the shader)
  auto tryFloat = [&](const char* name, float val) {
    if (effect->findUniform(name)) builder.uniform(name) = val;
  };
  auto tryVec2 = [&](const char* name, float x, float y) {
    if (effect->findUniform(name)) builder.uniform(name) = SkV2{x, y};
  };

  const float t = static_cast<float>(frame) / std::max(m_fps, 1.f);
  tryFloat("_frame",       static_cast<float>(frame));
  tryFloat("frame",        static_cast<float>(frame));
  tryFloat("time",         t);
  tryFloat("iTime",        t);
  tryFloat("_clipWidth",   static_cast<float>(src->width()));
  tryFloat("_clipHeight",  static_cast<float>(src->height()));
  tryVec2 ("iResolution",  static_cast<float>(src->width()),
                           static_cast<float>(src->height()));
  tryVec2 ("resolution",   static_cast<float>(src->width()),
                           static_cast<float>(src->height()));

  auto shader = builder.makeShader();
  if (!shader) {
    LOG_ERROR("SkRuntimeShaderBuilder::makeShader() failed for [" << tid << "]");
    return src;
  }

  // ── Render into offscreen GPU surface (Qteee: SkSurfaces::RenderTarget) ───
  const int w = src->width();
  const int h = src->height();
  SkImageInfo info = SkImageInfo::Make(w, h, kRGBA_8888_SkColorType,
                                       kPremul_SkAlphaType);
  GrDirectContext* grCtx = m_skia ? m_skia->getDirectContext() : nullptr;

  sk_sp<SkSurface> offscreen;
  if (grCtx)
    offscreen = SkSurfaces::RenderTarget(grCtx, skgpu::Budgeted::kYes, info);
  if (!offscreen)
    offscreen = SkSurfaces::Raster(info);  // CPU fallback
  if (!offscreen) {
    LOG_ERROR("Cannot create offscreen surface for effect [" << tid << "]");
    return src;
  }

  SkPaint paint;
  paint.setShader(shader);
  offscreen->getCanvas()->clear(SK_ColorTRANSPARENT);
  offscreen->getCanvas()->drawPaint(paint);

  if (grCtx) grCtx->flushAndSubmit();

  return offscreen->makeImageSnapshot();
}

// ── Chain all effects on a clip ───────────────────────────────────────────────
sk_sp<SkImage> HeadlessCompositor::applyEffects(sk_sp<SkImage> src,
                                                const ClipDesc& clip,
                                                int64_t frame) {
  if (clip.effects.empty()) return src;
  sk_sp<SkImage> img = src;
  for (const auto& ep : clip.effects)
    img = applyOneEffect(img, ep, frame);
  return img;
}

// ── Render a generative clip to an SkImage (for SkSL effect input) ───────────
// Text, Shape, Pen, Solid, SVG are all drawn to an offscreen surface so that
// SkSL shaders get a proper pixel buffer to sample from via "source".
sk_sp<SkImage> HeadlessCompositor::renderGenerativeToImage(const ClipDesc& clip) {
  SkImageInfo info = SkImageInfo::MakeN32Premul(m_width, m_height,
                                                SkColorSpace::MakeSRGB());
  sk_sp<SkSurface> surf;
  if (m_skia && m_skia->getDirectContext())
    surf = SkSurfaces::RenderTarget(m_skia->getDirectContext(),
                                    skgpu::Budgeted::kYes, info);
  if (!surf)
    surf = SkSurfaces::Raster(info);
  if (!surf) return nullptr;

  SkCanvas* cv = surf->getCanvas();
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
        nextTick = clock::now() + frameDur; // reset deadline after seek
      }

      int64_t frame = m_currentFrame.load();

      // Fetch layout from Python
      auto t0 = clock::now();
      std::string json = fetchFrameJson(frame);
      auto t1 = clock::now();

      if (!json.empty()) {
        FrameDescriptor fd = parseFrameDescriptor(json);
        if (fd.valid) {
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
      if (now >= nextTick) {
        // Behind schedule
        auto behind = std::chrono::duration_cast<ns>(now - nextTick);
        int64_t framesLate = behind.count() / frameDur.count();
        if (framesLate > 0) {
          m_currentFrame.fetch_add(framesLate);
        }
        nextTick = now + frameDur;
      } else {
        // On time
        std::unique_lock<std::mutex> lk(m_sleepMutex);
        m_sleepCv.wait_until(lk, nextTick, [this, &lastSeekGen]() {
          return !m_playing.load() || m_seekGeneration.load() != lastSeekGen;
        });
        nextTick += frameDur;
      }
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

  // Send: 4-byte LE frame number
  uint32_t req = static_cast<uint32_t>(frameNum);
  if (send(m_frameSock, reinterpret_cast<char *>(&req), 4, 0) != 4) {
    LOG_ERROR("TCP send failed — reconnecting next frame");
    closesocket(m_frameSock);
    m_frameSock = INVALID_SOCKET;
    return {};
  }

  // Receive: 4-byte LE payload length
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
