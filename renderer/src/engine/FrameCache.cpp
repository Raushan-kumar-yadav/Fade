#include "FrameCache.hpp"

FrameCache::FrameCache(size_t maxBytes) : m_maxBytes(maxBytes) {}

std::shared_ptr<DecodedFrame> FrameCache::get(const FrameKey &key) {
  // lock the door
  std::lock_guard<std::mutex> lock(m_mutex);

  // find the data with key
  auto it = m_map.find(key);
  // if not found then return null
  if (it == m_map.end())
    return nullptr;

  // means its recently used
  m_order.splice(m_order.begin(), m_order, it->second.second);

  // return it
  return it->second.first;
}

void FrameCache::put(const FrameKey &key, std::shared_ptr<DecodedFrame> frame) {
  if (!frame)
    return;

  std::lock_guard<std::mutex> lock(m_mutex);

  auto it = m_map.find(key);

  if (it != m_map.end()) {

    // Reorder the linked list
    m_order.splice(m_order.begin(), m_order, it->second.second);

    //  Adjust the RAM budget accurately!
    m_usedBytes -= frameBytes(it->second.first);
    m_usedBytes += frameBytes(frame);

    //  Replace the current frame
    it->second.first = frame;

    // Check budget in case the new frame was bigger
    evictUntilUnderBudget();
    return;
  }

  // --If Not found--
  m_order.push_front(key);
  m_map[key] = {frame, m_order.begin()};
  m_usedBytes += frameBytes(frame);

  evictUntilUnderBudget();
}

void FrameCache::evictClip(const ClipID &clipId) {

  std::lock_guard<std::mutex> lock(m_mutex);

  // loop through each obj in map
  for (auto it = m_map.begin(); it != m_map.end();) {
    if (it->first.first == clipId) {
      m_usedBytes -= frameBytes(it->second.first);
      m_order.erase(it->second.second);
      it = m_map.erase(it);
    } else {
      ++it;
    }
  }
}

void FrameCache::evictUntilUnderBudget() {

  while (m_usedBytes > m_maxBytes && !m_map.empty()) {
    auto lru = m_order.back();
    m_order.pop_back();
    auto it = m_map.find(lru);
    if (it != m_map.end()) {
      m_usedBytes -= frameBytes(it->second.first);
      m_map.erase(it);
    }
  }
}

size_t FrameCache::frameBytes(const std::shared_ptr<DecodedFrame> &f) {
  if (!f)
    return 0;
  return f->sizeBytes();
}