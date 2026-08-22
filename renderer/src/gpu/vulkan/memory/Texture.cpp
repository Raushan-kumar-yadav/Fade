#include "Texture.hpp"
#include "core/api/logger.hpp"
#include "core/gpu/vulkan/command/CommandBuffer.hpp"
#include "core/gpu/vulkan/command/CommandPool.hpp"
#include <stdexcept>

#include "stb/stb_image.h"

Texture::Texture(DeviceContext *context, CommandPool &commandPool,
                 VkQueue queue, uint8_t *pixels, VkDeviceSize imageSize,
                 int width, int height, int channels,
                 VkSamplerAddressMode addressMode, bool anisotropy)
    : m_context(context), m_image(VK_NULL_HANDLE),
      m_imageMemory(VK_NULL_HANDLE), m_imageView(VK_NULL_HANDLE),
      m_sampler(VK_NULL_HANDLE), m_height(height), m_width(width),
      m_channels(channels), m_imageSize(imageSize), m_addressMode(addressMode),
      m_anisotropy(anisotropy) {
  if (!pixels) {
    LOG_ERROR("Didn't receive the texture");
    throw std::runtime_error("Didn't receive the texture!");
  }

  if (m_channels == 1) {
    m_format = VK_FORMAT_R8_UNORM;
  } else if (m_channels == 2) {
    m_format = VK_FORMAT_R8G8_UNORM; // NV12 UV plane
  } else if (m_channels == 3) {
    m_format = VK_FORMAT_R8G8B8_UNORM;
  }

  else if (m_channels == 4) {
    m_format = VK_FORMAT_R8G8B8A8_UNORM;
  } else {
    throw std::runtime_error("Unsupported channel count!");
  }

  VkBufferCreateInfo bufferInfo{};
  bufferInfo.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
  bufferInfo.size = m_imageSize;
  bufferInfo.usage = VK_BUFFER_USAGE_TRANSFER_SRC_BIT;
  bufferInfo.sharingMode = VK_SHARING_MODE_EXCLUSIVE;

  if (vkCreateBuffer(m_context->getLogicalDevice(), &bufferInfo, nullptr,
                     &m_stagingBuffer) != VK_SUCCESS) {
    throw std::runtime_error("Failed to create staging buffer!");
  }

  VkMemoryRequirements memRequirements;
  vkGetBufferMemoryRequirements(m_context->getLogicalDevice(), m_stagingBuffer,
                                &memRequirements);

  VkMemoryAllocateInfo allocInfo{};
  allocInfo.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
  allocInfo.allocationSize = memRequirements.size;
  allocInfo.memoryTypeIndex = findMemoryType(
      memRequirements.memoryTypeBits, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT |
                                          VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);

  vkAllocateMemory(m_context->getLogicalDevice(), &allocInfo, nullptr,
                   &m_stagingBufferMemory);
  vkBindBufferMemory(m_context->getLogicalDevice(), m_stagingBuffer,
                     m_stagingBufferMemory, 0);

  //   Map the memory
  vkMapMemory(m_context->getLogicalDevice(), m_stagingBufferMemory, 0,
              m_imageSize, 0, &m_mappedData);

  // Copy pixels
  memcpy(m_mappedData, pixels, static_cast<size_t>(m_imageSize));

  createImage(m_width, m_height, m_format, VK_IMAGE_TILING_OPTIMAL,
              VK_IMAGE_USAGE_TRANSFER_SRC_BIT |
                  VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_SAMPLED_BIT,
              VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT, m_image, m_imageMemory);

  transitionImageLayout(commandPool, queue, m_image, m_format,
                        VK_IMAGE_LAYOUT_UNDEFINED,
                        VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL);
  copyBufferToImage(commandPool, queue, m_stagingBuffer, m_image,
                    static_cast<uint32_t>(m_width),
                    static_cast<uint32_t>(m_height));
  transitionImageLayout(commandPool, queue, m_image, m_format,
                        VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
                        VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL);

  // Create View & Sampler
  createImageView(m_format, VK_IMAGE_ASPECT_COLOR_BIT);
  createTextureSampler();

  LOG_INFO("Texture Transferred & Persistently Mapped");
}

