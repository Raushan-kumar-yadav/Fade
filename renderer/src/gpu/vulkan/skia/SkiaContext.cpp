#include "SkiaContext.hpp"
#include "gpu/ganesh/vk/GrVkDirectContext.h"
#include "gpu/vk/VulkanBackendContext.h"
#include "gpu/vk/VulkanExtensions.h"
#include "gpu/vk/VulkanMemoryAllocator.h"

#define VMA_IMPLEMENTATION
#include "vk_mem_alloc.h"

#include <iostream>
#include <vector>

namespace {

class VmaVulkanAllocator : public skgpu::VulkanMemoryAllocator {
public:
  explicit VmaVulkanAllocator(VmaAllocator vmaAllocator)
      : m_allocator(vmaAllocator) {}

  VkResult allocateImageMemory(VkImage image, uint32_t allocationPropertyFlags,
                               skgpu::VulkanBackendMemory *outMemory) override {
    VmaAllocationCreateInfo allocInfo =
        makeAllocInfo(allocationPropertyFlags, false);

    auto *allocation = new VmaAllocation{};
    VkResult result = vmaAllocateMemoryForImage(m_allocator, image, &allocInfo,
                                                allocation, nullptr);
    if (result != VK_SUCCESS) {
      delete allocation;
      return result;
    }
    *outMemory = reinterpret_cast<skgpu::VulkanBackendMemory>(allocation);
    return VK_SUCCESS;
  }

  VkResult
  allocateBufferMemory(VkBuffer buffer, BufferUsage usage,
                       uint32_t allocationPropertyFlags,
                       skgpu::VulkanBackendMemory *outMemory) override {
    VmaAllocationCreateInfo allocInfo =
        makeAllocInfo(allocationPropertyFlags, true, usage);

    auto *allocation = new VmaAllocation{};
    VkResult result = vmaAllocateMemoryForBuffer(
        m_allocator, buffer, &allocInfo, allocation, nullptr);
    if (result != VK_SUCCESS) {
      delete allocation;
      return result;
    }
    *outMemory = reinterpret_cast<skgpu::VulkanBackendMemory>(allocation);
    return VK_SUCCESS;
  }

  void getAllocInfo(const skgpu::VulkanBackendMemory &mem,
                    skgpu::VulkanAlloc *outAlloc) const override {
    auto *allocation = reinterpret_cast<VmaAllocation *>(mem);
    VmaAllocationInfo info{};
    vmaGetAllocationInfo(m_allocator, *allocation, &info);

    outAlloc->fMemory = info.deviceMemory;
    outAlloc->fOffset = info.offset;
    outAlloc->fSize = info.size;
    
    outAlloc->fFlags = 0;
    VkMemoryPropertyFlags memFlags;
    vmaGetMemoryTypeProperties(m_allocator, info.memoryType, &memFlags);
    if ((memFlags & VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT) != 0) {
        outAlloc->fFlags |= skgpu::VulkanAlloc::kMappable_Flag;
    }
    if ((memFlags & VK_MEMORY_PROPERTY_HOST_COHERENT_BIT) == 0) {
        outAlloc->fFlags |= skgpu::VulkanAlloc::kNoncoherent_Flag;
    }
    if ((memFlags & VK_MEMORY_PROPERTY_LAZILY_ALLOCATED_BIT) != 0) {
        outAlloc->fFlags |= skgpu::VulkanAlloc::kLazilyAllocated_Flag;
    }

    outAlloc->fBackendMemory = mem;
  }

  void* mapMemory(const skgpu::VulkanBackendMemory &mem) override {
    auto *allocation = reinterpret_cast<VmaAllocation *>(mem);
    VmaAllocationInfo info;
    vmaGetAllocationInfo(m_allocator, *allocation, &info);
    if (info.pMappedData) {
        return info.pMappedData;
    }
    void* mappedData = nullptr;
    vmaMapMemory(m_allocator, *allocation, &mappedData);
    return mappedData;
  }

  VkResult mapMemory(const skgpu::VulkanBackendMemory &mem,
                     void **data) override {
    auto *allocation = reinterpret_cast<VmaAllocation *>(mem);
    return vmaMapMemory(m_allocator, *allocation, data);
  }

  void unmapMemory(const skgpu::VulkanBackendMemory &mem) override {
    auto *allocation = reinterpret_cast<VmaAllocation *>(mem);
    vmaUnmapMemory(m_allocator, *allocation);
  }

