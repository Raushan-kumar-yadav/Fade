#pragma once
#include <cstdint>
#include <iostream>
#include <memory> 
#include "gpu/vulkan/data/DecodedFrame.hpp"

class baseDecoder
{

public:
    virtual ~baseDecoder() = default;
    virtual std::shared_ptr<DecodedFrame> decodeFrame(int64_t frameNumber) = 0;

    // Zero-copy decode: sws_scale writes RGBA directly to dstBuffer.
    // Returns true on success. Default: not supported (returns false).
    virtual bool decodeFrameDirect(int64_t frameNumber, uint8_t* dstBuffer,
                                   int dstW, int dstH) { return false; }

    virtual int  getWidth() const = 0;
    virtual  int getHeight() const = 0;
    virtual  double getDuration() const = 0;
    virtual double getFps() const = 0;
};


