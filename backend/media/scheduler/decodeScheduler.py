from __future__ import annotations
import threading
import gc
from typing import Optional
from backend.media.cache.frameCache import FrameCache
from backend.media.decoder.decoderPool import DecoderPool
from backend.media.decoder.decodedFrame import DecodedFrame
from backend.media.asset.mediaAsset import MediaAsset


class DecodeScheduler:
  

    BATCH_SIZE = 5    
    SEEK_FWD_THRESH = 30   
    SEEK_BWD_THRESH = 5    

    def __init__(self, cacheBytes: int = 512 * 1024 * 1024) -> None:
        self._frameCache = FrameCache(maxBytes=cacheBytes)
        self._decoderPool  = DecoderPool()
        self._lock = threading.Lock()

        # Per pump-id tracking
        self._lastDecoded: dict[str, int] = {}
        self._targetFrames: dict[str, int] = {}
        self._lastAnchor: dict[str, int] = {}
        self._pumpToContent:  dict[str, str] = {}
        self._contentRefCount: dict[str, int] = {}
 
    def tryGetFrame(self, contentId: str, frame: int) -> Optional[DecodedFrame]:
        """Cache lookup — called every frame by the clip. Must be fast."""
        return self._frameCache.get((contentId, frame))

    def prefetchAround(self, clipId: str, anchorFrame: int, radius: int = 15) -> None:
     
        with self._lock:
            lastAnchor = self._lastAnchor.get(clipId, -1)
            seekedFwd  = anchorFrame > lastAnchor + self.SEEK_FWD_THRESH
            seekedBwd  = anchorFrame < lastAnchor - self.SEEK_BWD_THRESH

            if seekedFwd or seekedBwd:
                self._lastDecoded[clipId]  = anchorFrame - 1
                self._targetFrames[clipId] = anchorFrame + radius

            self._lastAnchor[clipId] = anchorFrame

            if anchorFrame + radius > self._targetFrames.get(clipId, 0):
                self._targetFrames[clipId] = anchorFrame + radius

            needs_pump = self._lastDecoded.get(clipId, -1) < self._targetFrames.get(clipId, 0)

        if needs_pump:
           
            self._pumpWorker(clipId)

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

 
    def _pumpWorker(self, clipId: str) -> None:
      
        with self._lock:
            contentId = self._pumpToContent.get(clipId, "")
        if not contentId:
            return

        decoder = self._decoderPool.checkout(clipId)
        if decoder is None:
            return

        decoded = 0
        try:
            while decoded < self.BATCH_SIZE:
                with self._lock:
                    target  = self._targetFrames.get(clipId, 0)
                    current = self._lastDecoded.get(clipId, -1)

                if current >= target:
                    break

                nextFrame = current + 1
                success   = False

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
                    with self._lock:
                        self._targetFrames[clipId] = self._lastDecoded.get(clipId, 0)
                    break
        finally:
            self._decoderPool.checkin(clipId)
            gc.collect()

    def shutdown(self) -> None:
        pass   

    def __repr__(self) -> str:
        return (
            f"DecodeScheduler("
            f"clips={len(self._pumpToContent)}, "
            f"cache={self._frameCache})"
        )
