from __future__ import annotations
import threading
from backend.media.decoder.baseDecoder import BaseDecoder
from backend.media.decoder.videoDecoder import VideoDecoder
from backend.media.asset.baseAsset import MediaType


class _Entry:
    """One entry in the pool """
    def __init__(self, decoder: BaseDecoder) -> None:
        self.decoder = decoder
        self.mutex = threading.Lock()
        self.inUse = False


class DecoderPool:
     

    def __init__(self) -> None:
        self._pool: dict[str, _Entry] = {}
        self._poolLock  = threading.Lock()

    def open(self, clipId: str, filepath: str, mediaType: MediaType) -> None:
        with self._poolLock:
            if clipId in self._pool:
                return   # already open

            if mediaType == MediaType.video:
                decoder = VideoDecoder(filepath)
            elif mediaType == MediaType.image:
                from backend.media.decoder.imageDecoder import ImageDecoder
                decoder = ImageDecoder(filepath)
            else:
                return   # audio/subtitle  

            self._pool[clipId] = _Entry(decoder)

    def close(self, clipId: str) -> None:
        entry = None
        with self._poolLock:
            entry = self._pool.pop(clipId, None)

        if entry:
             
            with entry.mutex:
                entry.decoder.close()

    def checkout(self, clipId: str) -> BaseDecoder | None:
        
        with self._poolLock:
            entry = self._pool.get(clipId)
        if entry is None:
            return None
        entry.mutex.acquire()
        entry.inUse = True
        return entry.decoder

    def checkin(self, clipId: str) -> None:
         
        with self._poolLock:
            entry = self._pool.get(clipId)
        if entry:
            entry.inUse = False
            entry.mutex.release()

    def has(self, clipId: str) -> bool:
        with self._poolLock:
            return clipId in self._pool

    def __repr__(self) -> str:
        return f"DecoderPool({len(self._pool)} decoders)"
