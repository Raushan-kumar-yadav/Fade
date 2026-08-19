from __future__ import annotations
from collections import OrderedDict
from threading import Lock
from typing import Optional
from backend.media.decoder.decodedFrame import DecodedFrame

# Cache key: (assetId/contentId, frameNumber)
FrameKey = tuple[str, int]


class FrameCache:
     

    def __init__(self, maxBytes: int = 512 * 1024 * 1024) -> None:
        self._maxBytes  = maxBytes
        self._usedBytes = 0
        self._map: OrderedDict[FrameKey, DecodedFrame] = OrderedDict()
        self._lock = Lock()

    def get(self, key: FrameKey) -> Optional[DecodedFrame]:
        with self._lock:
            if key not in self._map:
                return None
            self._map.move_to_end(key)   
            return self._map[key]

    def put(self, key: FrameKey, frame: DecodedFrame) -> None:
        if not frame or not frame.valid:
            return
        with self._lock:
            if key in self._map:
                # Update in-place  
                self._usedBytes -= self._map[key].sizeBytes()
                self._map.move_to_end(key)
                self._map[key] = frame
                self._usedBytes += frame.sizeBytes()
            else:
                self._map[key] = frame
                self._usedBytes += frame.sizeBytes()
                self._map.move_to_end(key)

            self._evictUntilUnderBudget()

    def evictClip(self, contentId: str) -> None:
        
        with self._lock:
            keysToRemove = [k for k in self._map if k[0] == contentId]
            for k in keysToRemove:
                self._usedBytes -= self._map[k].sizeBytes()
                del self._map[k]

    def clear(self) -> None:
        with self._lock:
            self._map.clear()
            self._usedBytes = 0

    def _evictUntilUnderBudget(self) -> None:
        # Called while _lock is already held
        while self._usedBytes > self._maxBytes and self._map:
            _, lruFrame = self._map.popitem(last=False)  # oldest first
            self._usedBytes -= lruFrame.sizeBytes()

    @property
    def usedMB(self) -> float:
        return self._usedBytes / (1024 * 1024)

    def __repr__(self) -> str:
        return f"FrameCache({self.usedMB:.1f}/{self._maxBytes/(1024*1024):.0f} MB, {len(self._map)} frames)"
