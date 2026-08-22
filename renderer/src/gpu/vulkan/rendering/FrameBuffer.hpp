#pragma once 
#include <vulkan/vulkan.h>
#include "core/gpu/vulkan/device/DeviceContext.hpp"
#include "core/api/logger.hpp"  


class FrameBuffer
{
private:
    DeviceContext *m_context;
    VkFramebuffer m_framebuffer;
    VkExtent2D m_extent;

public:

    FrameBuffer(DeviceContext *context, VkRenderPass renderPass, VkImageView imageView, VkExtent2D extent);
    ~FrameBuffer();

    VkFramebuffer getHandle() const { return m_framebuffer; }
    VkExtent2D getExtent() const { return m_extent; } 
};