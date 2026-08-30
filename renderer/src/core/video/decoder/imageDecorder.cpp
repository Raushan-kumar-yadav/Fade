#define STB_IMAGE_IMPLEMENTATION
#include "stb/stb_image.h"
#include "core/video/decoder/imageDecorder.hpp"
#include "core/api/Logger.hpp"
#include <cstring>


imageDecorder::imageDecorder(const std::string &filePath) : m_filepath(filePath)
{
     m_cachedFrame = nullptr;
}

std::shared_ptr<DecodedFrame> imageDecorder::decodeFrame(int64_t frame) 
{
     if (m_cachedFrame && m_cachedFrame->valid) {
        m_cachedFrame->frameNumber = frame; 
        return m_cachedFrame; 
    }
    
     int localWidth, localHeight, localChannels;
     unsigned char* rawPixels = stbi_load(m_filepath.c_str(), &localWidth, &localHeight, &localChannels, 4);
    
    if (!rawPixels) {
        LOG_ERROR("Failed to load STB image: " + m_filepath);
        return nullptr;
    }

    m_width = localWidth;
    m_height = localHeight;
    m_channels = 4;

    m_cachedFrame = std::make_shared<DecodedFrame>();
    m_cachedFrame->type = FrameType::SOFTWARE_RGBA;
    m_cachedFrame->width = m_width;     
    m_cachedFrame->height = m_height;  
    m_cachedFrame->pts = 0; 
    m_cachedFrame->frameNumber = frame;
    m_cachedFrame->valid = true;
    m_cachedFrame->isStatic = true; 
    
    size_t dataSize = m_width * m_height * 4;
    m_cachedFrame->dataRGBA.resize(dataSize);
    std::memcpy(m_cachedFrame->dataRGBA.data(), rawPixels, dataSize);

    stbi_image_free(rawPixels);
    
    LOG_INFO("Worker thread successfully decoded STB Image.");
    return m_cachedFrame; 
}

double imageDecorder::getDuration() const
{
    return 0.0;
}

double imageDecorder::getFps() const
{
    return 0.0;
}

VkDeviceSize imageDecorder::getImageSize() const
{   
    return static_cast<VkDeviceSize>(m_width * m_height * 4);
}
