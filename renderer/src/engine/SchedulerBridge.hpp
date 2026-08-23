#pragma once
#include <cstdint>
#include <vector>
#include <string>

// ── Thin wrapper around DecodeScheduler for HeadlessCompositor ──
// Exists to avoid header conflicts: HeadlessCompositor uses local
// DecodedFrame.hpp while DecodeScheduler uses the VK_SRC (core/) copy.
// By isolating scheduler calls in a separate .cpp, each translation
// unit only sees one copy of DecodedFrame.

struct CachedFrameData {
    const uint8_t *data = nullptr;  // Points into the shared_ptr (valid while held)
    size_t dataSize = 0;
    uint32_t width = 0;
    uint32_t height = 0;
    bool valid = false;

    // Opaque handle to keep the shared_ptr alive
    void *_handle = nullptr;
};

// Returns cached frame RGBA pixels if available.
// The returned data pointer is valid until releaseCachedFrame() is called.
CachedFrameData tryGetCachedFrame(const std::string &clipId, int64_t frame);
void releaseCachedFrame(CachedFrameData &cfd);

// Registers a video/image clip for async pre-decode.
void schedRegisterVideo(const std::string &clipId, const std::string &filepath);
void schedRegisterImage(const std::string &clipId, const std::string &filepath);

// Triggers prefetch of frames around anchor.
void schedPrefetchAround(const std::string &clipId, int64_t anchorFrame, int radius = 8);

// Sets the Vulkan device context for HW decode in the scheduler's pool.
void schedSetDeviceContext(void *deviceCtx);
