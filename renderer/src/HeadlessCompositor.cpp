#include "HeadlessCompositor.hpp"
#include "core/api/Logger.hpp"
#include "rendering/DrawPen.hpp"
#include "rendering/DrawShape.hpp"
#include "rendering/DrawText.hpp"


#include <core/SkBlendMode.h>
#include <core/SkCanvas.h>
#include <core/SkData.h>
#include <core/SkM44.h>
#include <core/SkPaint.h>
#include <core/SkRect.h>
#include <core/SkSamplingOptions.h>
#include <effects/SkRuntimeEffect.h>
#include <gpu/ganesh/GrDirectContext.h>
#include <gpu/ganesh/SkSurfaceGanesh.h>

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

// ── Constructor / destructor

HeadlessCompositor::HeadlessCompositor(int width, int height, float fps,
                                       const std::string &effectsDir)
    : m_width(width), m_height(height), m_fps(fps) {
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

  //  Allocate front buffer (SharedArrayBuffer — JS reads this)
  m_bufferSize = static_cast<size_t>(m_width) * m_height * 4;
  m_buffer = std::make_unique<uint8_t[]>(m_bufferSize);
  std::memset(m_buffer.get(), 0, m_bufferSize);
  // Back buffer — C++ renders here; memcpy to m_buffer before signaling JS
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

  // Flush all in-flight GPU work before releasing resources
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

  //   ULTRA-FAST PATH
  // sws_scale writes RGBA directly into m_buffer — video/image only
  // Generative clip types (Solid, Text, Shape) must NOT enter this path
  // because they have no file to decode.
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

        // Direct decode: sws_scale → m_renderBuffer (double-buffered)
        if (decoder->decodeFrameDirect(clip.sourceFrame, m_renderBuffer.get(),
                                       m_width, m_height)) {
          // Flip: atomic copy to front buffer before signaling JS
          std::memcpy(m_buffer.get(), m_renderBuffer.get(), m_bufferSize);
          if (m_onFrameReady)
            m_onFrameReady(fd.frame);
          return;
        }
        // Fall through if direct decode not supported (SW decoder)
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
        clip.type == ClipDesc::Type::Pen) {
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

  if (!needsGpu) {

    SkImageInfo cpuInfo = SkImageInfo::Make(
        m_width, m_height, kRGBA_8888_SkColorType, kPremul_SkAlphaType);
    auto cpuSurface = SkSurfaces::WrapPixels(cpuInfo, m_renderBuffer.get(),
                                             static_cast<size_t>(m_width) * 4);

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
        if (cp.rgba.empty())
          continue;
        drawClipOnCanvas(canvas, *cp.clip, cp.rgba.data(), cp.imgW, cp.imgH,
                         /*useGpu=*/false);
      }
      // Flip: copy fully-composed frame to front buffer, then signal JS.
      // JS reads m_buffer; C++ wrote to m_renderBuffer — no race.
      cpuSurface.reset();  // flush WrapPixels surface before memcpy
      std::memcpy(m_buffer.get(), m_renderBuffer.get(), m_bufferSize);
      if (m_onFrameReady)
        m_onFrameReady(fd.frame);
      return;
    }
  }

  //   GPU path
  SkCanvas *canvas = m_surface->getCanvas();
  canvas->clear(SK_ColorBLACK);

  for (const auto &cp : decoded) {
    if (cp.clip->type == ClipDesc::Type::Solid) {
      SkPaint p;
      p.setColor4f(
          {cp.clip->solidR, cp.clip->solidG, cp.clip->solidB, cp.clip->solidA});
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
    if (cp.rgba.empty())
      continue;
    drawClipOnCanvas(canvas, *cp.clip, cp.rgba.data(), cp.imgW, cp.imgH,
                     /*useGpu=*/true);
  }

  // GPU sync + readback → m_renderBuffer, then flip to m_buffer
  m_skia->getDirectContext()->flushAndSubmit();
  SkImageInfo readInfo = SkImageInfo::Make(
      m_width, m_height, kRGBA_8888_SkColorType, kOpaque_SkAlphaType);
  bool ok = m_surface->readPixels(readInfo, m_renderBuffer.get(),
                                  static_cast<size_t>(m_width) * 4, 0, 0);
  if (!ok) {
    LOG_ERROR("readPixels failed for frame " << fd.frame);
    return;
  }
  // Flip: JS reads m_buffer, C++ wrote m_renderBuffer — no race
  std::memcpy(m_buffer.get(), m_renderBuffer.get(), m_bufferSize);
  if (m_onFrameReady)
    m_onFrameReady(fd.frame);
}

void HeadlessCompositor::drawClipOnCanvas(SkCanvas *canvas,
                                          const ClipDesc &clip,
                                          const uint8_t *rgba, int imgW,
                                          int imgH, bool useGpu) {
  // Use actual decoded dimensions
  if (imgW <= 0 || imgH <= 0) {
    imgW = m_width;
    imgH = m_height;
  }

  SkImageInfo info = SkImageInfo::Make(imgW, imgH, kRGBA_8888_SkColorType,
                                       kOpaque_SkAlphaType);
  SkBitmap bmp;
  bmp.installPixels(info, const_cast<uint8_t *>(rgba),
                    static_cast<size_t>(imgW) * 4);
  bmp.setImmutable();
  sk_sp<SkImage> img = bmp.asImage();

  // Apply SkSL effects (GPU-side only)
  if (useGpu && !clip.effects.empty())
    img = applyEffects(img, clip);

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

sk_sp<SkImage> HeadlessCompositor::applyEffects(sk_sp<SkImage> src,
                                                const ClipDesc &clip) {
  (void)clip;
  return src;
}

// Text  → fade::drawing::drawText()   in rendering/DrawText.cpp
// Shape → fade::drawing::drawShape()  in rendering/DrawShape.cpp

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
  // Serialize the full send+recv transaction.
  // seek() spawns concurrent threads — without this lock they interleave
  // their uint32_t writes and reads on the shared socket, producing garbled
  // JSON.
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
