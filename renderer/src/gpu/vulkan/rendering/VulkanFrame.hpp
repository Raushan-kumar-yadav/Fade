#pragma once

#include <vulkan/vulkan.h>
#include "core/gpu/vulkan/device/DeviceContext.hpp"
#include "core/gpu/vulkan/sync/Semaphore.hpp" 
#include "core/gpu/vulkan/sync/Fence.hpp" 
#include "core/gpu/vulkan/command/CommandPool.hpp"
#include "core/gpu/vulkan/command/CommandBuffer.hpp"



class VulkanFrame
{
private:

Semaphore* m_imageAvailableSemaphore;
Semaphore* m_renderFinishedSemaphore;
Fence* m_inFlightFence;

DeviceContext* m_context;
CommandPool* m_commandPool;

CommandBuffer* m_commandBuffer;





public: 
    VulkanFrame(DeviceContext* context , CommandPool* CommandPool);
    ~VulkanFrame();

    // getter and setter 

    VkSemaphore getImageAvailableSemaphore() const { return m_imageAvailableSemaphore->getHandle(); }
    VkSemaphore getRenderFinishedSemaphore() const { return m_renderFinishedSemaphore->getHandle(); }
    VkFence getInFlightFence() const { return m_inFlightFence->getHandle(); }

    void waitForReady();
void reset();
    CommandBuffer* getCommandBuffer() const { return m_commandBuffer; }
};



