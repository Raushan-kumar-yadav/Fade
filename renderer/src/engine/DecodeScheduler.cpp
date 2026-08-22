#include "DecodeScheduler.hpp"

#include "core/api/Logger.hpp"
#include "include/core/SkBitmap.h"
#include "include/core/SkCanvas.h"
#include "include/core/SkImageInfo.h"

std::shared_ptr<DecodedFrame>
DecodeScheduler::tryGetFrameFromCache(const ClipID &contentId, int64_t frame) {
  return m_frameCache.get({contentId, frame});
}

void DecodeScheduler::prefetchAround(const ClipID &clipId, int64_t anchorFrame,
                                     int radius) {

  bool needsPump = false;

  {
    std::lock_guard<std::mutex> lock(m_pumpMutex);

    int64_t lastAnchor = m_lastAnchorFrame[clipId];
    int64_t last = m_lastDecoded[clipId];

    bool seekedForward = (anchorFrame > lastAnchor + 30);
    bool seekedBackward = (anchorFrame < lastAnchor - 5);

    if (seekedForward || seekedBackward) {
      m_lastDecoded[clipId] = anchorFrame - 1;
      m_targetFrames[clipId] = anchorFrame + radius;
      LOG_INFO("Hard Seek triggered for " + clipId + " to frame " +
               std::to_string(anchorFrame));
    }

    m_lastAnchorFrame[clipId] = anchorFrame;

    // Keep the target runway moving
    if (anchorFrame + radius > m_targetFrames[clipId]) {
      m_targetFrames[clipId] = anchorFrame + radius;
    }

    if (m_lastDecoded[clipId] < m_targetFrames[clipId]) {
      needsPump = true;
    }
  }

  if (needsPump) {
    startPump(clipId);
  }
}

void DecodeScheduler::startPump(const ClipID &pumpId) {
  std::lock_guard<std::mutex> lock(m_pumpMutex);
  if (m_activePumps.count(pumpId) > 0)
    return;

  m_activePumps.insert(pumpId);

  m_threadPool.submitWork([this, pumpId]() {
    // Resolve shared content ID for frame cache
    ClipID contentId;
    {
      std::lock_guard<std::mutex> l(m_pumpMutex);
      auto it = m_pumpToContent.find(pumpId);
      if (it == m_pumpToContent.end()) {
        m_activePumps.erase(pumpId);
        return;
      }
      contentId = it->second;
    }

    baseDecoder *dec = m_decoderPool.checkout(pumpId);
    if (!dec) {
      LOG_ERROR("DecoderPool checkout failed! Decoder doesn't exist for: " +
                pumpId);
      std::lock_guard<std::mutex> l(m_pumpMutex);
      m_activePumps.erase(pumpId);
      return;
    }

    const int BATCH_SIZE = 5;
    int framesDecodedThisRun = 0;
    bool needsMoreWork = false;

    while (framesDecodedThisRun < BATCH_SIZE) {
      int64_t target = 0;
      int64_t current = 0;

      {
        std::lock_guard<std::mutex> l(m_pumpMutex);
        target = m_targetFrames[pumpId];
        current = m_lastDecoded[pumpId];
      }

      if (current >= target) {
        break;
      }

      int64_t nextFrame = current + 1;
      bool success = false;

      // Check shared content cache first
      if (m_frameCache.get({contentId, nextFrame}) != nullptr) {
        success = true;
      } else {
        auto f = dec->decodeFrame(nextFrame);
        if (f) {
          // Store under contentId
          m_frameCache.put({contentId, nextFrame}, f);
          success = true;
        }
      }

      if (success) {
        std::lock_guard<std::mutex> l(m_pumpMutex);
        m_lastDecoded[pumpId] = nextFrame;
        framesDecodedThisRun++;
      } else {
        LOG_WARN("Pump failed to decode frame " + std::to_string(nextFrame) +
                 ". Reached EOF?");

        std::lock_guard<std::mutex> l(m_pumpMutex);
        m_targetFrames[pumpId] = m_lastDecoded[pumpId];

        break;
      }
    }

    m_decoderPool.checkin(pumpId);

    {
      std::lock_guard<std::mutex> l(m_pumpMutex);
      m_activePumps.erase(pumpId);
      needsMoreWork = (m_lastDecoded[pumpId] < m_targetFrames[pumpId]);
    }

    if (needsMoreWork) {
      startPump(pumpId);
    }
  });
}

