from __future__ import annotations
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from backend.media.cache.frameCache import FrameCache
from backend.media.decoder.decoderPool import DecoderPool
from backend.media.decoder.decodedFrame import DecodedFrame
from backend.media.asset.mediaAsset import MediaAsset


class DecodeScheduler:
    """
    Orchestrates background prefetch decoding.
    Port of C++ DecodeScheduler.

    Flow (mirrors C++ exactly):
      1. VideoClip.render() calls tryGetFrameFromCache().
      2. If found  → return immediately (fast path, no FFmpeg).
      3. If missing → return a black frame THIS frame, trigger prefetchAround().
      4. prefetchAround() detects seeks and triggers startPump() in a thread.
      5. startPump() decodes BATCH_SIZE frames and puts them in FrameCache.

    Shared content deduplication:
      - Two clips on the same source file have different clipIds (pumpIds)
        but the same contentId (= assetId).
      - FrameCache is keyed by contentId — so the second clip hits the cache
        for any frame the first clip already decoded.
    """

    BATCH_SIZE = 5    # frames decoded per pump run
    SEEK_FWD_THRESH = 30   # frames: forward jump this big = hard seek
    SEEK_BWD_THRESH = 5    # frames: any backward jump = hard seek

    def __init__(self, cacheBytes: int = 512 * 1024 * 1024) -> None:
        self._frameCache = FrameCache(maxBytes=cacheBytes)
        self._decoderPool  = DecoderPool()
        self._threadPool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="decode")

        self._lock = threading.Lock()

        # Per pump-id tracking  
        self._lastDecoded: dict[str, int] = {}
        self._targetFrames: dict[str, int] = {}
        self._lastAnchor: dict[str, int] = {}
        self._pumpToContent:  dict[str, str] = {}  
        self._contentRefCount: dict[str, int] = {}
        self._activePumps: set[str] = set()

    #   Public API used by VideoClip.render()  

    def tryGetFrame(self, contentId: str, frame: int) -> Optional[DecodedFrame]:
        """Cache lookup — called every frame by the clip. Must be fast."""
        return self._frameCache.get((contentId, frame))

    def prefetchAround(self, clipId: str, anchorFrame: int, radius: int = 15) -> None:
        
        needsPump = False
        with self._lock:
            lastAnchor = self._lastAnchor.get(clipId, -1)

            seekedFwd = anchorFrame > lastAnchor + self.SEEK_FWD_THRESH
            seekedBwd = anchorFrame < lastAnchor - self.SEEK_BWD_THRESH

            if seekedFwd or seekedBwd:
                # Hard seek 
                self._lastDecoded[clipId]  = anchorFrame - 1
                self._targetFrames[clipId] = anchorFrame + radius

            self._lastAnchor[clipId] = anchorFrame

            # Keep runway moving
            if anchorFrame + radius > self._targetFrames.get(clipId, 0):
                self._targetFrames[clipId] = anchorFrame + radius

            if self._lastDecoded.get(clipId, -1) < self._targetFrames.get(clipId, 0):
                needsPump = True

        if needsPump:
            self._startPump(clipId)

    #   Clip registration  

    def registerClip(self, clipId: str, asset: MediaAsset, contentId: str = "") -> None:
        
        cid = contentId or asset.assetId
        if not self._decoderPool.has(clipId):
            self._decoderPool.open(clipId, asset.filepath, asset.mediaType)
            with self._lock:
                self._lastDecoded[clipId] = -1
                self._targetFrames[clipId] = 0
                self._lastAnchor[clipId] = -1
                self._pumpToContent[clipId] = cid
                self._contentRefCount[cid] = self._contentRefCount.get(cid, 0) + 1

    def unregisterClip(self, clipId: str) -> None:
        
        contentId = ""
        with self._lock:
            self._targetFrames.pop(clipId, None)
            self._lastDecoded.pop(clipId, None)
            self._lastAnchor.pop(clipId, None)
            contentId = self._pumpToContent.pop(clipId, "")
            if contentId:
                self._contentRefCount[contentId] = self._contentRefCount.get(contentId, 1) - 1
                if self._contentRefCount[contentId] <= 0:
                    del self._contentRefCount[contentId]
                    # Last reference gone  
                    self._frameCache.evictClip(contentId)

        self._decoderPool.close(clipId)

    #   Internal pump  

    def _startPump(self, clipId: str) -> None:
        with self._lock:
            if clipId in self._activePumps:
                return    # already decoding this clip
            self._activePumps.add(clipId)

        self._threadPool.submit(self._pumpWorker, clipId)

    def _pumpWorker(self, clipId: str) -> None:
        
        contentId = ""
        with self._lock:
            contentId = self._pumpToContent.get(clipId, "")
        if not contentId:
            with self._lock:
                self._activePumps.discard(clipId)
            return

        decoder = self._decoderPool.checkout(clipId)
        if decoder is None:
            with self._lock:
                self._activePumps.discard(clipId)
            return

        decoded = 0
        needsMore = False

        try:
            while decoded < self.BATCH_SIZE:
                with self._lock:
                    target  = self._targetFrames.get(clipId, 0)
                    current = self._lastDecoded.get(clipId, -1)

                if current >= target:
                    break

                nextFrame = current + 1
                success = False

                # Check cache  
                if self._frameCache.get((contentId, nextFrame)) is not None:
                    success = True
                else:
                    frame = decoder.decodeFrame(nextFrame)
                    if frame and frame.valid:
                        self._frameCache.put((contentId, nextFrame), frame)
                        success = True

                if success:
                    with self._lock:
                        self._lastDecoded[clipId] = nextFrame
                    decoded += 1
                else:
                    # EOF or decode error  
                    with self._lock:
                        self._targetFrames[clipId] = self._lastDecoded.get(clipId, 0)
                    break

        finally:
            self._decoderPool.checkin(clipId)

        with self._lock:
            self._activePumps.discard(clipId)
            needsMore = (
                self._lastDecoded.get(clipId, -1) < self._targetFrames.get(clipId, 0)
            )

        if needsMore:
            self._startPump(clipId)

    def shutdown(self) -> None:
        self._threadPool.shutdown(wait=False)

    def __repr__(self) -> str:
        return (
            f"DecodeScheduler("
            f"clips={len(self._pumpToContent)}, "
            f"cache={self._frameCache})"
        )