Texture::~Texture() {
  if (m_context && m_context->getLogicalDevice()) {
    vkDeviceWaitIdle(m_context->getLogicalDevice());
  }

  if (m_mappedData) {
    vkUnmapMemory(m_context->getLogicalDevice(), m_stagingBufferMemory);
  }
  if (m_stagingBuffer) {
    vkDestroyBuffer(m_context->getLogicalDevice(), m_stagingBuffer, nullptr);
    vkFreeMemory(m_context->getLogicalDevice(), m_stagingBufferMemory, nullptr);
  }

  if (m_pendingCmd != VK_NULL_HANDLE && m_pendingPool != VK_NULL_HANDLE) {
    vkFreeCommandBuffers(m_context->getLogicalDevice(), m_pendingPool, 1,
                         &m_pendingCmd);
    m_pendingCmd = VK_NULL_HANDLE;
  }

  vkDestroySampler(m_context->getLogicalDevice(), m_sampler, nullptr);
  vkDestroyImageView(m_context->getLogicalDevice(), m_imageView, nullptr);
  vkDestroyImage(m_context->getLogicalDevice(), m_image, nullptr);
  vkFreeMemory(m_context->getLogicalDevice(), m_imageMemory, nullptr);

  if (m_uploadSemaphore != VK_NULL_HANDLE) {
    vkDestroySemaphore(m_context->getLogicalDevice(), m_uploadSemaphore,
                       nullptr);
    m_uploadSemaphore = VK_NULL_HANDLE;
  }
}

void Texture::transitionImageLayout(CommandPool &commandPool, VkQueue queue,
                                    VkImage image, VkFormat format,
                                    VkImageLayout oldLayout,
                                    VkImageLayout newLayout) {

  CommandBuffer cmd(commandPool, true);
  cmd.begin(VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT);

  VkImageMemoryBarrier barrier{};
  barrier.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
  barrier.oldLayout = oldLayout;
  barrier.newLayout = newLayout;
  barrier.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
  barrier.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
  barrier.image = image;
  barrier.subresourceRange.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
  barrier.subresourceRange.baseMipLevel = 0;
  barrier.subresourceRange.levelCount = 1;
  barrier.subresourceRange.baseArrayLayer = 0;
  barrier.subresourceRange.layerCount = 1;

  VkPipelineStageFlags sourceStage;
  VkPipelineStageFlags destinationStage;

  if (oldLayout == VK_IMAGE_LAYOUT_UNDEFINED &&
      newLayout == VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL) {
    barrier.srcAccessMask = 0;
    barrier.dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
    sourceStage = VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT;
    destinationStage = VK_PIPELINE_STAGE_TRANSFER_BIT;
  } else if (oldLayout == VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL &&
             newLayout == VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL) {
    barrier.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
    barrier.dstAccessMask = VK_ACCESS_SHADER_READ_BIT;
    sourceStage = VK_PIPELINE_STAGE_TRANSFER_BIT;
    destinationStage = VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT;
  } else if (oldLayout == VK_IMAGE_LAYOUT_GENERAL &&
             newLayout == VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL) {
    barrier.srcAccessMask = VK_ACCESS_SHADER_READ_BIT;
    barrier.dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
    sourceStage = VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT;
    destinationStage = VK_PIPELINE_STAGE_TRANSFER_BIT;
  } else if (oldLayout == VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL &&
             newLayout == VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL) {
    barrier.srcAccessMask = VK_ACCESS_SHADER_READ_BIT;
    barrier.dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
    sourceStage = VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT;
    destinationStage = VK_PIPELINE_STAGE_TRANSFER_BIT;
  } else if (oldLayout == VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL &&
             newLayout == VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL) {
    barrier.srcAccessMask = VK_ACCESS_TRANSFER_READ_BIT;
    barrier.dstAccessMask = VK_ACCESS_SHADER_READ_BIT;
    sourceStage = VK_PIPELINE_STAGE_TRANSFER_BIT;
    destinationStage = VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT;
  } else if (oldLayout == VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL &&
             newLayout == VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL) {
    barrier.srcAccessMask = VK_ACCESS_TRANSFER_READ_BIT;
    barrier.dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
    sourceStage = VK_PIPELINE_STAGE_TRANSFER_BIT;
    destinationStage = VK_PIPELINE_STAGE_TRANSFER_BIT;
  } else {
    throw std::invalid_argument("Unsupported layout transition!");
  }

  vkCmdPipelineBarrier(cmd.getHandle(), sourceStage, destinationStage, 0, 0,
                       nullptr, 0, nullptr, 1, &barrier);
  cmd.end();

  VkSubmitInfo submitInfo{};
  submitInfo.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
  submitInfo.commandBufferCount = 1;
  VkCommandBuffer rawCmd = cmd.getHandle();
  submitInfo.pCommandBuffers = &rawCmd;

  m_context->lockGraphicsQueue();
  vkQueueSubmit(queue, 1, &submitInfo, VK_NULL_HANDLE);
  vkQueueWaitIdle(queue);
  m_context->unlockGraphicsQueue();

  // Track the new layout if this transition was for our own image
  if (image == m_image) {
    m_currentLayout = newLayout;
  }
}

