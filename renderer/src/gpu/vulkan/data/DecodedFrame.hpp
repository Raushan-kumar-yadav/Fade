#pragma once
#include <vector>
#include <vulkan/vulkan.h>

extern "C" {
#include <libavutil/frame.h>
}

enum class FrameType {
  SOFTWARE_YUV,
  HARDWARE_VULKAN,
  HARDWARE_CACHED,
  SOFTWARE_RGBA
};

struct DecodedFrame {
  // Hybrid tracking
  FrameType type = FrameType::SOFTWARE_YUV;

  // Standard Metadata
  int64_t frameNumber = -1; // which frame in source video
  int64_t pts = 0;          // Presentation Timestamp from FFmpeg
  uint32_t width = 0;       // width
  uint32_t height = 0;      // height
  int channels = 4;         // RGBA = 4
  bool isStatic = false;
  bool valid = false; //  decode successful or not

  // CPU Frame Data (Software YUV I420)
  std::vector<uint8_t> dataY;
  std::vector<uint8_t> dataU;
  std::vector<uint8_t> dataV;

  // CPU Frame Data (HW-decoded NV12, downloaded from GPU)
  std::vector<uint8_t> dataNV12Y;  // Luma plane
  std::vector<uint8_t> dataNV12UV; // Interleaved chroma plane

  // RGBA data for image
  std::vector<uint8_t> dataRGBA;

  // GPU Frame Data
  VkImage vkImage = VK_NULL_HANDLE;
  VkSemaphore readySemaphore = VK_NULL_HANDLE;
  uint64_t readySemaphoreValue = 0;
  VkImageLayout currentLayout = VK_IMAGE_LAYOUT_UNDEFINED;

  // FFmpeg HW Context
  AVFrame *hwAvFrame = nullptr;

  // Destructor
  ~DecodedFrame() {

    if (hwAvFrame) {
      av_frame_free(&hwAvFrame);
    }
  }

  bool isEmpty() const {
    if (type == FrameType::SOFTWARE_YUV) {
      return dataY.empty();
    } else if (type == FrameType::SOFTWARE_RGBA) {
      return dataRGBA.empty();
    } else if (type == FrameType::HARDWARE_CACHED) {
      return dataNV12Y.empty();
    } else {
      return vkImage == VK_NULL_HANDLE;
    }
  }

  // Getters
  uint32_t getWidth() const { return width; }
  uint32_t getHeight() const { return height; }
  bool getIsStatic() const { return isStatic; }
  uint64_t sizeBytes() const {
    if (type == FrameType::SOFTWARE_RGBA) {
      return static_cast<uint64_t>(width) * height * 4; // 4 bytes per pixel
    }
    if (type == FrameType::HARDWARE_CACHED) {
      // NV12: Y plane (w*h) + UV plane (w*h/2)
      return dataNV12Y.size() + dataNV12UV.size();
    }
    if (type == FrameType::HARDWARE_VULKAN) {
      // Live GPU frame — estimate NV12 size for budget accounting
      uint64_t luma = static_cast<uint64_t>(width) * height;
      return luma + luma / 2;
    }
    // SOFTWARE_YUV: I420 calculation
    uint64_t luma = static_cast<uint64_t>(width) * height;
    uint64_t chroma = luma / 2;
    return luma + chroma;
  }
};