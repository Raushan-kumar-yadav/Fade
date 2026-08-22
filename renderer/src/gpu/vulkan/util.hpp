#undef VK_NO_PROTOTYPES
#include <vulkan/vulkan.h>

#include <string> 
#include <vector>
#include <stdexcept> 
#include "core/api/logger.hpp"

struct SwapChainSupportDetails {
    VkSurfaceCapabilitiesKHR capabilities;
    std::vector<VkSurfaceFormatKHR> formats;
    std::vector<VkPresentModeKHR> presentModes;
};

static uint32_t findMemoryType(VkPhysicalDevice physicalDevice, uint32_t allowedType, VkMemoryPropertyFlags properties) {

	VkPhysicalDeviceMemoryProperties memoryProperties;
	vkGetPhysicalDeviceMemoryProperties(physicalDevice, &memoryProperties);

	for (uint32_t i = 0; i < memoryProperties.memoryTypeCount; i++) {
		if ((allowedType & (1 << i)) && (memoryProperties.memoryTypes[i].propertyFlags & properties) == properties) {
			return i;
		}
	}

    LOG_ERROR("Failed to find suitable memory type!");
	throw std::runtime_error("Failed to find suitable memory type!");
};