void Texture::copyBufferToImage(CommandPool &commandPool, VkQueue queue,
                                VkBuffer buffer, VkImage image, uint32_t width,
                                uint32_t height) {

  CommandBuffer cmd(commandPool, true);
  cmd.begin(VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT);

  VkBufferImageCopy region{};
  region.bufferOffset = 0;
  region.bufferRowLength = 0;
  region.bufferImageHeight = 0;
  region.imageSubresource.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
  region.imageSubresource.mipLevel = 0;
  region.imageSubresource.baseArrayLayer = 0;
  region.imageSubresource.layerCount = 1;
  region.imageOffset = {0, 0, 0};
  region.imageExtent = {width, height, 1};

  vkCmdCopyBufferToImage(cmd.getHandle(), buffer, image,
                         VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &region);
  cmd.end();

  VkSubmitInfo submitInfo{};
  submitInfo.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
  submitInfo.commandBufferCount = 1;
  VkCommandBuffer rawCmd = cmd.getHandle();
  submitInfo.pCommandBuffers = &rawCmd;

  m_context->lockGraphicsQueue();
  vkQueueSubmit(queue, 1, &submitInfo, VK_NULL_HANDLE);
  vkQueueWaitIdle(queue);
  m_context->unlockGraphicsQueue();
}

void Texture::updatePixels(CommandPool &commandPool, VkQueue queue,
                           uint8_t *pixels, VkDeviceSize imageSize) {
  if (!pixels || imageSize > m_imageSize)
    return;

  memcpy(m_mappedData, pixels, static_cast<size_t>(imageSize));

  {
    CommandBuffer cmd(commandPool, true);
    cmd.begin(VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT);

    VkImageMemoryBarrier barrier{};
    barrier.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
    barrier.srcAccessMask = 0;
    barrier.dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
    barrier.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    barrier.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    barrier.image = m_image;
    barrier.subresourceRange.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
    barrier.subresourceRange.baseMipLevel = 0;
    barrier.subresourceRange.levelCount = 1;
    barrier.subresourceRange.baseArrayLayer = 0;
    barrier.subresourceRange.layerCount = 1;

    barrier.oldLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    barrier.newLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
    barrier.srcAccessMask = 0;
    barrier.dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;

    vkCmdPipelineBarrier(cmd.getHandle(), VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,
                         VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, nullptr, 0,
                         nullptr, 1, &barrier);

    VkBufferImageCopy region{};
    region.bufferOffset = 0;
    region.imageSubresource.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
    region.imageSubresource.layerCount = 1;
    region.imageExtent = {static_cast<uint32_t>(m_width),
                          static_cast<uint32_t>(m_height), 1};
    vkCmdCopyBufferToImage(cmd.getHandle(), m_stagingBuffer, m_image,
                           VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &region);

    barrier.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
    barrier.newLayout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;
    barrier.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
    barrier.dstAccessMask = VK_ACCESS_SHADER_READ_BIT;

    vkCmdPipelineBarrier(cmd.getHandle(), VK_PIPELINE_STAGE_TRANSFER_BIT,
                         VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT, 0, 0, nullptr,
                         0, nullptr, 1, &barrier);

    cmd.end();

    VkSubmitInfo submitInfo{};
    submitInfo.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
    submitInfo.commandBufferCount = 1;
    VkCommandBuffer rawCmd = cmd.getHandle();
    submitInfo.pCommandBuffers = &rawCmd;

    VkFenceCreateInfo fenceInfo{};
    fenceInfo.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO;
    VkFence uploadFence = VK_NULL_HANDLE;
    vkCreateFence(m_context->getLogicalDevice(), &fenceInfo, nullptr,
                  &uploadFence);

    m_context->lockGraphicsQueue();
    vkQueueSubmit(queue, 1, &submitInfo, uploadFence);
    m_context->unlockGraphicsQueue();

    vkWaitForFences(m_context->getLogicalDevice(), 1, &uploadFence, VK_TRUE,
                    UINT64_MAX);
    vkDestroyFence(m_context->getLogicalDevice(), uploadFence, nullptr);
  }
}

