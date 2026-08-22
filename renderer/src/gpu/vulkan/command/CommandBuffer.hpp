#pragma once 
#include <vulkan/vulkan.h>
#include "CommandPool.hpp"

class DeviceContext;

class CommandBuffer
{
private:
    VkDevice m_device{VK_NULL_HANDLE};
    VkCommandPool m_pool{VK_NULL_HANDLE};
    VkCommandBuffer m_commandBuffer{VK_NULL_HANDLE};
public:
    CommandBuffer(CommandPool& pool , bool isPrimary = true);
    ~CommandBuffer();

    CommandBuffer(const CommandBuffer&) = delete;
    CommandBuffer& operator=(const CommandBuffer&) = delete;
    CommandBuffer(CommandBuffer&& other ) noexcept;
    CommandBuffer& operator=(CommandBuffer&& other) noexcept;

    void begin(VkCommandBufferUsageFlags flags = 0 );
    void end();

    void reset(VkCommandBufferResetFlags flags = 0);

    VkCommandBuffer getHandle()const {return m_commandBuffer;}
};

