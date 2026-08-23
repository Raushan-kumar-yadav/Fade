#pragma once
#include "DecoderPool.hpp"
#include "FrameCache.hpp"
#include "ThreadPool.hpp"
#include "core/media/LottieAsset.hpp"
#include "core/media/MediaAsset.hpp"
#include <atomic>
#include <memory>
#include <mutex>
#include <unordered_map>
#include <unordered_set>

class DecodeScheduler {
public:
  static DecodeScheduler &get() {
    static DecodeScheduler instance;
    return instance;
  }

  DecoderPool *getDecoderPool() { return &m_decoderPool; }

  std::shared_ptr<DecodedFrame> tryGetFrameFromCache(const ClipID &contentId,
                                                     int64_t frame);

  void registerClip(const ClipID &pumpId, const MediaAsset &asset,
                    const ClipID &contentId = "");

  void registerClipByPath(const ClipID &clipId, const std::string &filepath,
                          MediaType type);

  void unregisterClip(const ClipID &pumpId);
  void prefetchAround(const ClipID &pumpId, int64_t anchorFrame,
                      int radius = 4);

  void registerLottieClip(const ClipID &clipId,
                          std::shared_ptr<LottieAsset> asset, int width,
                          int height, double projectFps);

  void prefetchLottieAround(const ClipID &clipId, double anchorFrame,
                            int radius = 4);

  void unregisterLottieClip(const ClipID &clipId);

private:
  DecodeScheduler() : m_threadPool(4) {}

  //   Video pump
  void startPump(const ClipID &clipId);

  //   Lottie pump
  void startLottiePump(const ClipID &clipId);

  struct LottieClipState {
    std::shared_ptr<LottieAsset> asset;
    int width = 0;
    int height = 0;
    double projectFps = 30.0;
  };

  ThreadPool m_threadPool;
  DecoderPool m_decoderPool;
  FrameCache m_frameCache;

  std::mutex m_pumpMutex;

  // Video pump state
  std::unordered_map<ClipID, int64_t> m_targetFrames;
  std::unordered_map<ClipID, int64_t> m_lastDecoded;
  std::unordered_map<ClipID, int64_t> m_lastAnchorFrame;
  std::unordered_set<ClipID> m_activePumps;

  std::unordered_map<ClipID, ClipID> m_pumpToContent;
  std::unordered_map<ClipID, int> m_contentRefCount;

  // Lottie pump state
  std::unordered_map<ClipID, LottieClipState> m_lottieClips;
  std::unordered_map<ClipID, int64_t> m_lottieTargetFrames;
  std::unordered_map<ClipID, int64_t> m_lottieLastRastered;
  std::unordered_map<ClipID, int64_t> m_lottieLastAnchor;
  std::unordered_set<ClipID> m_activeLottiePumps;
};