VkSemaphore Texture::updatePixelsAsync(CommandPool &transferPool,
                                       VkQueue transferQueue, uint8_t *pixels,
                                       VkDeviceSize imageSize) {
  if (!pixels || imageSize > m_imageSize)
    return VK_NULL_HANDLE;

  memcpy(m_mappedData, pixels, static_cast<size_t>(imageSize));

  if (m_uploadSemaphore == VK_NULL_HANDLE) {
    VkSemaphoreCreateInfo si{};
    si.sType = VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO;
    vkCreateSemaphore(m_context->getLogicalDevice(), &si, nullptr,
                      &m_uploadSemaphore);
  }

  VkCommandPool rawPool = transferPool.getHandle();
  VkCommandBufferAllocateInfo allocInfo{};
  allocInfo.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
  allocInfo.commandPool = rawPool;
  allocInfo.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
  allocInfo.commandBufferCount = 1;

  VkCommandBuffer cmd = VK_NULL_HANDLE;
  vkAllocateCommandBuffers(m_context->getLogicalDevice(), &allocInfo, &cmd);

  VkCommandBufferBeginInfo beginInfo{};
  beginInfo.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
  beginInfo.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
  vkBeginCommandBuffer(cmd, &beginInfo);

  // Transition: UNDEFINED → TRANSFER_DST (discard old content — safe for
  // full-image overwrite on every frame).
  VkImageMemoryBarrier toTransfer{};
  toTransfer.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
  toTransfer.srcAccessMask = 0;
  toTransfer.dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
  toTransfer.oldLayout = VK_IMAGE_LAYOUT_UNDEFINED;
  toTransfer.newLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
  toTransfer.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
  toTransfer.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
  toTransfer.image = m_image;
  toTransfer.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
  vkCmdPipelineBarrier(cmd, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,
                       VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, nullptr, 0,
                       nullptr, 1, &toTransfer);

  VkBufferImageCopy region{};
  region.bufferOffset = 0;
  region.imageSubresource.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
  region.imageSubresource.layerCount = 1;
  region.imageExtent = {static_cast<uint32_t>(m_width),
                        static_cast<uint32_t>(m_height), 1};
  vkCmdCopyBufferToImage(cmd, m_stagingBuffer, m_image,
                         VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &region);

  // Transition TRANSFER_DST → SHADER_READ_ONLY_OPTIMAL so it matches the
  // layout we report to Skia in wrapRGBAToSkImage.
  VkImageMemoryBarrier toShader{};
  toShader.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
  toShader.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
  toShader.dstAccessMask = 0;
  toShader.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
  toShader.newLayout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;
  toShader.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
  toShader.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
  toShader.image = m_image;
  toShader.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
  vkCmdPipelineBarrier(cmd, VK_PIPELINE_STAGE_TRANSFER_BIT,
                       VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT, 0, 0, nullptr, 0,
                       nullptr, 1, &toShader);

  vkEndCommandBuffer(cmd);

  VkSubmitInfo submitInfo{};
  submitInfo.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
  submitInfo.commandBufferCount = 1;
  submitInfo.pCommandBuffers = &cmd;
  submitInfo.signalSemaphoreCount = 1;
  submitInfo.pSignalSemaphores = &m_uploadSemaphore;

  m_context->lockTransferQueue();
  vkQueueSubmit(transferQueue, 1, &submitInfo, VK_NULL_HANDLE);
  m_context->unlockTransferQueue();

  m_pendingCmd = cmd;
  m_pendingPool = rawPool;
  m_currentLayout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;

  return m_uploadSemaphore;
}

