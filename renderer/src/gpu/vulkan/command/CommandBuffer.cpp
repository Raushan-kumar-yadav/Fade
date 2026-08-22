#include "CommandBuffer.hpp"
#include "core/gpu/vulkan/device/DeviceContext.hpp" 

CommandBuffer::CommandBuffer(CommandPool &pool, bool isPrimary):m_device(pool.getDevice()),m_pool(pool.getHandle())
{
    VkCommandBufferAllocateInfo allocateInfo{};
    allocateInfo.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
    allocateInfo.commandPool =  m_pool;
    allocateInfo.commandBufferCount = 1 ;
    allocateInfo.pNext = nullptr;
    allocateInfo.level = isPrimary ? VK_COMMAND_BUFFER_LEVEL_PRIMARY : VK_COMMAND_BUFFER_LEVEL_SECONDARY;


    if (vkAllocateCommandBuffers(m_device, &allocateInfo, &m_commandBuffer) != VK_SUCCESS) {
        throw std::runtime_error("Failed to allocate command buffer!");
    }
}

CommandBuffer::~CommandBuffer() {
    if (m_commandBuffer != VK_NULL_HANDLE) {
        vkFreeCommandBuffers(m_device, m_pool, 1, &m_commandBuffer);
    }
}

CommandBuffer::CommandBuffer(CommandBuffer&& other) noexcept 
    : m_device(other.m_device),
      m_pool(other.m_pool),
      m_commandBuffer(other.m_commandBuffer) 
{
    other.m_commandBuffer = VK_NULL_HANDLE;
}


CommandBuffer& CommandBuffer::operator=(CommandBuffer&& other) noexcept {
    if (this != &other) {
        // Destroy old
        if (m_commandBuffer != VK_NULL_HANDLE) {
            vkFreeCommandBuffers(m_device, m_pool, 1, &m_commandBuffer);
        }
        
        // assigned to new
        m_device = other.m_device;
        m_pool = other.m_pool;
        m_commandBuffer = other.m_commandBuffer;
        
        // null source
        other.m_commandBuffer = VK_NULL_HANDLE;
    }
    return *this;
}


void CommandBuffer::begin(VkCommandBufferUsageFlags flags) {
    VkCommandBufferBeginInfo beginInfo{};
    beginInfo.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
    beginInfo.flags = flags;

    if (vkBeginCommandBuffer(m_commandBuffer, &beginInfo) != VK_SUCCESS) {
        throw std::runtime_error("Failed to begin recording command buffer!");
    }
}


void CommandBuffer::end() {
    if (vkEndCommandBuffer(m_commandBuffer) != VK_SUCCESS) {
        throw std::runtime_error("Failed to record command buffer!");
    }
}

void CommandBuffer::reset(VkCommandBufferResetFlags flags)
{
    if (vkResetCommandBuffer(m_commandBuffer, flags) != VK_SUCCESS) {
        throw std::runtime_error("Failed to reset command buffer!");
    }
}
