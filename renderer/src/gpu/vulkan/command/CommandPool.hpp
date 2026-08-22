#pragma once 
#include <vulkan/vulkan.h>
#include "core/gpu/vulkan/device/DeviceContext.hpp"
#include "core/api/Logger.hpp"

class DeviceContext;

class CommandPool
{
private:
    DeviceContext* m_DeviceContext;
    VkCommandPool m_commandPool{VK_NULL_HANDLE};
public:
    CommandPool(DeviceContext* context,uint32_t queueFamilyIndex,VkCommandPoolCreateFlags  CreateFlag);
    ~CommandPool();

    CommandPool(const CommandPool&)  = delete;
    CommandPool& operator=(const CommandPool&) = delete;

    
    CommandPool(CommandPool&& other) noexcept;
    CommandPool& operator=(CommandPool&& other) noexcept;

    VkCommandPool getHandle() const { return m_commandPool; }
    VkDevice getDevice(){return m_DeviceContext->getLogicalDevice();};
};