void DecodeScheduler::registerClip(const ClipID &pumpId,
                                   const MediaAsset &asset,
                                   const ClipID &contentId) {
  // Resolve which content ID to use for the shared frame cache
  const ClipID &cid = contentId.empty() ? pumpId : contentId;

  if (!m_decoderPool.has(pumpId)) {
    m_decoderPool.open(pumpId, asset.getFilepath(), asset.getType());
    std::lock_guard<std::mutex> lock(m_pumpMutex);
    m_lastDecoded[pumpId] = -1;
    m_pumpToContent[pumpId] = cid;
    m_contentRefCount[cid]++;
  }
}

void DecodeScheduler::unregisterClip(const ClipID &pumpId) {
  ClipID contentId;
  {
    std::lock_guard<std::mutex> lock(m_pumpMutex);
    m_targetFrames.erase(pumpId);
    m_lastDecoded.erase(pumpId);
    m_lastAnchorFrame.erase(pumpId);

    auto cit = m_pumpToContent.find(pumpId);
    if (cit != m_pumpToContent.end()) {
      contentId = cit->second;
      m_pumpToContent.erase(cit);
      if (--m_contentRefCount[contentId] <= 0) {
        m_contentRefCount.erase(contentId);
      }
    }
  }
  if (!contentId.empty() &&
      m_contentRefCount.find(contentId) == m_contentRefCount.end()) {
    m_frameCache.evictClip(contentId);
  }
  m_decoderPool.close(pumpId);
}

void DecodeScheduler::registerLottieClip(const ClipID &clipId,
                                         std::shared_ptr<LottieAsset> asset,
                                         int width, int height,
                                         double projectFps) {
  std::lock_guard<std::mutex> lock(m_pumpMutex);
  if (m_lottieClips.count(clipId))
    return;

  constexpr int MAX_PUMP_DIM = 512;
  int cappedW = width;
  int cappedH = height;
  if (cappedW > MAX_PUMP_DIM || cappedH > MAX_PUMP_DIM) {
    float scale = static_cast<float>(MAX_PUMP_DIM) /
                  static_cast<float>(std::max(cappedW, cappedH));
    cappedW = std::max(1, static_cast<int>(cappedW * scale));
    cappedH = std::max(1, static_cast<int>(cappedH * scale));
  }

  m_lottieClips[clipId] = {asset, cappedW, cappedH, projectFps};
  m_lottieLastRastered[clipId] = -1;
  m_lottieLastAnchor[clipId] = -1;
  LOG_INFO("[LottiePump] Registered clip: " + clipId + " (" +
           std::to_string(cappedW) + "x" + std::to_string(cappedH) +
           ", capped from " + std::to_string(width) + "x" +
           std::to_string(height) + ")");
}

void DecodeScheduler::unregisterLottieClip(const ClipID &clipId) {
  {
    std::lock_guard<std::mutex> lock(m_pumpMutex);
    m_lottieClips.erase(clipId);
    m_lottieTargetFrames.erase(clipId);
    m_lottieLastRastered.erase(clipId);
    m_lottieLastAnchor.erase(clipId);
  }
  m_frameCache.evictClip(clipId);
  LOG_INFO("[LottiePump] Unregistered clip: " + clipId);
}

void DecodeScheduler::prefetchLottieAround(const ClipID &clipId,
                                           double anchorTimeSec, int radius) {
  double projectFps = 30.0;
  {
    std::lock_guard<std::mutex> lock(m_pumpMutex);
    auto it = m_lottieClips.find(clipId);
    if (it == m_lottieClips.end())
      return;
    projectFps = it->second.projectFps;
  }

  int64_t anchorFrame = static_cast<int64_t>(anchorTimeSec * projectFps);

  bool needsPump = false;
  {
    std::lock_guard<std::mutex> lock(m_pumpMutex);

    int64_t lastAnchor = m_lottieLastAnchor[clipId];

    bool seekedForward = (anchorFrame > lastAnchor + 30);
    bool seekedBackward = (anchorFrame < lastAnchor - 5);

    if (seekedForward || seekedBackward) {
      m_lottieLastRastered[clipId] = anchorFrame - 1;
      m_lottieTargetFrames[clipId] = anchorFrame + radius;
      LOG_INFO("[LottiePump] Hard seek for " + clipId + " to frame " +
               std::to_string(anchorFrame));
    }

    m_lottieLastAnchor[clipId] = anchorFrame;

    if (anchorFrame + radius > m_lottieTargetFrames[clipId])
      m_lottieTargetFrames[clipId] = anchorFrame + radius;

    if (m_lottieLastRastered[clipId] < m_lottieTargetFrames[clipId])
      needsPump = true;
  }

  if (needsPump)
    startLottiePump(clipId);
}

