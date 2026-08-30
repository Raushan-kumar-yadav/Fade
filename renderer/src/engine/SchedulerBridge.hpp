#pragma once
#include <cstdint>
#include <string>
#include <vector>

struct CachedFrameData {
  const uint8_t *data = nullptr;
  size_t dataSize = 0;
  uint32_t width = 0;
  uint32_t height = 0;
  bool valid = false;

  void *_handle = nullptr;
};

CachedFrameData tryGetCachedFrame(const std::string &clipId, int64_t frame);
void releaseCachedFrame(CachedFrameData &cfd);

void schedRegisterVideo(const std::string &clipId, const std::string &filepath);
void schedRegisterImage(const std::string &clipId, const std::string &filepath);

void schedPrefetchAround(const std::string &clipId, int64_t anchorFrame,
                         int radius = 8);

void schedSetDeviceContext(void *deviceCtx);
void schedSetPreviewScale(float scale);

// Push externally-captured RGBA data
void schedPushFrame(const std::string &pseudoPath, int64_t frame,
                    const uint8_t *rgba, size_t dataSize, uint32_t width,
                    uint32_t height);
