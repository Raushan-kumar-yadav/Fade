#include "DeviceContext.hpp"
#include <iostream>
#include <set>
#include <stdexcept>
#include <vector>

// Windows-native Vulkan surface (no Qt)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <Windows.h>
#include <vulkan/vulkan_win32.h>

// These may already be defined by logger.hpp — only define if missing
#ifndef LOG_INFO
#define LOG_INFO(msg)  do { std::cout << "[DeviceContext] "       << msg << "\n"; } while(0)
#endif
#ifndef LOG_WARN
#define LOG_WARN(msg)  do { std::cout << "[DeviceContext][WARN] " << msg << "\n"; } while(0)
#endif
#ifndef LOG_ERROR
#define LOG_ERROR(msg) do { std::cerr << "[DeviceContext][ERR] "  << msg << "\n"; } while(0)
#endif

DeviceContext::DeviceContext()  {}
DeviceContext::~DeviceContext() {
  if (mainDevice.LogicalDevice != VK_NULL_HANDLE)
    vkDestroyDevice(mainDevice.LogicalDevice, nullptr);
  if (m_dummySurface != VK_NULL_HANDLE)
    vkDestroySurfaceKHR(m_instance, m_dummySurface, nullptr);
  if (m_instance != VK_NULL_HANDLE)
    vkDestroyInstance(m_instance, nullptr);
}

// ── Public init (headless — no QWindow) ─────────────────────────────────────

bool DeviceContext::init() {
  try {
    createInstance();
  } catch (const std::exception& e) {
    LOG_ERROR(std::string("createInstance failed: ") + e.what());
    return false;
  }

  // Create a tiny invisible Win32 window just for VkSurfaceKHR device selection.
  // We need a surface to query swapchain support during device scoring.
  // The surface is destroyed after device selection; headless rendering uses
  // offscreen VkImages (no swapchain needed for our preview pipeline).
  HWND hwnd = CreateWindowExA(0, "STATIC", "fade_probe", WS_OVERLAPPED,
                               0, 0, 1, 1, nullptr, nullptr,
                               GetModuleHandle(nullptr), nullptr);

  VkWin32SurfaceCreateInfoKHR surfaceInfo{};
  surfaceInfo.sType     = VK_STRUCTURE_TYPE_WIN32_SURFACE_CREATE_INFO_KHR;
  surfaceInfo.hinstance = GetModuleHandle(nullptr);
  surfaceInfo.hwnd      = hwnd;

  if (vkCreateWin32SurfaceKHR(m_instance, &surfaceInfo, nullptr, &m_dummySurface) != VK_SUCCESS) {
    LOG_WARN("Failed to create dummy Win32 surface — device scoring limited");
    m_dummySurface = VK_NULL_HANDLE;
  }
  DestroyWindow(hwnd); // window handle no longer needed

  try {
    pickPhysicalDevice();
  } catch (const std::exception& e) {
    LOG_ERROR(std::string("pickPhysicalDevice failed: ") + e.what());
    return false;
  }

  createLogicalDevice();
  LOG_INFO("DeviceContext initialized (headless Vulkan)");
  return true;
}

// ── Instance creation (raw Vulkan, replaces QVulkanInstance) ─────────────────

void DeviceContext::createInstance() {
  VkApplicationInfo appInfo{};
  appInfo.sType              = VK_STRUCTURE_TYPE_APPLICATION_INFO;
  appInfo.pApplicationName   = "FadeRenderEngine";
  appInfo.applicationVersion = VK_MAKE_VERSION(1, 0, 0);
  appInfo.pEngineName        = "FadeNative";
  appInfo.apiVersion         = VK_API_VERSION_1_2;

  std::vector<const char*> layers;
  if (enableValidationLayers)
    layers.push_back("VK_LAYER_KHRONOS_validation");

  VkInstanceCreateInfo createInfo{};
  createInfo.sType                   = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
  createInfo.pApplicationInfo        = &appInfo;
  createInfo.enabledLayerCount       = static_cast<uint32_t>(layers.size());
  createInfo.ppEnabledLayerNames     = layers.empty() ? nullptr : layers.data();
  createInfo.enabledExtensionCount   = static_cast<uint32_t>(m_instanceExtensions.size());
  createInfo.ppEnabledExtensionNames = m_instanceExtensions.data();

  VkResult res = vkCreateInstance(&createInfo, nullptr, &m_instance);
  if (res != VK_SUCCESS)
    throw std::runtime_error("vkCreateInstance failed: " + std::to_string(res));

  LOG_INFO("VkInstance created (API 1.2)");
}

