 
from __future__ import annotations
import threading
import time
import queue
from typing import Optional
from backend.media.cache.frameCache import FrameCache
from backend.media.decoder.decoderPool import DecoderPool
from backend.media.decoder.decodedFrame import DecodedFrame
from backend.media.asset.mediaAsset import MediaAsset


class DecodeScheduler:
     

    BATCH_SIZE       = 24   # frames per worker wakeup — smaller = more responsive to seeks
    WORKER_COUNT     = 4
    MAX_ACTIVE_PUMPS = 2    # at most 2 clips decode simultaneously (prevents bus saturation)
    SEEK_FWD_THRESH  = 30
    SEEK_BWD_THRESH  = 5
    DECODE_SLEEP_S   = 0.002  # 2ms yield between frames — releases memory bus for GPU

    def __init__(self, cacheBytes: int = 2 * 1024 * 1024 * 1024) -> None:
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

        # Cancel flags — set True when a seek invalidates the running pump
        self._cancelFlags: dict[str, bool] = {}

        # Preview scale factor 
        self._previewScale: float = 0.5   

        # A small pool lets independent clips decode concurrently without
        # creating one Python thread per clip.
        self._jobQueue: queue.Queue[str] = queue.Queue()
        self._workerThreads = [
            threading.Thread(
                target=self._workerLoop,
                name=f"DecodeWorker-{index + 1}",
                daemon=True,
            )
            for index in range(self.WORKER_COUNT)
        ]
        for worker in self._workerThreads:
            worker.start()
            # Lower decode threads to below-normal OS priority.
            # This prevents them from starving the GPU display DMA pipeline
            # which causes Windows TDR (display driver crash/restart).
            try:
                import ctypes
                THREAD_PRIORITY_BELOW_NORMAL = -1
                handle = ctypes.windll.kernel32.OpenThread(0x0060, False, worker.ident)
                if handle:
                    ctypes.windll.kernel32.SetThreadPriority(handle, THREAD_PRIORITY_BELOW_NORMAL)
                    ctypes.windll.kernel32.CloseHandle(handle)
            except Exception:
                pass   # non-Windows or ctypes unavailable — safe to ignore

    #   Public API  

    def tryGetFrame(self, contentId: str, frame: int) -> Optional[DecodedFrame]:
        """Cache lookup — called every frame by the clip. Always instant."""
        return self._frameCache.get((contentId, frame))

    def sourceFrame(self, clipId: str, timelineFrame: int, timelineFps: float) -> int:
        sourceFps = self._decoderPool.fps(clipId, timelineFps)
        if timelineFps <= 0:
            return timelineFrame
        return max(0, round(timelineFrame * sourceFps / timelineFps))

    def prefetchAround(self, clipId: str, anchorFrame: int, radius: int = 15) -> None:
         
        needs_pump = False

        with self._lock:
            lastAnchor = self._lastAnchor.get(clipId, -1)
            seekedFwd  = anchorFrame > lastAnchor + self.SEEK_FWD_THRESH
            seekedBwd  = anchorFrame < lastAnchor - self.SEEK_BWD_THRESH

            if seekedFwd or seekedBwd:
                # Seek detected: cancel any running pump immediately
                self._cancelFlags[clipId] = True
                # Remove from activePumps so next pump slot is free immediately
                self._activePumps.discard(clipId)

                self._lastDecoded[clipId]  = anchorFrame - 1
                self._targetFrames[clipId] = anchorFrame + radius

            self._lastAnchor[clipId] = anchorFrame

            if anchorFrame + radius > self._targetFrames.get(clipId, 0):
                self._targetFrames[clipId] = anchorFrame + radius

            behind = self._lastDecoded.get(clipId, -1) < self._targetFrames.get(clipId, 0)
             
            # Limit concurrent decoders — prevents PCIe/RAM bus saturation (GPU TDR)
            if behind and clipId not in self._activePumps and len(self._activePumps) < self.MAX_ACTIVE_PUMPS:
                self._activePumps.add(clipId)
                self._cancelFlags[clipId] = False  # clear cancel for new pump
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
                self._cancelFlags[clipId] = False
                self._pumpToContent[clipId] = cid
                self._contentRefCount[cid] = self._contentRefCount.get(cid, 0) + 1

    def unregisterClip(self, clipId: str) -> None:
        contentId = ""
        with self._lock:
            self._targetFrames.pop(clipId, None)
            self._lastDecoded.pop(clipId, None)
            self._lastAnchor.pop(clipId, None)
            self._cancelFlags.pop(clipId, None)
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
        for _ in self._workerThreads:
            self._jobQueue.put_nowait(_SENTINEL)
        for worker in self._workerThreads:
            worker.join(timeout=3)

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
                # Check cancel flag — set by seek in prefetchAround()
                with self._lock:
                    if self._cancelFlags.get(clipId, False):
                        needs_more = False
                        break

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
                    # 2ms yield — releases PCIe/memory bus for GPU display pipeline
                    # This prevents Windows TDR (display driver restart)
                    time.sleep(self.DECODE_SLEEP_S)
                else:
                    # EOF or decode error — stop pump
                    with self._lock:
                        self._targetFrames[clipId] = self._lastDecoded.get(clipId, 0)
                    break

            # Check if more work remains  
            with self._lock:
                cancelled = self._cancelFlags.get(clipId, False)
                behind = self._lastDecoded.get(clipId, -1) < self._targetFrames.get(clipId, 0)
                if behind and not cancelled:
                    needs_more = True
                    # Stay in activePumps for the chained job
                else:
                    self._activePumps.discard(clipId)

        finally:
            self._decoderPool.checkin(clipId)

         
        if needs_more:
            self._jobQueue.put_nowait(clipId)

    def __repr__(self) -> str:
        return (
            f"DecodeScheduler("
            f"clips={len(self._pumpToContent)}, "
            f"cache={self._frameCache})"
        )


_SENTINEL = object()
