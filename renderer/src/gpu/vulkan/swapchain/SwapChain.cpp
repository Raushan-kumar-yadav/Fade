#include "Swapchain.hpp"


Swapchain::Swapchain(DeviceContext* deviceContext, uint32_t width, uint32_t height)
    : m_device(deviceContext) 
{
    create(width, height);
    LOG_INFO("Swachchain created !!");
}

Swapchain::~Swapchain() {
    cleanup();
}


void Swapchain::cleanup(){

    VkDevice device = m_device->getLogicalDevice();

    for (auto framebuffer : m_framebuffers) {
        vkDestroyFramebuffer(device, framebuffer, nullptr);
    }
    m_framebuffers.clear();

    for(auto imageView : m_imageViews){
        vkDestroyImageView(device,imageView,nullptr);

    };

    m_imageViews.clear();

    if (m_swapchain != VK_NULL_HANDLE) {
        vkDestroySwapchainKHR(device, m_swapchain, nullptr);
        m_swapchain = VK_NULL_HANDLE;
    }
}


void Swapchain::recreate(uint32_t width, uint32_t height) {
    cleanup();
    create(width, height);
}

void Swapchain::setupFramebuffers(VkRenderPass renderPass) {


    VkDevice device = m_device->getLogicalDevice();
    for (auto framebuffer : m_framebuffers) {
        vkDestroyFramebuffer(device, framebuffer, nullptr);
    }

    m_framebuffers.resize(m_imageViews.size());

    
    for (size_t i = 0; i < m_imageViews.size(); i++) {
        VkImageView attachments[] = { m_imageViews[i] };

        VkFramebufferCreateInfo framebufferInfo{};
        framebufferInfo.sType = VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO;
        framebufferInfo.renderPass = renderPass;
        framebufferInfo.attachmentCount = 1;
        framebufferInfo.pAttachments = attachments; 
        framebufferInfo.width = m_extent.width;
        framebufferInfo.height = m_extent.height;
        framebufferInfo.layers = 1;

        if (vkCreateFramebuffer(device, &framebufferInfo, nullptr, &m_framebuffers[i]) != VK_SUCCESS) {
            LOG_ERROR("Failed to create framebuffer index {0}", i);
            throw std::runtime_error("failed to create framebuffer!");
        }
    }
    LOG_INFO("Successfully created {0} Framebuffers in Swapchain", m_framebuffers.size());
}


void Swapchain::create(uint32_t width, uint32_t height)
{   
    
    SwapChainDetails details = getSwapchainDetails(m_device->getPhysicalDevice(), m_device->getSurface());

   
    VkSurfaceFormatKHR surfaceFormat = chooseSwapSurfaceFormat(details.formats);
    VkPresentModeKHR presentMode = chooseSwapPresentMode(details.presentationModes);
    VkExtent2D extent = chooseSwapExtent(details.surfaceCapabilities, width, height);


    uint32_t imageCount = details.surfaceCapabilities.minImageCount + 1;
    if (details.surfaceCapabilities.maxImageCount > 0 && imageCount > details.surfaceCapabilities.maxImageCount) {
        imageCount = details.surfaceCapabilities.maxImageCount;
    }

   
    VkSwapchainCreateInfoKHR createInfo{};
    createInfo.sType = VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR;
    createInfo.surface = m_device->getSurface();
    createInfo.minImageCount = imageCount;
    createInfo.imageFormat = surfaceFormat.format;
    createInfo.imageColorSpace = surfaceFormat.colorSpace;
    createInfo.imageExtent = extent;
    createInfo.imageArrayLayers = 1; 
    createInfo.imageUsage = VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT;

    // Skia's Ganesh Vulkan backend (SkSurfaces::WrapBackendRenderTarget)
    // requires the wrapped image to also support being sampled/copied,
    // not just used as a color attachment. Request these bits too, if the
    // surface supports them (virtually all desktop drivers do), so the
    // Skia compositor can wrap swapchain images directly.
    VkImageUsageFlags supportedUsage = details.surfaceCapabilities.supportedUsageFlags;
    if (supportedUsage & VK_IMAGE_USAGE_SAMPLED_BIT)
        createInfo.imageUsage |= VK_IMAGE_USAGE_SAMPLED_BIT;
    if (supportedUsage & VK_IMAGE_USAGE_TRANSFER_SRC_BIT)
        createInfo.imageUsage |= VK_IMAGE_USAGE_TRANSFER_SRC_BIT;
    if (supportedUsage & VK_IMAGE_USAGE_TRANSFER_DST_BIT)
        createInfo.imageUsage |= VK_IMAGE_USAGE_TRANSFER_DST_BIT;
    m_imageUsageFlags = createInfo.imageUsage;

    
    QueueFamilyIndices indices = m_device->getQueueFamilyIndices();
    uint32_t queueFamilyIndices[] = { static_cast<uint32_t>(indices.graphicsFamily), static_cast<uint32_t>(indices.presentationFamily) };

    if (indices.graphicsFamily != indices.presentationFamily) {
        
        createInfo.imageSharingMode = VK_SHARING_MODE_CONCURRENT;
        createInfo.queueFamilyIndexCount = 2;
        createInfo.pQueueFamilyIndices = queueFamilyIndices;
    } else {
        createInfo.imageSharingMode = VK_SHARING_MODE_EXCLUSIVE;
    }

    createInfo.preTransform = details.surfaceCapabilities.currentTransform;
    createInfo.compositeAlpha = VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR; 
    createInfo.presentMode = presentMode;
    createInfo.clipped = VK_TRUE;
    createInfo.oldSwapchain = VK_NULL_HANDLE;

   
    if (vkCreateSwapchainKHR(m_device->getLogicalDevice(), &createInfo, nullptr, &m_swapchain) != VK_SUCCESS) {
        LOG_ERROR("Failed to create swapchain!");
        throw std::runtime_error("Swapchain creation failed");
    }

  
    uint32_t actualImageCount = 0;
vkGetSwapchainImagesKHR(m_device->getLogicalDevice(), m_swapchain, &actualImageCount, nullptr);

m_images.resize(actualImageCount);
vkGetSwapchainImagesKHR(m_device->getLogicalDevice(), m_swapchain, &actualImageCount, m_images.data());

    m_imageFormat = surfaceFormat.format;
    m_extent = extent;

 
    m_imageViews.resize(m_images.size());
    for (size_t i = 0; i < m_images.size(); i++) {
        VkImageViewCreateInfo viewInfo{};
        viewInfo.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO;
        viewInfo.image = m_images[i];
        viewInfo.viewType = VK_IMAGE_VIEW_TYPE_2D;
        viewInfo.format = m_imageFormat;
        viewInfo.components.r = VK_COMPONENT_SWIZZLE_IDENTITY;
        viewInfo.components.g = VK_COMPONENT_SWIZZLE_IDENTITY;
        viewInfo.components.b = VK_COMPONENT_SWIZZLE_IDENTITY;
        viewInfo.components.a = VK_COMPONENT_SWIZZLE_IDENTITY;
        viewInfo.subresourceRange.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
        viewInfo.subresourceRange.baseMipLevel = 0;
        viewInfo.subresourceRange.levelCount = 1;
        viewInfo.subresourceRange.baseArrayLayer = 0;
        viewInfo.subresourceRange.layerCount = 1;

        if (vkCreateImageView(m_device->getLogicalDevice(), &viewInfo, nullptr, &m_imageViews[i]) != VK_SUCCESS) {
             LOG_ERROR("Failed to create image views!");
             throw std::runtime_error("Image View creation failed");
        }
    }
    
    LOG_INFO("Swapchain created successfully!");
}

