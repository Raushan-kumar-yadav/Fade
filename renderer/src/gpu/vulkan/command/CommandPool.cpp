#include "CommandPool.hpp"
#include <stdexcept>


CommandPool::CommandPool(DeviceContext* context, uint32_t queueFamilyIndex, VkCommandPoolCreateFlags flags)
    : m_DeviceContext(context) {
    
    VkCommandPoolCreateInfo poolInfo{};
    poolInfo.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO;
    poolInfo.flags = flags;
    poolInfo.queueFamilyIndex = queueFamilyIndex;

    
    if (vkCreateCommandPool(m_DeviceContext->getLogicalDevice(), &poolInfo, nullptr, &m_commandPool) != VK_SUCCESS) {
        throw std::runtime_error("Failed to create command pool!");
    }
}



CommandPool::~CommandPool() {
    
    if (m_commandPool != VK_NULL_HANDLE) {
        vkDestroyCommandPool(m_DeviceContext->getLogicalDevice(), m_commandPool, nullptr);
    }
}


CommandPool::CommandPool(CommandPool&& other) noexcept 
    : m_DeviceContext(other.m_DeviceContext), 
      m_commandPool(other.m_commandPool) {
    
    other.m_commandPool = VK_NULL_HANDLE;      
    other.m_DeviceContext = nullptr;           
}


CommandPool& CommandPool::operator=(CommandPool&& other) noexcept {
    if (this != &other) {
       
        if (m_commandPool != VK_NULL_HANDLE) {
            vkDestroyCommandPool(m_DeviceContext->getLogicalDevice(), m_commandPool, nullptr);
        }
        
    
        m_DeviceContext = other.m_DeviceContext;
        m_commandPool = other.m_commandPool;
        
       
        other.m_commandPool = VK_NULL_HANDLE;
        other.m_DeviceContext = nullptr;
    }
    return *this;
}