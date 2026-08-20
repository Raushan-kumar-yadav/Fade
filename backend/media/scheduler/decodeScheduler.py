 
from __future__ import annotations
import threading
import queue
import gc
from typing import Optional
from backend.media.cache.frameCache import FrameCache
from backend.media.decoder.decoderPool import DecoderPool
from backend.media.decoder.decodedFrame import DecodedFrame
from backend.media.asset.mediaAsset import MediaAsset


class DecodeScheduler:
     

    BATCH_SIZE = 30    
    SEEK_FWD_THRESH = 30     
    SEEK_BWD_THRESH = 5    

    def __init__(self, cacheBytes: int = 512 * 1024 * 1024) -> None:
        self._frameCache  = FrameCache(maxBytes=cacheBytes)
        self._decoderPool = DecoderPool()
        self._lock = threading.Lock()

        # Per-clip pump state
        self._lastDecoded: dict[str, int] = {}
        self._targetFrames: dict[str, int] = {}
        self._lastAnchor: dict[str, int] = {}
        self._pumpToContent:  dict[str, str] = {}
        self._contentRefCount: dict[str, int] = {}

        # Active pump guard  
        self._activePumps: set[str] = set()

        # Preview scale factor 
        self._previewScale: float = 0.5   

        # Single background decode worker  
        self._jobQueue: queue.Queue[str] = queue.Queue()
        self._workerThread = threading.Thread(
            target=self._workerLoop,
            name="DecodeWorker",
            daemon=True,
        )
        self._workerThread.start()

    #   Public API  

    def tryGetFrame(self, contentId: str, frame: int) -> Optional[DecodedFrame]:
        """Cache lookup — called every frame by the clip. Always instant."""
        return self._frameCache.get((contentId, frame))

    def prefetchAround(self, clipId: str, anchorFrame: int, radius: int = 15) -> None:
         
        needs_pump = False

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

            behind = self._lastDecoded.get(clipId, -1) < self._targetFrames.get(clipId, 0)
             
            if behind and clipId not in self._activePumps:
                self._activePumps.add(clipId)
                needs_pump = True

        if needs_pump:
            self._jobQueue.put_nowait(clipId)

    # Clip registration  

    def registerClip(self, clipId: str, asset: MediaAsset, contentId: str = "") -> None:
        cid = contentId or asset.assetId
        if not self._decoderPool.has(clipId):
            self._decoderPool.open(clipId, asset.filepath, asset.mediaType,
                                   scale=self._previewScale)
            with self._lock:
                self._lastDecoded[clipId] = -1
                self._targetFrames[clipId]  = 0
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
            self._activePumps.discard(clipId)
            if contentId:
                self._contentRefCount[contentId] = self._contentRefCount.get(contentId, 1) - 1
                if self._contentRefCount[contentId] <= 0:
                    del self._contentRefCount[contentId]
                    self._frameCache.evictClip(contentId)

        self._decoderPool.close(clipId)

    def shutdown(self) -> None:
        """Signal the worker to stop and wait for it."""
        self._jobQueue.put_nowait(_SENTINEL)
        self._workerThread.join(timeout=3)

    # Background worker  

    def _workerLoop(self) -> None:
        
        while True:
            clipId = self._jobQueue.get()
            if clipId is _SENTINEL:
                self._jobQueue.task_done()
                break
            try:
                self._pumpWorker(clipId)
            except Exception as e:
                print(f"[DecodeScheduler] pump error for {clipId}: {e}")
                with self._lock:
                    self._activePumps.discard(clipId)
            finally:
                self._jobQueue.task_done()

    def _pumpWorker(self, clipId: str) -> None:
 
       
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
        needs_more = False

        try:
            while decoded < self.BATCH_SIZE:
                with self._lock:
                    target  = self._targetFrames.get(clipId, 0)
                    current = self._lastDecoded.get(clipId, -1)

                if current >= target:
                    break

                nextFrame = current + 1

                # Cache hit 
                if self._frameCache.get((contentId, nextFrame)) is not None:
                    with self._lock:
                        self._lastDecoded[clipId] = nextFrame
                    decoded += 1
                    continue

                # Decode the frame
                frame = decoder.decodeFrame(nextFrame)
                if frame and frame.valid:
                    self._frameCache.put((contentId, nextFrame), frame)
                    with self._lock:
                        self._lastDecoded[clipId] = nextFrame
                    decoded += 1
                else:
                    # EOF or decode error — stop pump
                    with self._lock:
                        self._targetFrames[clipId] = self._lastDecoded.get(clipId, 0)
                    break

            # Check if more work remains  
            with self._lock:
                behind = self._lastDecoded.get(clipId, -1) < self._targetFrames.get(clipId, 0)
                if behind:
                    needs_more = True
                    # Stay in activePumps for the chained job
                else:
                    self._activePumps.discard(clipId)

        finally:
            self._decoderPool.checkin(clipId)
            gc.collect()

         
        if needs_more:
            self._jobQueue.put_nowait(clipId)

    def __repr__(self) -> str:
        return (
            f"DecodeScheduler("
            f"clips={len(self._pumpToContent)}, "
            f"cache={self._frameCache})"
        )


_SENTINEL = object()
