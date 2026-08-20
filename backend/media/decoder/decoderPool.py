from __future__ import annotations
import threading
from backend.media.decoder.baseDecoder import BaseDecoder
from backend.media.decoder.videoDecoder import VideoDecoder
from backend.media.asset.baseAsset import MediaType


class _Entry:
    """One entry in the pool """
    def __init__(self, decoder: BaseDecoder, filepath: str, mediaType) -> None:
        self.decoder   = decoder
        self.filepath  = filepath
        self.mediaType = mediaType
        self.mutex     = threading.Lock()
        self.inUse     = False


class DecoderPool:
     

    def __init__(self) -> None:
        self._pool: dict[str, _Entry] = {}
        self._poolLock  = threading.Lock()

    def open(self, clipId: str, filepath: str, mediaType: MediaType,
              scale: float = 0.5) -> None:
        with self._poolLock:
            if clipId in self._pool:
                return   # already open

            if mediaType == MediaType.video:
                decoder = VideoDecoder(filepath, scale_factor=scale)
            elif mediaType == MediaType.image:
                from backend.media.decoder.imageDecoder import ImageDecoder
                decoder = ImageDecoder(filepath)
            else:
                return   # audio/subtitle

            self._pool[clipId] = _Entry(decoder, filepath, mediaType)

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

    def reopen(self, clipId: str, scale: float = 0.5) -> None:
        """Close and reopen a decoder at a new scale. Used by setPreviewScale()."""
        entry = None
        with self._poolLock:
            entry = self._pool.get(clipId)
        if entry is None:
            return
        filepath  = entry.filepath
        mediaType = entry.mediaType
        self.close(clipId)
        self.open(clipId, filepath, mediaType, scale)

    def has(self, clipId: str) -> bool:
        with self._poolLock:
            return clipId in self._pool

    def fps(self, clipId: str, default: float = 30.0) -> float:
        with self._poolLock:
            entry = self._pool.get(clipId)
        if entry is None:
            return default
        return float(getattr(entry.decoder, "fps", default))

    def __repr__(self) -> str:
        return f"DecoderPool({len(self._pool)} decoders)"
