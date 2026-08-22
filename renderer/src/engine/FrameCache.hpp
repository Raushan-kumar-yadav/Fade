#pragma once
#include <unordered_map>
#include <list>
#include <mutex>
#include <memory>
#include <string>
#include "core/gpu/vulkan/data/DecodedFrame.hpp"

using ClipID = std::string;
using FrameKey = std::pair<ClipID, int64_t>;

struct FrameKeyHash {
    size_t operator()(const FrameKey& k) const {
        return std::hash<std::string>()(k.first) ^ std::hash<int64_t>()(k.second);
    }
};

class FrameCache {
public:
    explicit FrameCache(size_t maxBytes = 2048ULL * 1024 * 1024); // 2000MB default

    std::shared_ptr<DecodedFrame> get(const FrameKey& key);
    void put(const FrameKey& key, std::shared_ptr<DecodedFrame> frame);
    void evictClip(const ClipID& clipId);   // call on goToSleep

private:

    void evictUntilUnderBudget();
    size_t frameBytes(const std::shared_ptr<DecodedFrame>& f);

    using LRUList = std::list<FrameKey>;
    using LRUMap = std::unordered_map<FrameKey, std::pair<std::shared_ptr<DecodedFrame>, LRUList::iterator>,FrameKeyHash>;

    LRUList m_order;   // front = MRU, back = LRU
    LRUMap m_map;
    size_t m_maxBytes{0};
    size_t m_usedBytes{0};
    std::mutex m_mutex;
};