SwapChainDetails Swapchain::getSwapchainDetails(VkPhysicalDevice phyicalDevice, VkSurfaceKHR surface)
{
      SwapChainDetails details;
    vkGetPhysicalDeviceSurfaceCapabilitiesKHR(phyicalDevice,surface,&details.surfaceCapabilities);

    uint32_t formateCount;
    vkGetPhysicalDeviceSurfaceFormatsKHR(phyicalDevice,surface,&formateCount,nullptr);

    if(formateCount != 0){
        details.formats.resize(formateCount);
        vkGetPhysicalDeviceSurfaceFormatsKHR(phyicalDevice,surface,&formateCount,details.formats.data());

    }

   
    uint32_t presentModeCount;
    vkGetPhysicalDeviceSurfacePresentModesKHR(phyicalDevice, surface, &presentModeCount, nullptr);

    if (presentModeCount != 0) {
        details.presentationModes.resize(presentModeCount);
        vkGetPhysicalDeviceSurfacePresentModesKHR(phyicalDevice, surface, &presentModeCount, details.presentationModes.data());
    }

    return details;
}

VkSurfaceFormatKHR Swapchain::chooseSwapSurfaceFormat(const std::vector<VkSurfaceFormatKHR> &availableFormats)
{

    
	
	if (availableFormats.size() == 1 && availableFormats[0].format == VK_FORMAT_UNDEFINED)
	{
		return { VK_FORMAT_R8G8B8A8_UNORM, VK_COLOR_SPACE_SRGB_NONLINEAR_KHR };
	}

	//  search for optimal format
	for (const auto& format : availableFormats)
	{
		if ((format.format == VK_FORMAT_R8G8B8A8_UNORM || format.format == VK_FORMAT_B8G8R8A8_UNORM)
			&& format.colorSpace == VK_COLOR_SPACE_SRGB_NONLINEAR_KHR)
		{
			return format;
		}
	}

	// fallback to frist one 
	return availableFormats[0];
    
}

VkPresentModeKHR Swapchain::chooseSwapPresentMode(const std::vector<VkPresentModeKHR> &availablePresentModes)
{
    //  Mailbox presentation mode
for (const auto& presentationMode : availablePresentModes)
{
	if (presentationMode == VK_PRESENT_MODE_MAILBOX_KHR)
	{
		return presentationMode;
	}
}

// fallback to FIFO
return VK_PRESENT_MODE_FIFO_KHR;
}

VkExtent2D Swapchain::chooseSwapExtent(const VkSurfaceCapabilitiesKHR &capabilities, uint32_t width, uint32_t height)
{
    
	
	if (capabilities.currentExtent.width != std::numeric_limits<uint32_t>::max())
	{
		return capabilities.currentExtent;
	}
	else
	{
		
		VkExtent2D newExtent = {};
		newExtent.width = static_cast<uint32_t>(width);
		newExtent.height = static_cast<uint32_t>(height);

		newExtent.width = std::max<uint32_t>(capabilities.minImageExtent.width, std::min<uint32_t>(capabilities.maxImageExtent.width, newExtent.width));
		newExtent.height = std::max<uint32_t>(capabilities.minImageExtent.height, std::min<uint32_t>(capabilities.maxImageExtent.height, newExtent.height));

		return newExtent;
	}
}

