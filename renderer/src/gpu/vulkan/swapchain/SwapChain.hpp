#pragma once
#include "core/api/Logger.hpp"
#include "core/gpu/vulkan/device/DeviceContext.hpp"
#include <vector>
#include <vulkan/vulkan.h>

struct SwapChainDetails {
  VkSurfaceCapabilitiesKHR surfaceCapabilities;
  std::vector<VkSurfaceFormatKHR> formats;
  std::vector<VkPresentModeKHR> presentationModes;
};

class Swapchain {
private:
  DeviceContext *m_device;
  VkSwapchainKHR m_swapchain = VK_NULL_HANDLE;

  VkFormat m_imageFormat;
  VkExtent2D m_extent;
  VkImageUsageFlags m_imageUsageFlags = 0;

  std::vector<VkImage> m_images;
  std::vector<VkImageView> m_imageViews;

  std::vector<VkFramebuffer> m_framebuffers;

  void create(uint32_t width, uint32_t height);
  void cleanup();

  // Helpers
  SwapChainDetails getSwapchainDetails(VkPhysicalDevice phyicalDevice,
                                       VkSurfaceKHR surface);
  VkSurfaceFormatKHR chooseSwapSurfaceFormat(
      const std::vector<VkSurfaceFormatKHR> &availableFormats);
  VkPresentModeKHR chooseSwapPresentMode(
      const std::vector<VkPresentModeKHR> &availablePresentModes);
  VkExtent2D chooseSwapExtent(const VkSurfaceCapabilitiesKHR &capabilities,
                              uint32_t width, uint32_t height);

public:
  Swapchain(DeviceContext *deviceContext, uint32_t widht, uint32_t height);
  ~Swapchain();

  void recreate(uint32_t width, uint32_t height);

  // Getters for the Renderer to use
  VkSwapchainKHR getHandle() const { return m_swapchain; }
  VkFormat getImageFormat() const { return m_imageFormat; }
  VkExtent2D getExtent() const { return m_extent; }
  VkImageUsageFlags getImageUsageFlags() const { return m_imageUsageFlags; }

  std::vector<VkImage> getImages() const { return m_images; }

  const std::vector<VkImageView> &getImageViews() const { return m_imageViews; }
  size_t getImageCount() const { return m_images.size(); }

  VkFramebuffer getFramebuffer(uint32_t index) const {
    return m_framebuffers[index];
  }
  void setupFramebuffers(VkRenderPass renderPass);
};