// ── Physical device selection ─────────────────────────────────────────────────

void DeviceContext::pickPhysicalDevice() {
  uint32_t count = 0;
  vkEnumeratePhysicalDevices(m_instance, &count, nullptr);
  if (count == 0)
    throw std::runtime_error("No Vulkan-capable GPUs found");

  std::vector<VkPhysicalDevice> devices(count);
  vkEnumeratePhysicalDevices(m_instance, &count, devices.data());

  VkPhysicalDevice best  = VK_NULL_HANDLE;
  int              score = -1;

  for (auto& dev : devices) {
    VkPhysicalDeviceProperties props;
    vkGetPhysicalDeviceProperties(dev, &props);
    int s = getScoreOfGPU(props, dev, m_dummySurface);
    LOG_INFO(std::string("GPU: ") + props.deviceName + "  score=" + std::to_string(s));
    if (s > score) { score = s; best = dev; }
  }

  if (best == VK_NULL_HANDLE)
    throw std::runtime_error("No suitable GPU found");

  mainDevice.PhysicalDevice = best;
  m_indices = findQueueFamilies(best, m_dummySurface);
  probeOptionalExtensions();

  VkPhysicalDeviceProperties chosen;
  vkGetPhysicalDeviceProperties(best, &chosen);
  LOG_INFO(std::string("Selected GPU: ") + chosen.deviceName);
}

int DeviceContext::getScoreOfGPU(VkPhysicalDeviceProperties& props,
                                  VkPhysicalDevice device, VkSurfaceKHR surface) {
  if (!isDeviceSuitable(device, surface)) return -1;
  int s = 0;
  if (props.deviceType == VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU)   s += 1000;
  if (props.deviceType == VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU) s += 100;
  s += static_cast<int>(props.limits.maxImageDimension2D / 1000);
  return s;
}

// ── Logical device ────────────────────────────────────────────────────────────

