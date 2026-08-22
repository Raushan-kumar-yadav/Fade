#include "Buffer.hpp"


Buffer::Buffer(DeviceContext *context, VkDeviceSize BufferSize, VkBufferUsageFlags bufferUsageFlags, VkMemoryPropertyFlags memoryPropertyFlags)
{
    this->m_context = context;
    this->m_bufferSize = BufferSize;
    this->m_bufferUsageFlags = bufferUsageFlags;
    this->m_memoryPropertyFlags = memoryPropertyFlags;

    createBuffer();
    LOG_INFO("Buffer created successfully!");
}

void Buffer::createBuffer()
{

    
VkBufferCreateInfo createBufferinfo = {};
createBufferinfo.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
createBufferinfo.size = m_bufferSize;
createBufferinfo.usage = m_bufferUsageFlags;
createBufferinfo.sharingMode = VK_SHARING_MODE_EXCLUSIVE;

VkResult result = vkCreateBuffer(m_context->getLogicalDevice(), &createBufferinfo, nullptr, &m_buffer);

if (result != VK_SUCCESS) {
    LOG_ERROR("Failed to create buffer! Error code: " + std::to_string(result));
	throw std::runtime_error("unable to create buffer");
}

VkMemoryRequirements memRequirements;
vkGetBufferMemoryRequirements(m_context->getLogicalDevice(), m_buffer, &memRequirements); 

VkMemoryAllocateInfo allocateInfo = {};
allocateInfo.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
allocateInfo.allocationSize = memRequirements.size;
allocateInfo.memoryTypeIndex = findMemoryType(m_context->getPhysicalDevice(), memRequirements.memoryTypeBits, m_memoryPropertyFlags);

VkResult allocResult = vkAllocateMemory(m_context->getLogicalDevice(), &allocateInfo, nullptr, &m_bufferMemory);


// attach memroy to the given buffer
if (allocResult != VK_SUCCESS) {
    LOG_ERROR("Failed to allocate buffer memory! Error code: " + std::to_string(allocResult));
	throw std::runtime_error("Failed to allocate buffer memory! Error code: " + std::to_string(allocResult));
}

// Attach memory to the given buffer
vkBindBufferMemory(m_context->getLogicalDevice(), m_buffer, m_bufferMemory, 0);


}





void Buffer::copyBuffer(VkQueue transferQueu, VkCommandPool transferCommandPool, VkBuffer srcBuffer, VkBuffer dstBuffer, VkDeviceSize size)
{
    VkCommandBuffer transferCommandBuffer;

// command buffer details 
VkCommandBufferAllocateInfo commandBufferCreateInfo = {};
commandBufferCreateInfo.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
commandBufferCreateInfo.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
commandBufferCreateInfo.commandPool = transferCommandPool;
commandBufferCreateInfo.commandBufferCount = 1;

vkAllocateCommandBuffers(m_context->getLogicalDevice(), &commandBufferCreateInfo, &transferCommandBuffer);


VkCommandBufferBeginInfo beginInfo = {};
beginInfo.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
beginInfo.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;

vkBeginCommandBuffer(transferCommandBuffer, &beginInfo);

VkBufferCopy bufferCopyRegion = {};
bufferCopyRegion.srcOffset = 0;
bufferCopyRegion.dstOffset = 0;
bufferCopyRegion.size = size;

vkCmdCopyBuffer(transferCommandBuffer, srcBuffer, dstBuffer, 1, &bufferCopyRegion);

// End commands
vkEndCommandBuffer(transferCommandBuffer);

// Queue submission information
VkSubmitInfo submitInfo = {};
submitInfo.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
submitInfo.commandBufferCount = 1;
submitInfo.pCommandBuffers = &transferCommandBuffer;

m_context->lockGraphicsQueue();
vkQueueSubmit(transferQueu, 1, &submitInfo, VK_NULL_HANDLE);
m_context->unlockGraphicsQueue();
vkQueueWaitIdle(transferQueu);

vkFreeCommandBuffers(m_context->getLogicalDevice(), transferCommandPool, 1, &transferCommandBuffer);

}
void* Buffer::map()
{
    void* data;
    vkMapMemory(m_context->getLogicalDevice(), m_bufferMemory, 0, m_bufferSize, 0, &data);
    return data;
}

void Buffer::unmap()
{
    vkUnmapMemory(m_context->getLogicalDevice(), m_bufferMemory);
}

Buffer::~Buffer()
{
    vkDestroyBuffer(m_context->getLogicalDevice(), m_buffer, nullptr);
    vkFreeMemory(m_context->getLogicalDevice(), m_bufferMemory, nullptr);
    LOG_INFO("Buffer destroyed successfully!");
}