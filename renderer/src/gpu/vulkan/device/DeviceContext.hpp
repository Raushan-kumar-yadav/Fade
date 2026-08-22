#pragma once

#include "../util.hpp"  // defines SwapChainSupportDetails, findMemoryType
#include <mutex>
#include <optional>
#include <string>
#include <vector>

// SwapChainSupportDetails already defined in util.hpp — do NOT redefine here

struct QueueFamilyIndices {
  int graphicsFamily      = -1;
  int presentationFamily  = -1;
  int videoDecodeFamily   = -1;
  int transferFamily      = -1;

  bool hasVideoDecodeQueue()     const { return videoDecodeFamily >= 0; }
  bool hasDedicatedTransferQueue() const {
    return transferFamily >= 0 && transferFamily != graphicsFamily;
  }
  bool isComplete() { return graphicsFamily >= 0 && presentationFamily >= 0; }
};

class DeviceContext {
public:
  DeviceContext();
  ~DeviceContext();

  // Headless init — no window, no swapchain surface needed
  // Uses a dummy Win32 surface internally for device selection, then destroys it.
  bool init();

  VkInstance         getInstance()       const { return m_instance; }
  VkDevice           getLogicalDevice()  const { return mainDevice.LogicalDevice; }
  VkPhysicalDevice   getPhysicalDevice() const { return mainDevice.PhysicalDevice; }
  VkQueue            getGraphicsQueue()  const { return m_graphicsQueue; }
  VkQueue            getPresentQueue()   const { return m_presentQueue; }
  VkQueue            getTransferQueue()  const { return m_transferQueue; }

  bool isVideoDecodeSupported() const { return m_videoDecodeSupported; }
  std::string getStatus();

  QueueFamilyIndices findQueueFamilies(VkPhysicalDevice device, VkSurfaceKHR surface);
  std::recursive_mutex& graphicsQueueMutex() { return m_graphicsQueueMutex; }
  std::recursive_mutex& transferQueueMutex() { return m_transferQueueMutex; }

  // Compat methods for Qteee-Vulkan Buffer.cpp / Texture.cpp
  void lockGraphicsQueue()   { m_graphicsQueueMutex.lock(); }
  void unlockGraphicsQueue() { m_graphicsQueueMutex.unlock(); }
  void lockTransferQueue()   { m_transferQueueMutex.lock(); }
  void unlockTransferQueue() { m_transferQueueMutex.unlock(); }

  SwapChainSupportDetails querySwapChainSupport(VkPhysicalDevice device, VkSurfaceKHR surface);

  QueueFamilyIndices getQueueFamilyIndices() const { return m_indices; }
  uint32_t getGraphicsQueueFamilyIndex() const {
      return static_cast<uint32_t>(m_indices.graphicsFamily);
  }

  // SkiaContext.cpp compatibility aliases
  VkQueue getGraphicQueue() const { return m_graphicsQueue; }  // alias (original has no 's')
  const std::vector<const char*>& getDeviceExtensions() const { return m_deviceExtensions; }

  // SkiaContext.cpp calls getVulkanInstance()->vkInstance()
  // Return a thin wrapper that exposes vkInstance()
  struct VkInstanceWrapper {
      VkInstance inst;
      VkInstance vkInstance() const { return inst; }
  };
  VkInstanceWrapper getVulkanInstance() const { return {m_instance}; }

private:
  VkInstance m_instance = VK_NULL_HANDLE;

  std::vector<const char*> m_instanceExtensions = {
      VK_KHR_SURFACE_EXTENSION_NAME,
      "VK_KHR_win32_surface",
      VK_KHR_EXTERNAL_MEMORY_CAPABILITIES_EXTENSION_NAME,
      VK_KHR_GET_PHYSICAL_DEVICE_PROPERTIES_2_EXTENSION_NAME,
  };

  std::vector<const char*> m_deviceExtensions = {
      VK_KHR_SWAPCHAIN_EXTENSION_NAME,
      VK_KHR_EXTERNAL_MEMORY_EXTENSION_NAME,
      "VK_KHR_external_memory_win32",
      VK_KHR_EXTERNAL_SEMAPHORE_EXTENSION_NAME,
      "VK_KHR_external_semaphore_win32",
      "VK_KHR_synchronization2",
  };

  struct {
    VkPhysicalDevice PhysicalDevice = VK_NULL_HANDLE;
    VkDevice         LogicalDevice  = VK_NULL_HANDLE;
  } mainDevice;

  VkQueue m_graphicsQueue = VK_NULL_HANDLE;
  VkQueue m_presentQueue  = VK_NULL_HANDLE;
  VkQueue m_transferQueue = VK_NULL_HANDLE;
  VkSurfaceKHR m_dummySurface = VK_NULL_HANDLE; // used only for device selection

  QueueFamilyIndices m_indices;
  bool m_videoDecodeSupported = false;

  std::recursive_mutex m_graphicsQueueMutex;
  std::recursive_mutex m_decodeQueueMutex;
  std::recursive_mutex m_transferQueueMutex;

  void createInstance();
  void pickPhysicalDevice();
  void createLogicalDevice();
  void probeOptionalExtensions();

  bool isDeviceSuitable(VkPhysicalDevice device, VkSurfaceKHR surface);
  bool checkDeviceExtensionSupport(VkPhysicalDevice device);
  int  getScoreOfGPU(VkPhysicalDeviceProperties& props, VkPhysicalDevice device, VkSurfaceKHR surface);

  static constexpr bool enableValidationLayers =
#ifdef NDEBUG
      false;
#else
      true;
#endif
  const std::vector<const char*> m_validationLayers = {"VK_LAYER_KHRONOS_validation"};
};