void DecodeScheduler::startLottiePump(const ClipID &clipId) {
  {
    std::lock_guard<std::mutex> lock(m_pumpMutex);
    if (m_activeLottiePumps.count(clipId))
      return;
    m_activeLottiePumps.insert(clipId);
  }

  m_threadPool.submitWork([this, clipId]() {
    try {
      LottieClipState state;
      {
        std::lock_guard<std::mutex> l(m_pumpMutex);
        auto it = m_lottieClips.find(clipId);
        if (it == m_lottieClips.end()) {
          m_activeLottiePumps.erase(clipId);
          return;
        }
        state = it->second;
      }

      auto anim = state.asset->createAnimation();
      if (!anim) {
        LOG_ERROR("[LottiePump] createAnimation() failed for " + clipId);
        std::lock_guard<std::mutex> l(m_pumpMutex);
        m_activeLottiePumps.erase(clipId);
        return;
      }

      SkBitmap bitmap;
      SkImageInfo imgInfo =
          SkImageInfo::Make(state.width, state.height, kRGBA_8888_SkColorType,
                            kPremul_SkAlphaType);
      if (!bitmap.tryAllocPixels(imgInfo)) {
        LOG_ERROR("[LottiePump] SkBitmap alloc failed w=" +
                  std::to_string(state.width) +
                  " h=" + std::to_string(state.height));
        std::lock_guard<std::mutex> l(m_pumpMutex);
        m_activeLottiePumps.erase(clipId);
        return;
      }
      SkRect bounds = SkRect::MakeWH(static_cast<float>(state.width),
                                     static_cast<float>(state.height));
      size_t byteCount = static_cast<size_t>(bitmap.computeByteSize());
      const int BATCH_SIZE = 15;
      int framesDecodedThisRun = 0;
      bool needsMoreWork = false;

      while (framesDecodedThisRun < BATCH_SIZE) {
        int64_t target = 0;
        int64_t current = 0;
        {
          std::lock_guard<std::mutex> l(m_pumpMutex);
          target = m_lottieTargetFrames[clipId];
          current = m_lottieLastRastered[clipId];
        }

        if (current >= target)
          break;

        int64_t nextFrame = current + 1;
        bool success = false;

        if (m_frameCache.get({clipId, nextFrame}) != nullptr) {
          success = true;
        } else {
          double t = static_cast<double>(nextFrame) / state.projectFps;
          SkCanvas canvas(bitmap);
          canvas.clear(SK_ColorTRANSPARENT);
          anim->seekFrameTime(static_cast<float>(t));
          anim->render(&canvas, &bounds);

          auto frame = std::make_shared<DecodedFrame>();
          frame->type = FrameType::SOFTWARE_RGBA;
          frame->frameNumber = nextFrame;
          frame->width = static_cast<uint32_t>(state.width);
          frame->height = static_cast<uint32_t>(state.height);
          frame->channels = 4;
          frame->valid = true;
          frame->dataRGBA.resize(byteCount);
          std::memcpy(frame->dataRGBA.data(), bitmap.getPixels(), byteCount);

          m_frameCache.put({clipId, nextFrame}, frame);
          success = true;
        }

        if (success) {
          std::lock_guard<std::mutex> l(m_pumpMutex);
          m_lottieLastRastered[clipId] = nextFrame;
          framesDecodedThisRun++;
        } else {
          break;
        }
      }

      {
        std::lock_guard<std::mutex> l(m_pumpMutex);
        m_activeLottiePumps.erase(clipId);
        needsMoreWork =
            (m_lottieLastRastered[clipId] < m_lottieTargetFrames[clipId]);
      }

      if (needsMoreWork) {
        startLottiePump(clipId);
      }

    } catch (const std::exception &e) {
      LOG_ERROR("[LottiePump] EXCEPTION in pump: " + std::string(e.what()));
      std::lock_guard<std::mutex> l(m_pumpMutex);
      m_activeLottiePumps.erase(clipId);
    } catch (...) {
      LOG_ERROR("[LottiePump] UNKNOWN EXCEPTION in pump!");
      std::lock_guard<std::mutex> l(m_pumpMutex);
      m_activeLottiePumps.erase(clipId);
    }
  });
}