void DeviceContext::createLogicalDevice() {
  QueueFamilyIndices indices = m_indices;

  std::set<int> uniqueFamilies = {
      indices.graphicsFamily, indices.presentationFamily,
  };
  if (indices.hasDedicatedTransferQueue())
    uniqueFamilies.insert(indices.transferFamily);

  std::vector<VkDeviceQueueCreateInfo> queueInfos;
  float priority = 1.0f;
  for (int family : uniqueFamilies) {
    VkDeviceQueueCreateInfo qi{};
    qi.sType            = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO;
    qi.queueFamilyIndex = static_cast<uint32_t>(family);
    qi.queueCount       = 1;
    qi.pQueuePriorities = &priority;
    queueInfos.push_back(qi);
  }

  VkPhysicalDeviceFeatures features{};
  features.samplerAnisotropy = VK_TRUE;

  // Vulkan 1.2 features needed by Skia
  VkPhysicalDeviceVulkan12Features vk12{};
  vk12.sType                   = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES;
  vk12.drawIndirectCount       = VK_TRUE;
  vk12.descriptorIndexing      = VK_TRUE;
  vk12.timelineSemaphore       = VK_TRUE;
  vk12.bufferDeviceAddress     = VK_TRUE;

  VkDeviceCreateInfo createInfo{};
  createInfo.sType                   = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO;
  createInfo.queueCreateInfoCount    = static_cast<uint32_t>(queueInfos.size());
  createInfo.pQueueCreateInfos       = queueInfos.data();
  createInfo.enabledExtensionCount   = static_cast<uint32_t>(m_deviceExtensions.size());
  createInfo.ppEnabledExtensionNames = m_deviceExtensions.data();
  createInfo.pEnabledFeatures        = &features;
  createInfo.pNext                   = &vk12;

  VkResult res = vkCreateDevice(mainDevice.PhysicalDevice, &createInfo,
                                 nullptr, &mainDevice.LogicalDevice);
  if (res != VK_SUCCESS)
    throw std::runtime_error("vkCreateDevice failed: " + std::to_string(res));

  vkGetDeviceQueue(mainDevice.LogicalDevice, indices.graphicsFamily, 0, &m_graphicsQueue);
  vkGetDeviceQueue(mainDevice.LogicalDevice, indices.presentationFamily, 0, &m_presentQueue);

  if (indices.hasDedicatedTransferQueue()) {
    vkGetDeviceQueue(mainDevice.LogicalDevice, indices.transferFamily, 0, &m_transferQueue);
    LOG_INFO("Dedicated transfer queue (family " + std::to_string(indices.transferFamily) + ")");
  } else {
    m_transferQueue = m_graphicsQueue;
    LOG_INFO("Sharing graphics queue for transfers");
  }

  LOG_INFO("VkDevice created");
}

// ── Queue family / surface query helpers ──────────────────────────────────────

QueueFamilyIndices DeviceContext::findQueueFamilies(VkPhysicalDevice device,
                                                     VkSurfaceKHR surface) {
  QueueFamilyIndices indices;
  uint32_t count = 0;
  vkGetPhysicalDeviceQueueFamilyProperties(device, &count, nullptr);
  std::vector<VkQueueFamilyProperties> families(count);
  vkGetPhysicalDeviceQueueFamilyProperties(device, &count, families.data());

  for (int i = 0; i < static_cast<int>(families.size()); ++i) {
    const auto& f = families[i];
    if (f.queueCount > 0 && (f.queueFlags & VK_QUEUE_GRAPHICS_BIT))
      indices.graphicsFamily = i;

    if (surface != VK_NULL_HANDLE) {
      VkBool32 present = VK_FALSE;
      vkGetPhysicalDeviceSurfaceSupportKHR(device, i, surface, &present);
      if (f.queueCount > 0 && present) indices.presentationFamily = i;
    } else {
      // headless — use graphics family for "present" (no real present needed)
      if (indices.graphicsFamily >= 0 && indices.presentationFamily < 0)
        indices.presentationFamily = indices.graphicsFamily;
    }

    bool hasTransfer = (f.queueFlags & VK_QUEUE_TRANSFER_BIT) != 0;
    bool noGraphics  = (f.queueFlags & VK_QUEUE_GRAPHICS_BIT) == 0;
    if (f.queueCount > 0 && hasTransfer && noGraphics && indices.transferFamily < 0)
      indices.transferFamily = i;

#ifdef VK_KHR_video_decode_queue
    if (f.queueCount > 0 &&
        (f.queueFlags & VK_QUEUE_VIDEO_DECODE_BIT_KHR) &&
        indices.videoDecodeFamily < 0)
      indices.videoDecodeFamily = i;
#endif
  }
  if (indices.transferFamily < 0) indices.transferFamily = indices.graphicsFamily;
  return indices;
}

bool DeviceContext::isDeviceSuitable(VkPhysicalDevice device, VkSurfaceKHR surface) {
  auto indices = findQueueFamilies(device, surface);
  if (!checkDeviceExtensionSupport(device)) return false;
  if (surface != VK_NULL_HANDLE) {
    auto sc = querySwapChainSupport(device, surface);
    if (sc.formats.empty() || sc.presentModes.empty()) return false;
  }
  return indices.graphicsFamily >= 0;
}

