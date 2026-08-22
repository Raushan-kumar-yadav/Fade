#pragma once

#include "core/gpu/vulkan/command/CommandPool.hpp"
#include "core/gpu/vulkan/device/DeviceContext.hpp"
#include <string>
#include <vulkan/vulkan.h>

class Texture {
public:
  Texture(DeviceContext *context, CommandPool &commandPool, VkQueue queue,
          uint8_t *pixels, VkDeviceSize imageSize, int width, int height,
          int channels,
          VkSamplerAddressMode addressMode = VK_SAMPLER_ADDRESS_MODE_REPEAT,
          bool anisotropy = true);
  ~Texture();

  VkImageView getImageView() const { return m_imageView; }
  VkSampler getSampler() const { return m_sampler; }
  void updatePixels(CommandPool &commandPool, VkQueue queue, uint8_t *pixels,
                    VkDeviceSize imageSize);

  VkSemaphore updatePixelsAsync(CommandPool &transferPool,
                                VkQueue transferQueue, uint8_t *pixels,
                                VkDeviceSize imageSize);
  VkImage getImage() const { return m_image; }
  VkDeviceMemory getImageMemory() const { return m_imageMemory; }
  VkDeviceSize getImageSize() const { return m_imageSize; }
  VkFormat getFormat() const { return m_format; }
  int getWidth() const { return m_width; }
  int getHeight() const { return m_height; }

  void transitionImageLayout(CommandPool &commandPool, VkQueue queue,
                             VkImage image, VkFormat format,
                             VkImageLayout oldLayout, VkImageLayout newLayout);

private:
  VkFormat m_format;
  DeviceContext *m_context;

  int m_width, m_height, m_channels;

  VkImage m_image;
  VkDeviceMemory m_imageMemory;
  VkImageView m_imageView;
  VkSampler m_sampler;

  VkBuffer m_stagingBuffer = VK_NULL_HANDLE;
  VkDeviceMemory m_stagingBufferMemory = VK_NULL_HANDLE;
  void *m_mappedData = nullptr;
  VkDeviceSize m_imageSize = 0;
  VkSamplerAddressMode m_addressMode = VK_SAMPLER_ADDRESS_MODE_REPEAT;

  bool m_anisotropy = true;

public:
  VkImageLayout m_currentLayout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;

private:
  VkSemaphore m_uploadSemaphore = VK_NULL_HANDLE;
  VkCommandBuffer m_pendingCmd = VK_NULL_HANDLE;
  VkCommandPool m_pendingPool = VK_NULL_HANDLE;

  //  Helpers
  void createImage(uint32_t width, uint32_t height, VkFormat format,
                   VkImageTiling tiling, VkImageUsageFlags usage,
                   VkMemoryPropertyFlags properties, VkImage &image,
                   VkDeviceMemory &imageMemory);
  void createImageView(VkFormat format, VkImageAspectFlags aspectFlags);
  void createTextureSampler();

  void copyBufferToImage(CommandPool &commandPool, VkQueue queue,
                         VkBuffer buffer, VkImage image, uint32_t width,
                         uint32_t height);
  // Memory Helper
  uint32_t findMemoryType(uint32_t typeFilter,
                          VkMemoryPropertyFlags properties);
};