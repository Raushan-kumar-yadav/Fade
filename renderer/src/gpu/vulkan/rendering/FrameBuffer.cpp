#include "FrameBuffer.hpp"
#include <vulkan/vulkan.h>
#include <vector>      
#include <stdexcept>

FrameBuffer::FrameBuffer(DeviceContext *context, VkRenderPass renderPass, VkImageView imageView, VkExtent2D extent)
{
    this->m_context = context;
    this->m_extent = extent;

    std::vector<VkImageView> attachments = { imageView };

    VkFramebufferCreateInfo framebufferInfo{};
    framebufferInfo.sType = VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO;
    framebufferInfo.renderPass = renderPass;
    framebufferInfo.attachmentCount = static_cast<uint32_t>(attachments.size());
    framebufferInfo.pAttachments = attachments.data();
    framebufferInfo.width = m_extent.width;
    framebufferInfo.height = m_extent.height;
    framebufferInfo.layers = 1;

    if (vkCreateFramebuffer(m_context->getLogicalDevice(), &framebufferInfo, nullptr, &m_framebuffer) != VK_SUCCESS) 
    {
        LOG_ERROR("Failed to create framebuffer!"); 
        throw std::runtime_error("Failed to create framebuffer!");
    }
    LOG_INFO("Framebuffer created successfully!");
}

FrameBuffer::~FrameBuffer()
{
    if (m_framebuffer != VK_NULL_HANDLE) 
    {
        vkDestroyFramebuffer(m_context->getLogicalDevice(), m_framebuffer, nullptr);
        m_framebuffer = VK_NULL_HANDLE;
    }
    
}