bool DeviceContext::checkDeviceExtensionSupport(VkPhysicalDevice device) {
  uint32_t count = 0;
  vkEnumerateDeviceExtensionProperties(device, nullptr, &count, nullptr);
  std::vector<VkExtensionProperties> available(count);
  vkEnumerateDeviceExtensionProperties(device, nullptr, &count, available.data());
  std::set<std::string> required = {VK_KHR_SWAPCHAIN_EXTENSION_NAME};
  for (auto& ext : available) required.erase(ext.extensionName);
  return required.empty();
}

SwapChainSupportDetails DeviceContext::querySwapChainSupport(VkPhysicalDevice device,
                                                              VkSurfaceKHR surface) {
  SwapChainSupportDetails d;
  if (surface == VK_NULL_HANDLE) return d;
  vkGetPhysicalDeviceSurfaceCapabilitiesKHR(device, surface, &d.capabilities);
  uint32_t n = 0;
  vkGetPhysicalDeviceSurfaceFormatsKHR(device, surface, &n, nullptr);
  d.formats.resize(n);
  vkGetPhysicalDeviceSurfaceFormatsKHR(device, surface, &n, d.formats.data());
  vkGetPhysicalDeviceSurfacePresentModesKHR(device, surface, &n, nullptr);
  d.presentModes.resize(n);
  vkGetPhysicalDeviceSurfacePresentModesKHR(device, surface, &n, d.presentModes.data());
  return d;
}

void DeviceContext::probeOptionalExtensions() {
  uint32_t count = 0;
  vkEnumerateDeviceExtensionProperties(mainDevice.PhysicalDevice, nullptr, &count, nullptr);
  std::vector<VkExtensionProperties> available(count);
  vkEnumerateDeviceExtensionProperties(mainDevice.PhysicalDevice, nullptr, &count, available.data());

  auto has = [&](const char* name) {
    for (auto& e : available) if (strcmp(e.extensionName, name) == 0) return true;
    return false;
  };

  bool videoQueue  = has("VK_KHR_video_queue");
  bool videoDecode = has("VK_KHR_video_decode_queue");
  bool videoH264   = has("VK_KHR_video_decode_h264");
  bool hasFamily   = m_indices.hasVideoDecodeQueue();

  LOG_INFO("=== Vulkan Video Decode Probe ===");
  LOG_INFO(std::string("VK_KHR_video_queue:         ") + (videoQueue  ? "YES" : "NO"));
  LOG_INFO(std::string("VK_KHR_video_decode_queue:  ") + (videoDecode ? "YES" : "NO"));
  LOG_INFO(std::string("VK_KHR_video_decode_h264:   ") + (videoH264   ? "YES" : "NO"));
  LOG_INFO(std::string("Video decode queue family:  ") + (hasFamily   ? "YES" : "NO"));

  if (videoQueue && videoDecode && videoH264 && hasFamily) {
    m_deviceExtensions.push_back("VK_KHR_video_queue");
    m_deviceExtensions.push_back("VK_KHR_video_decode_queue");
    m_deviceExtensions.push_back("VK_KHR_video_decode_h264");
    if (has("VK_KHR_video_decode_h265")) {
      m_deviceExtensions.push_back("VK_KHR_video_decode_h265");
      LOG_INFO("VK_KHR_video_decode_h265:   YES");
    }
    m_videoDecodeSupported = true;
    LOG_INFO("Vulkan Video Decode: ENABLED");
  } else {
    m_videoDecodeSupported = false;
    LOG_WARN("Vulkan Video Decode not supported on this driver — falling back to D3D11VA / CPU");
  }
}

std::string DeviceContext::getStatus() {
  uint32_t n = 0;
  vkEnumerateInstanceExtensionProperties(nullptr, &n, nullptr);
  return n > 0 ? "Vulkan supported (" + std::to_string(n) + " extensions)"
               : "No Vulkan extensions found";
}