  VkResult flushMemory(const skgpu::VulkanBackendMemory &mem,
                       VkDeviceSize offset, VkDeviceSize size) override {
    auto *allocation = reinterpret_cast<VmaAllocation *>(mem);
    return vmaFlushAllocation(m_allocator, *allocation, offset, size);
  }

  VkResult invalidateMemory(const skgpu::VulkanBackendMemory &mem,
                            VkDeviceSize offset, VkDeviceSize size) override {
    auto *allocation = reinterpret_cast<VmaAllocation *>(mem);
    return vmaInvalidateAllocation(m_allocator, *allocation, offset, size);
  }

  void freeMemory(const skgpu::VulkanBackendMemory &mem) override {
    auto *allocation = reinterpret_cast<VmaAllocation *>(mem);
    vmaFreeMemory(m_allocator, *allocation);
    delete allocation;
  }

  std::pair<uint64_t, uint64_t> totalAllocatedAndUsedMemory() const override {
    VmaTotalStatistics stats{};
    vmaCalculateStatistics(m_allocator, &stats);
    return {stats.total.statistics.blockBytes,
            stats.total.statistics.allocationBytes};
  }

private:
  VmaAllocator m_allocator;

  // NOTE: vmaAllocateMemoryForImage()/vmaAllocateMemoryForBuffer() (used
  // below in allocateImageMemory()/allocateBufferMemory()) always pass
  // VmaBufferImageUsage::UNKNOWN internally, and VMA_MEMORY_USAGE_AUTO*
  // requires a known buffer/image usage (it's only valid with
  // vmaCreateBuffer()/vmaCreateImage(), which see the full create-info).
  // Using AUTO* here unconditionally hits an assert inside VMA
  // (FindMemoryPreferences) and silently produces a broken allocation in
  // release builds. Use the legacy (non-AUTO) usage enums instead, which
  // don't require bufImgUsage.
  VmaAllocationCreateInfo
  makeAllocInfo(uint32_t skiaFlags, bool isBuffer,
                BufferUsage usage = BufferUsage::kGpuOnly) const {
    VmaAllocationCreateInfo info{};
    info.usage = VMA_MEMORY_USAGE_GPU_ONLY;

    if (skiaFlags & kDedicatedAllocation_AllocationPropertyFlag)
      info.flags |= VMA_ALLOCATION_CREATE_DEDICATED_MEMORY_BIT;

    if (skiaFlags & kPersistentlyMapped_AllocationPropertyFlag)
      info.flags |= VMA_ALLOCATION_CREATE_MAPPED_BIT |
                    VMA_ALLOCATION_CREATE_HOST_ACCESS_SEQUENTIAL_WRITE_BIT;

    if (skiaFlags & kLazyAllocation_AllocationPropertyFlag)
      info.usage = VMA_MEMORY_USAGE_GPU_LAZILY_ALLOCATED;

    if (isBuffer) {
      switch (usage) {
      case BufferUsage::kGpuOnly:
        info.usage = VMA_MEMORY_USAGE_GPU_ONLY;
        break;
      case BufferUsage::kCpuWritesGpuReads:
        info.flags |= VMA_ALLOCATION_CREATE_HOST_ACCESS_SEQUENTIAL_WRITE_BIT;
        info.usage = VMA_MEMORY_USAGE_CPU_TO_GPU;
        break;
      case BufferUsage::kTransfersFromCpuToGpu:
        info.flags |= VMA_ALLOCATION_CREATE_HOST_ACCESS_SEQUENTIAL_WRITE_BIT;
        info.usage = VMA_MEMORY_USAGE_CPU_TO_GPU;
        break;
      case BufferUsage::kTransfersFromGpuToCpu:
        info.flags |= VMA_ALLOCATION_CREATE_HOST_ACCESS_RANDOM_BIT;
        info.usage = VMA_MEMORY_USAGE_GPU_TO_CPU;
        break;
      }
    }

    return info;
  }
};

} // namespace

SkiaContext::SkiaContext(DeviceContext *deviceContext) { Init(deviceContext); }

SkiaContext::~SkiaContext() {

  fDirectContext.reset();
  if (fVmaAllocator) {
    vmaDestroyAllocator(static_cast<VmaAllocator>(fVmaAllocator));
    fVmaAllocator = nullptr;
  }
}