void Texture::createImage(uint32_t width, uint32_t height, VkFormat format,
                          VkImageTiling tiling, VkImageUsageFlags usage,
                          VkMemoryPropertyFlags properties, VkImage &image,
                          VkDeviceMemory &imageMemory) {
  VkImageCreateInfo imageInfo{};
  imageInfo.sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO;
  imageInfo.imageType = VK_IMAGE_TYPE_2D;
  imageInfo.extent.width = width;
  imageInfo.extent.height = height;
  imageInfo.extent.depth = 1;
  imageInfo.mipLevels = 1;
  imageInfo.arrayLayers = 1;
  imageInfo.format = format;
  imageInfo.tiling = tiling;
  imageInfo.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
  imageInfo.usage = usage;
  imageInfo.samples = VK_SAMPLE_COUNT_1_BIT;
  imageInfo.sharingMode = VK_SHARING_MODE_EXCLUSIVE;

  if (vkCreateImage(m_context->getLogicalDevice(), &imageInfo, nullptr,
                    &image) != VK_SUCCESS)
    throw std::runtime_error("Failed to create image!");

  VkMemoryRequirements memRequirements;
  vkGetImageMemoryRequirements(m_context->getLogicalDevice(), image,
                               &memRequirements);

  VkMemoryAllocateInfo allocInfo{};
  allocInfo.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
  allocInfo.allocationSize = memRequirements.size;
  allocInfo.memoryTypeIndex =
      findMemoryType(memRequirements.memoryTypeBits, properties);

  if (vkAllocateMemory(m_context->getLogicalDevice(), &allocInfo, nullptr,
                       &imageMemory) != VK_SUCCESS)
    throw std::runtime_error("Failed to allocate memory!");

  vkBindImageMemory(m_context->getLogicalDevice(), image, imageMemory, 0);
}

void Texture::createImageView(VkFormat format, VkImageAspectFlags aspectFlags) {
  VkImageViewCreateInfo viewInfo{};
  viewInfo.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO;
  viewInfo.image = m_image;
  viewInfo.viewType = VK_IMAGE_VIEW_TYPE_2D;
  viewInfo.format = format;
  viewInfo.subresourceRange.aspectMask = aspectFlags;
  viewInfo.subresourceRange.baseMipLevel = 0;
  viewInfo.subresourceRange.levelCount = 1;
  viewInfo.subresourceRange.baseArrayLayer = 0;
  viewInfo.subresourceRange.layerCount = 1;

  if (vkCreateImageView(m_context->getLogicalDevice(), &viewInfo, nullptr,
                        &m_imageView) != VK_SUCCESS)
    throw std::runtime_error("Failed to create view!");
}

void Texture::createTextureSampler() {
  VkPhysicalDeviceProperties properties{};
  vkGetPhysicalDeviceProperties(m_context->getPhysicalDevice(), &properties);

  VkSamplerCreateInfo samplerInfo{};
  samplerInfo.sType = VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO;
  samplerInfo.magFilter = VK_FILTER_LINEAR;
  samplerInfo.minFilter = VK_FILTER_LINEAR;
  samplerInfo.addressModeU = m_addressMode;
  samplerInfo.addressModeV = m_addressMode;
  samplerInfo.addressModeW = m_addressMode;
  samplerInfo.anisotropyEnable = m_anisotropy ? VK_TRUE : VK_FALSE;
  samplerInfo.maxAnisotropy =
      m_anisotropy ? properties.limits.maxSamplerAnisotropy : 1.0f;
  samplerInfo.borderColor = VK_BORDER_COLOR_INT_OPAQUE_BLACK;
  samplerInfo.unnormalizedCoordinates = VK_FALSE;
  samplerInfo.compareEnable = VK_FALSE;
  samplerInfo.compareOp = VK_COMPARE_OP_ALWAYS;
  samplerInfo.mipmapMode = VK_SAMPLER_MIPMAP_MODE_LINEAR;
  samplerInfo.maxLod = VK_LOD_CLAMP_NONE;

  if (vkCreateSampler(m_context->getLogicalDevice(), &samplerInfo, nullptr,
                      &m_sampler) != VK_SUCCESS)
    throw std::runtime_error("Failed to create sampler!");
}

uint32_t Texture::findMemoryType(uint32_t typeFilter,
                                 VkMemoryPropertyFlags properties) {
  VkPhysicalDeviceMemoryProperties memProperties;
  vkGetPhysicalDeviceMemoryProperties(m_context->getPhysicalDevice(),
                                      &memProperties);

  for (uint32_t i = 0; i < memProperties.memoryTypeCount; i++) {
    if ((typeFilter & (1 << i)) && (memProperties.memoryTypes[i].propertyFlags &
                                    properties) == properties) {
      return i;
    }
  }
  throw std::runtime_error("Failed to find suitable memory type!");
}