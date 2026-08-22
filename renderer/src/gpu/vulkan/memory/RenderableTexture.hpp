#pragma once
#include "core/gpu/vulkan/memory/Texture.hpp"
#include "core/gpu/vulkan/pipeline/Descriptor.hpp"
#include "core/video/decoder/baseDecoder.hpp"
#include <glm/glm.hpp>
#include <memory>
#include <vulkan/vulkan.h>

struct RenderableTexture {
  FrameType type = FrameType::SOFTWARE_YUV;
  int64_t currentFrameOnGPU = -1;
  std::shared_ptr<Descriptor> descriptor;

  // SOFTWARE
  std::shared_ptr<Texture> texY;
  std::shared_ptr<Texture> texU;
  std::shared_ptr<Texture> texV;

  std::shared_ptr<Texture> texRGBA;

  // HARDWARE VARIABLES
  VkImage hwImage = VK_NULL_HANDLE;
  VkImageView hwImageView = VK_NULL_HANDLE;   // Y plane (PLANE_0)
  VkImageView hwUVImageView = VK_NULL_HANDLE; // UV plane (PLANE_1, NV12)
  VkSemaphore hwReadySemaphore = VK_NULL_HANDLE;
  uint64_t hwReadySemaphoreValue = 0;
  VkImageLayout hwLayout = VK_IMAGE_LAYOUT_UNDEFINED;
  int width = 0;
  int height = 0;

  // clean up
  DeviceContext *context = nullptr;
  ~RenderableTexture() {
    if (hwImageView != VK_NULL_HANDLE && context != nullptr) {
      vkDestroyImageView(context->getLogicalDevice(), hwImageView, nullptr);
    }
    if (hwUVImageView != VK_NULL_HANDLE && context != nullptr) {
      vkDestroyImageView(context->getLogicalDevice(), hwUVImageView, nullptr);
    }
  }
};