void SkiaContext::Init(DeviceContext *deviceContext) {
  VkInstance instance = deviceContext->getInstance();
  VkPhysicalDevice physicalDevice = deviceContext->getPhysicalDevice();
  VkDevice device = deviceContext->getLogicalDevice();
  VkQueue graphicsQueue = deviceContext->getGraphicQueue();
  uint32_t queueFamilyIdx = deviceContext->getGraphicsQueueFamilyIndex();

  skgpu::VulkanGetProc getProc = [](const char *name, VkInstance inst,
                                    VkDevice dev) -> PFN_vkVoidFunction {
    if (dev != VK_NULL_HANDLE)
      return vkGetDeviceProcAddr(dev, name);

    return vkGetInstanceProcAddr(inst, name);
  };

  skgpu::VulkanExtensions vkExtensions;
  {
    // IMPORTANT: this must be the list of instance extensions that were
    // actually ENABLED on the VkInstance (via QVulkanInstance::create()),
    // not the full list of extensions merely AVAILABLE on the system.
    // Previously this enumerated every system-available instance extension
    // via vkEnumerateInstanceExtensionProperties, which told Skia's Vulkan
    // caps that things like VK_KHR_get_physical_device_properties2 /
    // VK_EXT_swapchain_colorspace / etc. were enabled when they weren't -
    // causing SkSurfaces::WrapBackendRenderTarget to silently fail while a
    // Skia-owned (non-wrapped) surface still worked fine. Confirmed via
    // QT_LOGGING_RULES=qt.vulkan.debug=true, which prints exactly what
    // QVulkanInstance enabled: VK_KHR_surface, VK_KHR_win32_surface,
    // VK_EXT_debug_utils, VK_KHR_portability_enumeration.
    std::vector<const char *> instExtNames = {
        VK_KHR_SURFACE_EXTENSION_NAME,
#if defined(_WIN32)
        "VK_KHR_win32_surface",
#endif
        VK_EXT_DEBUG_UTILS_EXTENSION_NAME,
        "VK_KHR_portability_enumeration",
    };

    const auto &devExts = deviceContext->getDeviceExtensions();
    std::vector<const char *> devExtNames;
    devExtNames.reserve(devExts.size());
    for (auto &e : devExts)
      devExtNames.push_back(e);

    vkExtensions.init(
        getProc, instance, physicalDevice,
        static_cast<uint32_t>(instExtNames.size()), instExtNames.data(),
        static_cast<uint32_t>(devExtNames.size()), devExtNames.data());
  }

  VkPhysicalDeviceFeatures2 features2{};
  features2.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2;
  vkGetPhysicalDeviceFeatures2(physicalDevice, &features2);

  VmaVulkanFunctions vmaFuncs{};
  vmaFuncs.vkGetInstanceProcAddr = vkGetInstanceProcAddr;
  vmaFuncs.vkGetDeviceProcAddr = vkGetDeviceProcAddr;

  VmaAllocatorCreateInfo vmaInfo{};
  vmaInfo.physicalDevice = physicalDevice;
  vmaInfo.device = device;
  vmaInfo.instance = instance;
  vmaInfo.vulkanApiVersion = VK_API_VERSION_1_2;
  vmaInfo.pVulkanFunctions = &vmaFuncs;

  VmaAllocator vmaAllocator{};
  if (vmaCreateAllocator(&vmaInfo, &vmaAllocator) != VK_SUCCESS) {
    std::cerr << "[SkiaContext] ERROR: vmaCreateAllocator failed!\n";
    return;
  }
  fVmaAllocator = vmaAllocator;

  auto allocator = sk_make_sp<VmaVulkanAllocator>(vmaAllocator);

  skgpu::VulkanBackendContext backendContext{};
  backendContext.fInstance = instance;
  backendContext.fPhysicalDevice = physicalDevice;
  backendContext.fDevice = device;
  backendContext.fQueue = graphicsQueue;
  backendContext.fGraphicsQueueIndex = queueFamilyIdx;
  backendContext.fMaxAPIVersion = VK_API_VERSION_1_2;
  backendContext.fVkExtensions = &vkExtensions;
  backendContext.fDeviceFeatures2 = &features2;
  backendContext.fMemoryAllocator = allocator;
  backendContext.fGetProc = getProc;

  fDirectContext = GrDirectContexts::MakeVulkan(backendContext);

  if (!fDirectContext) {
    std::cerr << "[SkiaContext] ERROR: Failed to create GrDirectContext!\n";
  } else {
    std::cout << "[SkiaContext] GrDirectContext created OK.\n";
  }
}
