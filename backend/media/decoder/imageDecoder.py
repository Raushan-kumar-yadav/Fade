from __future__ import annotations
from backend.media.decoder.baseDecoder import BaseDecoder
from backend.media.decoder.decodedFrame import DecodedFrame


class ImageDecoder(BaseDecoder):
    """
    PIL-based image decoder (single-frame assets like PNG/JPEG).
    Outputs BGRA bytes to match skia.ImageInfo.MakeN32Premul (little-endian).
    """

    def __init__(self, filepath: str) -> None:
        super().__init__(filepath)
        self._cached: DecodedFrame | None = None

    def decodeFrame(self, frame: int) -> DecodedFrame | None:
        if self._cached is not None:
            return self._cached

        try:
            from PIL import Image
            import numpy as np

            img  = Image.open(self.filepath).convert("RGBA")
            arr  = np.array(img, dtype=np.uint8)

            # Swap R↔B channels: RGBA → BGRA (matches skia MakeN32Premul on Windows)
            arr[:, :, [0, 2]] = arr[:, :, [2, 0]]
            raw = arr.tobytes()

            self._cached = DecodedFrame(
                frameNumber = 0,
                width       = img.width,
                height      = img.height,
                dataRGBA    = raw,   # actually BGRA — matches MakeN32Premul
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
