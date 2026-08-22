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
#include <thread>

#include <winsock2.h> // persistent TCP socket
#include <ws2tcpip.h>
#pragma comment(lib, "ws2_32.lib")

class HeadlessCompositor {
public:
  using FrameReadyCallback = std::function<void(int64_t frameNum)>;

  HeadlessCompositor(int width, int height, float fps,
                     const std::string &effectsDir = "");
  ~HeadlessCompositor();

  // Non-copyable
  HeadlessCompositor(const HeadlessCompositor &) = delete;
  HeadlessCompositor &operator=(const HeadlessCompositor &) = delete;

  // Called from NAPI bridge — enqueues a render request
  void renderFrame(const FrameDescriptor &fd);

  // Playback control
  void play();
  void pause();
  bool isPlaying() const { return m_playing.load(); }

  // Seek to a specific frame (renders one frame immediately)
  void seek(int64_t frame);

  // Export API: synchronous frame render → raw RGBA bytes (w*h*4).
  // Blocks until composited. Do NOT call during play loop.
  std::vector<uint8_t> exportFrameSync(int64_t frameNum);

  // Access the output buffer (BGRA, width*height*4 bytes)
  uint8_t *getBuffer() const { return m_buffer.get(); }
  size_t getBufferSize() const { return m_bufferSize; }

  void setFrameReadyCallback(FrameReadyCallback cb) {
    m_onFrameReady = std::move(cb);
  }
  void setPythonPort(int port) {
    if (m_pythonPort != port) {
      m_pythonPort = port;
      closeTcp();
    }
  }

  int width() const { return m_width; }
  int height() const { return m_height; }
  float fps() const { return m_fps; }

private:
  //   Initialization
  void init(const std::string &effectsDir);
  void shutdown();

  //   Core render
  void doRender(const FrameDescriptor &fd);

  // Draw a video/image clip onto canvas
  void drawClipOnCanvas(SkCanvas *canvas, const ClipDesc &clip,
                        const uint8_t *rgba, int imgW, int imgH, bool useGpu);

  // Apply SkSL effects to a clip image
  sk_sp<SkImage> applyEffects(sk_sp<SkImage> src, const ClipDesc &clip);
  std::vector<uint8_t> exortFramesync(int64_t frameNum);

  //   Members
  int m_width;
  int m_height;
  float m_fps;

  std::unique_ptr<DeviceContext> m_device;
  std::unique_ptr<SkiaContext> m_skia;

  // Per-file decoder cache
  std::unordered_map<std::string, std::unique_ptr<ClipDecoder>> m_decoders;

  // Skia offscreen surface
  sk_sp<SkSurface> m_surface;

  std::unique_ptr<uint8_t[]> m_buffer;       // front: JS reads
  std::unique_ptr<uint8_t[]> m_renderBuffer; // back:  C++ writes
  size_t m_bufferSize = 0;

  std::atomic<bool> m_playing{false};
  std::atomic<int64_t> m_currentFrame{0};
  std::atomic<uint64_t> m_seekGeneration{0}; // incremented on each seek
  std::thread m_playThread;
  FrameReadyCallback m_onFrameReady;
  std::mutex m_renderMutex;

  // immediately
  std::mutex m_sleepMutex;
  std::condition_variable m_sleepCv;

  std::string fetchFrameJson(int64_t frameNum);
  bool connectTcp(); // lazy-connect once
  void closeTcp();   // called on shutdown
  int m_pythonPort = 8001;

  SOCKET m_frameSock = INVALID_SOCKET;
  std::mutex m_tcpMutex; // serialize send+recv
};
