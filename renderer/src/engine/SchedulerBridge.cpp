

#include "SchedulerBridge.hpp"
#include "gpu/vulkan/device/DeviceContext.hpp"
#include "video/ClipDecoder.hpp"

#include <atomic>
#include <condition_variable>
#include <functional>
#include <iostream>
#include <list>
#include <memory>
#include <mutex>
#include <queue>
#include <thread>
#include <unordered_map>
#include <unordered_set>
#include <vector>

class MiniThreadPool {
public:
  explicit MiniThreadPool(size_t threads) : m_stop(false) {
    for (size_t i = 0; i < threads; ++i) {
      m_workers.emplace_back([this] {
        while (true) {
          std::function<void()> task;
          {
            std::unique_lock<std::mutex> lock(m_mutex);
            m_cv.wait(lock, [this] { return m_stop || !m_tasks.empty(); });
            if (m_stop && m_tasks.empty())
              return;
            task = std::move(m_tasks.front());
            m_tasks.pop();
          }
          task();
        }
      });
    }
  }

  ~MiniThreadPool() {
    {
      std::lock_guard<std::mutex> lock(m_mutex);
      m_stop = true;
    }
    m_cv.notify_all();
    for (auto &w : m_workers)
      w.join();
  }

  void enqueue(std::function<void()> task) {
    {
      std::lock_guard<std::mutex> lock(m_mutex);
      m_tasks.push(std::move(task));
    }
    m_cv.notify_one();
  }

private:
  std::vector<std::thread> m_workers;
  std::queue<std::function<void()>> m_tasks;
  std::mutex m_mutex;
  std::condition_variable m_cv;
  bool m_stop;
};

using CacheKey = std::pair<std::string, int64_t>;

struct CacheKeyHash {
  size_t operator()(const CacheKey &k) const {
    return std::hash<std::string>()(k.first) ^
           (std::hash<int64_t>()(k.second) << 1);
  }
};

struct CachedEntry {
  std::vector<uint8_t> rgba;
  uint32_t width = 0;
  uint32_t height = 0;
};

class MiniFrameCache {
public:
  explicit MiniFrameCache(size_t maxBytes = 1024ULL * 1024 * 1024)
      : m_maxBytes(maxBytes) {} // 1GB default

  std::shared_ptr<CachedEntry> get(const CacheKey &key) {
    std::lock_guard<std::mutex> lock(m_mutex);
    auto it = m_map.find(key);
    if (it == m_map.end())
      return nullptr;
    // Move to front (MRU)
    m_order.splice(m_order.begin(), m_order, it->second.second);
    return it->second.first;
  }

  void put(const CacheKey &key, std::shared_ptr<CachedEntry> entry) {
    if (!entry || entry->rgba.empty())
      return;
    std::lock_guard<std::mutex> lock(m_mutex);

    auto it = m_map.find(key);
    if (it != m_map.end()) {
      m_usedBytes -= it->second.first->rgba.size();
      m_order.erase(it->second.second);
      m_map.erase(it);
    }

    m_order.push_front(key);
    m_map[key] = {entry, m_order.begin()};
    m_usedBytes += entry->rgba.size();

    // Evict LRU entries if over budget
    while (m_usedBytes > m_maxBytes && !m_order.empty()) {
      auto lru = m_order.back();
      m_order.pop_back();
      auto mit = m_map.find(lru);
      if (mit != m_map.end()) {
        m_usedBytes -= mit->second.first->rgba.size();
        m_map.erase(mit);
      }
    }
  }

private:
  using LRUList = std::list<CacheKey>;
  using LRUMap = std::unordered_map<
      CacheKey, std::pair<std::shared_ptr<CachedEntry>, LRUList::iterator>,
      CacheKeyHash>;

  LRUList m_order;
  LRUMap m_map;
  size_t m_maxBytes;
  size_t m_usedBytes = 0;
  std::mutex m_mutex;
};

struct ClipState {
  std::unique_ptr<ClipDecoder> decoder;
  std::mutex decoderMutex; // one decode at a time per clip
  int64_t lastDecoded = -1;
};

class MiniScheduler {
public:
  static MiniScheduler &get() {
    static MiniScheduler instance;
    return instance;
  }

  void setDeviceContext(DeviceContext *ctx) { m_deviceCtx = ctx; }

