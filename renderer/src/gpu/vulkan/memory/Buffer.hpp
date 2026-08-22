#pragma once 
#include <vulkan/vulkan.h>
#include "core/gpu/vulkan/device/DeviceContext.hpp"
#include "core/api/Logger.hpp"
#include <vector>


class Buffer
{
private:
    DeviceContext* m_context;
    VkBuffer m_buffer;
    VkDeviceMemory m_bufferMemory;
    VkDeviceSize m_bufferSize;
    VkBufferUsageFlags m_bufferUsageFlags;
    VkMemoryPropertyFlags m_memoryPropertyFlags;

    void createBuffer();    

public:


    Buffer(DeviceContext* context , VkDeviceSize bufferSize, VkBufferUsageFlags bufferUsageFlags, VkMemoryPropertyFlags memoryPropertyFlags);
    ~Buffer();

    VkBuffer getBuffer() const { return m_buffer; }
    VkDeviceMemory getBufferMemory() const { return m_bufferMemory; }

    void* map();
    void unmap();
    
    void copyBuffer( VkQueue transferQueu, VkCommandPool transferCommandPool,VkBuffer srcBuffer, VkBuffer dstBuffer, VkDeviceSize size);

    //getter functions
    VkBuffer getBuffer(){return m_buffer;}
    VkDeviceMemory getBufferMemory(){return m_bufferMemory;}
    VkDeviceSize getBufferSize(){return m_bufferSize;}
    VkBufferUsageFlags getBufferUsageFlags(){return m_bufferUsageFlags;}
    VkMemoryPropertyFlags getMemoryPropertyFlags(){return m_memoryPropertyFlags;}

};


