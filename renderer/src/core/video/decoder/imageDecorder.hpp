#pragma once
#include "video/baseDecoder.hpp"
#include "vulkan/vulkan.h"
#include "gpu/vulkan/data/DecodedFrame.hpp"




class imageDecorder : public baseDecoder
{
private:
unsigned char* m_pixelData = nullptr;
int m_width , m_height , m_channels;
std::string m_filepath;
    
std::shared_ptr<DecodedFrame> m_cachedFrame = nullptr;


public:
    imageDecorder(const std::string& filePath );
    ~imageDecorder() override = default;

    virtual std::shared_ptr<DecodedFrame> decodeFrame(int64_t frameNumber) override ;

    VkDeviceSize getImageSize();
    int getWidth() const override {return m_width;}
    int getHeight() const override {return m_height;}
    double getDuration() const override;
    double getFps() const override;
    VkDeviceSize getImageSize() const;
};
