 #pragma once
#include <unordered_map>
#include <mutex>
#include <memory>
#include <string>
#include "core/video/decoder/baseDecoder.hpp"
#include "core/gpu/vulkan/device/DeviceContext.hpp"
#include "core/media/MediaAsset.hpp"

enum class MediaType;

using ClipID = std::string;

class DecoderPool {
public:
     void open(const ClipID& clipId, const std::string& filepath,MediaType type);

     void close(const ClipID& clipId);

     // Returns nullptr if clip not registered
    baseDecoder* checkout(const ClipID& clipId);
    void checkin(const ClipID& clipId);
    bool has(const ClipID& clipId);

    void setDeviceContext(DeviceContext* context) { m_context = context; }

private:
    struct Entry {
        std::unique_ptr<baseDecoder> decoder;
        std::mutex useMutex;  // one job at a time per clip
        bool inUse{false};
    };

    std::unordered_map<ClipID, std::unique_ptr<Entry>> m_pool;
    std::mutex m_poolMutex;
    DeviceContext* m_context;
};