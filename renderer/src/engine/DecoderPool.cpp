#include "DecoderPool.hpp"
#include <iostream>
#include "core/video/decoder/imageDecorder.hpp"
#include "core/video/decoder/videoDecoder.hpp"
#include "core/video/decoder/HwVideoDecoder.hpp"
#include "core/AppSettings.hpp"

void DecoderPool::open(const ClipID &clipId, const std::string &filepath , MediaType type)
{
    std::lock_guard<std::mutex> lock(m_poolMutex);
    if(m_pool.count(clipId)) return; 

    auto entry = std::make_unique<Entry>();

    if (type == MediaType::image) {
        entry->decoder = std::make_unique<imageDecorder>(filepath);
        LOG_INFO("[DecoderPool] Image decoder created for: " + filepath);
    } 
    else if (type == MediaType::video) {
         
        bool useHardwareSettings = AppSettings::get().isHardwareDecodingEnabled();
        bool deviceSupportsVideoDecode = m_context && m_context->isVideoDecodeSupported();
        
        LOG_INFO("========================================");
        LOG_INFO("[DecoderPool] Opening video: " + filepath);
        LOG_INFO("[DecoderPool] HW decode setting: " + std::string(useHardwareSettings ? "ENABLED" : "DISABLED"));
        LOG_INFO("[DecoderPool] Device context:    " + std::string(m_context ? "PRESENT" : "NULL"));
        LOG_INFO("[DecoderPool] VK_KHR_video_decode_queue: " + std::string(deviceSupportsVideoDecode ? "SUPPORTED" : "NOT SUPPORTED"));
        
        if (useHardwareSettings && m_context != nullptr && deviceSupportsVideoDecode) {
            try {
                 entry->decoder = std::make_unique<HWVideoDecoder>(filepath, m_context);
                 LOG_INFO("[DecoderPool] >>> DECODING MODE: GPU (Vulkan Hardware) <<<");
             } 
            catch (const std::exception& e) {
                 LOG_WARN("[DecoderPool] HW decoder failed: " + std::string(e.what()));
                 entry->decoder = std::make_unique<videoDecoder>(filepath);
                 LOG_INFO("[DecoderPool] >>> DECODING MODE: CPU (Software Fallback) <<<");
            }
        } 
        else {
             entry->decoder = std::make_unique<videoDecoder>(filepath);
             if (!useHardwareSettings) {
                 LOG_INFO("[DecoderPool] >>> DECODING MODE: CPU (HW decode disabled in settings) <<<");
             } else if (!deviceSupportsVideoDecode) {
                 LOG_WARN("[DecoderPool] >>> DECODING MODE: CPU (GPU lacks VK_KHR_video_decode_queue) <<<");
             } else {
                 LOG_INFO("[DecoderPool] >>> DECODING MODE: CPU (No device context) <<<");
             }
        }   
        LOG_INFO("========================================");
    }

    m_pool[clipId] = std::move(entry);
}

void DecoderPool::close(const ClipID &clipId)
{
    std::unique_ptr<Entry> entryToDestroy;
    {
        std::lock_guard<std::mutex> lock(m_poolMutex);
        auto it = m_pool.find(clipId);
        if(it != m_pool.end()){
            entryToDestroy = std::move(it->second);
            m_pool.erase(it);
        }
    }
    
 
    if (entryToDestroy) {
        std::lock_guard<std::mutex> waitLock(entryToDestroy->useMutex);
    }
}

void DecoderPool::checkin(const ClipID& clipId)
{
    Entry* entry = nullptr;
    {
        std::lock_guard<std::mutex> lock(m_poolMutex);
        auto it = m_pool.find(clipId);
        if (it == m_pool.end()) return;
        entry = it->second.get();
    }
     
    entry->inUse = false;
    entry->useMutex.unlock();
}
baseDecoder* DecoderPool::checkout(const ClipID& clipId)
{
     Entry* entry = nullptr;
    {
        std::lock_guard<std::mutex> lock(m_poolMutex);
        auto it = m_pool.find(clipId);
        if (it == m_pool.end()) return nullptr;
        entry = it->second.get();
    }
 
     entry->useMutex.lock();   // blocks if another worker has this clip
    entry->inUse = true;
    return entry->decoder.get();
}

bool DecoderPool::has(const ClipID& clipId) {
    std::lock_guard<std::mutex> lock(m_poolMutex);
    return m_pool.count(clipId) > 0;
}
