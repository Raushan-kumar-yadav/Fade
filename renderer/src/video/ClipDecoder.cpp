#include "video/ClipDecoder.hpp"
#include <algorithm>
#include <iostream>

ClipDecoder::ClipDecoder(const std::string& filepath, DeviceContext* device, float previewScale)
    : m_previewScale(previewScale) {
    // Try hardware (D3D11VA) first
    try {
        auto hw = std::make_unique<HWVideoDecoder>(filepath, device, previewScale);
        m_decoder = std::move(hw);
        m_valid   = true;
        std::cout << "[ClipDecoder] HW decode: " << filepath << "\n";
        return;
    } catch (const std::exception& e) {
        std::cerr << "[ClipDecoder] HW failed (" << e.what() << "), falling back to SW\n";
    }

    // Software fallback
    try {
        m_decoder = std::make_unique<videoDecoder>(filepath);
        m_valid   = true;
        std::cout << "[ClipDecoder] SW decode: " << filepath << "\n";
    } catch (const std::exception& e) {
        std::cerr << "[ClipDecoder] SW also failed: " << e.what() << "\n";
        m_valid = false;
    }
}

ClipDecoder::DecodeResult ClipDecoder::decodeFrame(int64_t frameNumber) {
    if (!m_valid || !m_decoder) return {};

    auto frame = m_decoder->decodeFrame(frameNumber);
    if (!frame || !frame->valid) return {};

    const int w = frame->width;
    const int h = frame->height;

    // If already RGBA (SOFTWARE_RGBA) — return directly
    if (frame->type == FrameType::SOFTWARE_RGBA && !frame->dataRGBA.empty())
        return { std::move(frame->dataRGBA), w, h };

    // Convert YUV I420 → RGBA using manual conversion
    if (frame->type == FrameType::SOFTWARE_YUV &&
        !frame->dataY.empty() && !frame->dataU.empty() && !frame->dataV.empty()) {

        std::vector<uint8_t> rgba(static_cast<size_t>(w) * h * 4);

        const uint8_t* Y = frame->dataY.data();
        const uint8_t* U = frame->dataU.data();
        const uint8_t* V = frame->dataV.data();

        for (int row = 0; row < h; ++row) {
            for (int col = 0; col < w; ++col) {
                const int uvIdx = (row / 2) * (w / 2) + (col / 2);
                const int y =  Y[row * w + col];
                const int u = U[uvIdx] - 128;
                const int v = V[uvIdx] - 128;

                const int r = y + (int)(1.402f  * v);
                const int g = y - (int)(0.344f  * u + 0.714f * v);
                const int b = y + (int)(1.772f  * u);

                const size_t idx = static_cast<size_t>(row * w + col) * 4;
                rgba[idx + 0] = static_cast<uint8_t>(std::clamp(r, 0, 255)); // R
                rgba[idx + 1] = static_cast<uint8_t>(std::clamp(g, 0, 255)); // G
                rgba[idx + 2] = static_cast<uint8_t>(std::clamp(b, 0, 255)); // B
                rgba[idx + 3] = 255;
            }
        }
        return { std::move(rgba), w, h };
    }

    // NV12 (HW cached) → RGBA
    if (frame->type == FrameType::HARDWARE_CACHED &&
        !frame->dataNV12Y.empty() && !frame->dataNV12UV.empty()) {

        std::vector<uint8_t> rgba(static_cast<size_t>(w) * h * 4);
        const uint8_t* Y   = frame->dataNV12Y.data();
        const uint8_t* UV  = frame->dataNV12UV.data();

        for (int row = 0; row < h; ++row) {
            for (int col = 0; col < w; ++col) {
                const int uvBase = (row / 2) * w + (col & ~1);
                const int y  =  Y[row * w + col];
                const int u  = UV[uvBase]     - 128;
                const int v  = UV[uvBase + 1] - 128;

                const int r = y + (int)(1.402f  * v);
                const int g = y - (int)(0.344f  * u + 0.714f * v);
                const int b = y + (int)(1.772f  * u);

                const size_t idx = static_cast<size_t>(row * w + col) * 4;
                rgba[idx + 0] = static_cast<uint8_t>(std::clamp(r, 0, 255)); // R
                rgba[idx + 1] = static_cast<uint8_t>(std::clamp(g, 0, 255)); // G
                rgba[idx + 2] = static_cast<uint8_t>(std::clamp(b, 0, 255)); // B
                rgba[idx + 3] = 255;
            }
        }
        return { std::move(rgba), w, h };
    }

    return {};
}

bool ClipDecoder::decodeFrameDirect(int64_t frameNumber, uint8_t* dstBuffer,
                                    int dstW, int dstH) {
    if (!m_valid || !m_decoder) return false;
    return m_decoder->decodeFrameDirect(frameNumber, dstBuffer, dstW, dstH);
}

int    ClipDecoder::width()    const { return m_decoder ? m_decoder->getWidth()    : 0; }
int    ClipDecoder::height()   const { return m_decoder ? m_decoder->getHeight()   : 0; }
double ClipDecoder::fps()      const { return m_decoder ? m_decoder->getFps()      : 0; }
double ClipDecoder::duration() const { return m_decoder ? m_decoder->getDuration() : 0; }
