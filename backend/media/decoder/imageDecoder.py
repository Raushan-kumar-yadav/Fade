from __future__ import annotations
from backend.media.decoder.baseDecoder import BaseDecoder
from backend.media.decoder.decodedFrame import DecodedFrame


class ImageDecoder(BaseDecoder):
    """
    Single-image decoder (JPEG, PNG, EXR, TIFF …).
    Uses Pillow for loading; converts to raw RGBA bytes.

    Since images don't have multiple frames, every call to decodeFrame()
    returns the same decoded data (cached in _cached after first decode).
    """

    def __init__(self, filepath: str) -> None:
        super().__init__(filepath)
        self._cached: DecodedFrame | None = None

    def decodeFrame(self, frame: int) -> DecodedFrame | None:
        if self._cached is not None:
            return self._cached

        try:
            from PIL import Image
            img  = Image.open(self.filepath).convert("RGBA")
            raw  = img.tobytes()   # RGBA8888 bytes
            self._cached = DecodedFrame(
                frameNumber = 0,
                width       = img.width,
                height      = img.height,
                dataRGBA    = raw,
                valid       = True,
            )
            return self._cached
        except Exception as e:
            print(f"[ImageDecoder] Failed to load {self.filepath}: {e}")
            return None

    def getDurationFrames(self) -> int:
        return 1   # images are 1 frame

    def close(self) -> None:
        self._cached = None
