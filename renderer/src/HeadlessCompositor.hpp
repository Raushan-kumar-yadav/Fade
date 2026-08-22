#pragma once
#include "gpu/vulkan/device/DeviceContext.hpp"
#include "gpu/vulkan/skia/SkiaContext.hpp"
#include "napi/FrameDescriptor.hpp"
#include "video/ClipDecoder.hpp"

#include <core/SkBitmap.h>
#include <core/SkCanvas.h>
#include <core/SkColorSpace.h>
#include <core/SkColorType.h>
#include <core/SkFont.h>
#include <core/SkFontMgr.h>
#include <core/SkFontStyle.h>
#include <core/SkImage.h>
#include <core/SkImageInfo.h>
#include <core/SkMaskFilter.h>
#include <core/SkPath.h>
#include <core/SkRRect.h>
#include <core/SkSurface.h>
#include <core/SkTextBlob.h>
#include <core/SkTypeface.h>
#include <effects/SkImageFilters.h>
#include <effects/SkRuntimeEffect.h>
#include <gpu/ganesh/GrDirectContext.h>
#include <gpu/ganesh/SkSurfaceGanesh.h>

#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

#include <winsock2.h>
#include <ws2tcpip.h>
#pragma comment(lib, "ws2_32.lib")

class HeadlessCompositor {
public:
  using FrameReadyCallback = std::function<void(int64_t frameNum)>;

  HeadlessCompositor(int width, int height, float fps,
                     const std::string &effectsDir = "");
  ~HeadlessCompositor();

  HeadlessCompositor(const HeadlessCompositor &) = delete;
  HeadlessCompositor &operator=(const HeadlessCompositor &) = delete;

  void renderFrame(const FrameDescriptor &fd);

  void play();
  void pause();
  bool isPlaying() const { return m_playing.load(); }

  void seek(int64_t frame);

  // Export: synchronous frame render → raw RGBA bytes.
  std::vector<uint8_t> exportFrameSync(int64_t frameNum);

  uint8_t *getBuffer() const { return m_buffer.get(); }
  size_t   getBufferSize() const { return m_bufferSize; }

  void setFrameReadyCallback(FrameReadyCallback cb) {
    m_onFrameReady = std::move(cb);
  }
  void setPythonPort(int port) {
    if (m_pythonPort != port) {
      m_pythonPort = port;
      closeTcp();
    }
  }

  int   width()  const { return m_width;  }
  int   height() const { return m_height; }
  float fps()    const { return m_fps;    }

private:
  // ── Lifecycle ─────────────────────────────────────────────────────────────
  void init(const std::string &effectsDir);
  void shutdown();
  void doRender(const FrameDescriptor &fd);

  // ── Per-clip draw ─────────────────────────────────────────────────────────
  // Draw decoded video/image pixels onto the main canvas, applying SkSL effects.
  void drawClipOnCanvas(SkCanvas *canvas, const ClipDesc &clip,
                        const uint8_t *rgba, int imgW, int imgH,
                        bool useGpu, int64_t frame = 0);

  // ── SkSL effect pipeline ──────────────────────────────────────────────────
  // Load + compile a SkSL shader by typeId, cached after first compile.
  sk_sp<SkRuntimeEffect> getOrCompileEffect(const std::string &typeId);

  // Apply one effect pass (Qteee SkRuntimeShaderBuilder pattern).
  sk_sp<SkImage> applyOneEffect(sk_sp<SkImage> src,
                                const EffectParam &ep, int64_t frame);

  // Chain all effects on a clip in order.
  sk_sp<SkImage> applyEffects(sk_sp<SkImage> src,
                              const ClipDesc &clip, int64_t frame = 0);

  // Rasterise a generative clip (Text/Shape/Pen/Solid/SVG) to an SkImage
  // so SkSL shaders can sample it via the "source" child.
  sk_sp<SkImage> renderGenerativeToImage(const ClipDesc &clip);

  // ── Members ───────────────────────────────────────────────────────────────
  int   m_width;
  int   m_height;
  float m_fps;

  // Directory that contains <typeId>.json manifests and <name>.sksl shaders.
  std::string m_skslDir;

  std::unique_ptr<DeviceContext> m_device;
  std::unique_ptr<SkiaContext>   m_skia;

  // Per-file video decoder cache
  std::unordered_map<std::string, std::unique_ptr<ClipDecoder>> m_decoders;

  // SkSL runtime-effect cache: typeId → compiled SkRuntimeEffect
  std::unordered_map<std::string, sk_sp<SkRuntimeEffect>> m_effectCache;

  // Main compositing surface
  sk_sp<SkSurface> m_surface;

  std::unique_ptr<uint8_t[]> m_buffer;       // front buffer: JS reads
  std::unique_ptr<uint8_t[]> m_renderBuffer; // back  buffer: C++ writes
  size_t m_bufferSize = 0;

  std::atomic<bool>     m_playing{false};
  std::atomic<int64_t>  m_currentFrame{0};
  std::atomic<uint64_t> m_seekGeneration{0};
  std::thread            m_playThread;
  FrameReadyCallback     m_onFrameReady;
  std::mutex             m_renderMutex;

  std::mutex              m_sleepMutex;
  std::condition_variable m_sleepCv;

  // ── TCP frame-data channel to Python ─────────────────────────────────────
  std::string fetchFrameJson(int64_t frameNum);
  bool connectTcp();
  void closeTcp();

  int    m_pythonPort = 8001;
  SOCKET m_frameSock  = INVALID_SOCKET;
  std::mutex m_tcpMutex;
};