  void registerVideo(const std::string &clipId, const std::string &filepath) {
    std::lock_guard<std::mutex> lock(m_clipsMutex);
    if (m_clips.count(clipId))
      return;
    auto state = std::make_unique<ClipState>();
    state->decoder = std::make_unique<ClipDecoder>(filepath, m_deviceCtx, 1.0f);
    m_clips[clipId] = std::move(state);
    std::cout << "[MiniScheduler] Registered: " << clipId << "\n";
  }

  void registerImage(const std::string &clipId, const std::string &filepath) {
    registerVideo(clipId, filepath); // same decoder handles images
  }

  void prefetchAround(const std::string &clipId, int64_t anchor, int radius) {
    for (int offset = 0; offset <= radius; ++offset) {
      int64_t frame = anchor + offset;
      CacheKey key{clipId, frame};

      // Already cached?
      if (m_cache.get(key))
        continue;

      // Already being decoded?
      {
        std::lock_guard<std::mutex> lock(m_pendingMutex);
        if (m_pending.count(key))
          continue;
        m_pending.insert(key);
      }

      // Submit decode job to thread pool
      m_pool.enqueue([this, clipId, frame, key]() {
        ClipState *state = nullptr;
        {
          std::lock_guard<std::mutex> lock(m_clipsMutex);
          auto it = m_clips.find(clipId);
          if (it == m_clips.end()) {
            std::lock_guard<std::mutex> plock(m_pendingMutex);
            m_pending.erase(key);
            return;
          }
          state = it->second.get();
        }

        // Lock this clip's decoder
        std::lock_guard<std::mutex> dlock(state->decoderMutex);

        auto result = state->decoder->decodeFrame(frame);
        if (!result.rgba.empty()) {
          auto entry = std::make_shared<CachedEntry>();
          entry->rgba = std::move(result.rgba);
          entry->width = result.width;
          entry->height = result.height;
          m_cache.put(key, entry);
        }

        {
          std::lock_guard<std::mutex> plock(m_pendingMutex);
          m_pending.erase(key);
        }
      });
    }
  }

  CachedFrameData tryGetCachedFrame(const std::string &clipId, int64_t frame) {
    CacheKey key{clipId, frame};
    auto entry = m_cache.get(key);
    if (!entry || entry->rgba.empty())
      return {};

    // Move the shared_ptr
    auto *handle = new std::shared_ptr<CachedEntry>(std::move(entry));

    CachedFrameData result;
    result.data = (*handle)->rgba.data();
    result.dataSize = (*handle)->rgba.size();
    result.width = (*handle)->width;
    result.height = (*handle)->height;
    result.valid = true;
    result._handle = handle;
    return result;
  }

  void releaseCachedFrame(CachedFrameData &cfd) {
    if (cfd._handle) {
      delete static_cast<std::shared_ptr<CachedEntry> *>(cfd._handle);
      cfd._handle = nullptr;
      cfd.data = nullptr;
      cfd.valid = false;
    }
  }

private:
  MiniScheduler() : m_pool(4) {}

  MiniThreadPool m_pool;
  MiniFrameCache m_cache;

  std::unordered_map<std::string, std::unique_ptr<ClipState>> m_clips;
  std::mutex m_clipsMutex;

  std::unordered_set<CacheKey, CacheKeyHash> m_pending;
  std::mutex m_pendingMutex;

  DeviceContext *m_deviceCtx = nullptr;
};

CachedFrameData tryGetCachedFrame(const std::string &clipId, int64_t frame) {
  return MiniScheduler::get().tryGetCachedFrame(clipId, frame);
}

void releaseCachedFrame(CachedFrameData &cfd) {
  MiniScheduler::get().releaseCachedFrame(cfd);
}

void schedRegisterVideo(const std::string &clipId,
                        const std::string &filepath) {
  MiniScheduler::get().registerVideo(clipId, filepath);
}

void schedRegisterImage(const std::string &clipId,
                        const std::string &filepath) {
  MiniScheduler::get().registerImage(clipId, filepath);
}

void schedPrefetchAround(const std::string &clipId, int64_t anchorFrame,
                         int radius) {
  MiniScheduler::get().prefetchAround(clipId, anchorFrame, radius);
}

void schedSetDeviceContext(void *deviceCtx) {
  MiniScheduler::get().setDeviceContext(
      static_cast<DeviceContext *>(deviceCtx));
}
