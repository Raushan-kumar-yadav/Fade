#pragma once
#include "gpu/vulkan/data/DecodedFrame.hpp"
#include "gpu/vulkan/device/DeviceContext.hpp"
#include "video/HwVideoDecoder.hpp"
#include "video/baseDecoder.hpp"
#include "video/videoDecoder.hpp"

#include <cstdint>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

class ClipDecoder {
public:
  ClipDecoder(const std::string &filepath, DeviceContext *device,
              float previewScale = 1.0f);
  ~ClipDecoder() = default;

  struct DecodeResult {
    std::vector<uint8_t> rgba;
    int width = 0;
    int height = 0;
  };
  DecodeResult decodeFrame(int64_t frameNumber);

  bool decodeFrameDirect(int64_t frameNumber, uint8_t *dstBuffer, int dstW,
                         int dstH);

  int width() const;
  int height() const;
  double fps() const;
  double duration() const;

private:
  std::unique_ptr<baseDecoder> m_decoder;
  bool m_valid = false;
  float m_previewScale = 1.0f;
};
