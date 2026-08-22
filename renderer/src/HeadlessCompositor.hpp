#pragma once
#include "gpu/vulkan/device/DeviceContext.hpp"
#include "gpu/vulkan/skia/SkiaContext.hpp"
#include "video/ClipDecoder.hpp"
#include "napi/FrameDescriptor.hpp"

#include <core/SkCanvas.h>
#include <core/SkSurface.h>
#include <core/SkImage.h>
#include <core/SkBitmap.h>
#include <core/SkColorSpace.h>
#include <core/SkColorType.h>
#include <core/SkImageInfo.h>
#include <effects/SkRuntimeEffect.h>
#include <gpu/ganesh/GrDirectContext.h>
#include <gpu/ganesh/SkSurfaceGanesh.h>

#include <atomic>
#include <functional>
#include <memory>
#include <condition_variable>
#include <mutex>
#include <thread>
#include <cstdint>

#include <winsock2.h>    // persistent TCP socket — replaces WinHTTP
#include <ws2tcpip.h>
#pragma comment(lib, "ws2_32.lib")

/**
 * HeadlessCompositor
 *
 * Owns the Vulkan device + Skia GPU context. On each renderFrame() call:
 *   1. Reads the FrameDescriptor (clip list from Python)
 *   2. Fetches decoded frames from DecodeScheduler (D3D11VA / CPU)
 *   3. Draws each clip onto an SkSurface backed by a Vulkan texture
 *   4. Applies SkSL effects via SkRuntimeEffect (same shaders as before)
 *   5. Reads back pixels to the SharedArrayBuffer (CPU)
 *
 * The SharedArrayBuffer pointer is shared with the Electron renderer process
 * via NAPI — zero-copy from JS perspective.
 */
class HeadlessCompositor {
public:
    using FrameReadyCallback = std::function<void(int64_t frameNum)>;

    HeadlessCompositor(int width, int height, float fps,
                       const std::string& effectsDir = "");
    ~HeadlessCompositor();

    // Non-copyable
    HeadlessCompositor(const HeadlessCompositor&) = delete;
    HeadlessCompositor& operator=(const HeadlessCompositor&) = delete;

    // Called from NAPI bridge — enqueues a render request
    void renderFrame(const FrameDescriptor& fd);

    // Playback control
    void play();
    void pause();
    bool isPlaying() const { return m_playing.load(); }

    // Seek to a specific frame (renders one frame immediately)
    void seek(int64_t frame);

    // Access the output buffer (BGRA, width*height*4 bytes)
    uint8_t*  getBuffer() const  { return m_buffer.get(); }
    size_t    getBufferSize() const { return m_bufferSize; }

    void setFrameReadyCallback(FrameReadyCallback cb) { m_onFrameReady = std::move(cb); }
    void setPythonPort(int port) {
        if (m_pythonPort != port) {
            m_pythonPort = port;
            closeTcp();  // force reconnect on next fetchFrameJson
        }
    }

    int   width()  const { return m_width; }
    int   height() const { return m_height; }
    float fps()    const { return m_fps; }

private:
    // ── Initialization ────────────────────────────────────────────────────────
    void init(const std::string& effectsDir);
    void shutdown();

    // ── Core render ──────────────────────────────────────────────────────────
    void doRender(const FrameDescriptor& fd);

    // Draw a single clip onto canvas (useGpu=true enables SkSL effects)
    void drawClipOnCanvas(SkCanvas* canvas, const ClipDesc& clip, const uint8_t* rgba, int imgW, int imgH, bool useGpu);

    // Apply SkSL effects to a clip image
    sk_sp<SkImage> applyEffects(sk_sp<SkImage> src, const ClipDesc& clip);

    // ── Members ──────────────────────────────────────────────────────────────
    int   m_width;
    int   m_height;
    float m_fps;

    std::unique_ptr<DeviceContext>   m_device;
    std::unique_ptr<SkiaContext>     m_skia;

    // Per-file decoder cache — lazily created on first access
    std::unordered_map<std::string, std::unique_ptr<ClipDecoder>> m_decoders;

    // Skia offscreen surface (Vulkan-backed)
    sk_sp<SkSurface> m_surface;

    // Output CPU buffer — this is the SharedArrayBuffer exposed to Electron
    std::unique_ptr<uint8_t[]> m_buffer;
    size_t m_bufferSize = 0;

    std::atomic<bool>     m_playing{false};
    std::atomic<int64_t>  m_currentFrame{0};
    std::atomic<uint64_t> m_seekGeneration{0};  // incremented on each seek
    std::thread           m_playThread;
    FrameReadyCallback    m_onFrameReady;
    std::mutex            m_renderMutex;

    // Interruptible sleep: pause()/seek() signal this to wake play thread immediately
    std::mutex              m_sleepMutex;
    std::condition_variable m_sleepCv;

    // Fetch frame descriptor via persistent TCP socket (port = pythonPort+1)
    // Protocol: send uint32_t frameNum (LE), receive uint32_t len (LE) + JSON
    std::string fetchFrameJson(int64_t frameNum);
    bool        connectTcp();   // lazy-connect once
    void        closeTcp();     // called on shutdown
    int         m_pythonPort = 8001;

    SOCKET m_frameSock = INVALID_SOCKET;  // persistent, reused every frame
};
