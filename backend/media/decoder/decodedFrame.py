from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class DecodedFrame:
    
    frameNumber: int   = 0
    width: int   = 0
    height: int   = 0
    dataRGBA: bytes = b""
    valid: bool  = False
    skiaImage: 'skia.Image | None' = None

    def sizeBytes(self) -> int:
        """Memory footprint """
        return len(self.dataRGBA)

    @property
    def channels(self) -> int:
        return 4  

    def __repr__(self) -> str:
        mb = self.sizeBytes() / (1024 * 1024)
        return f"DecodedFrame(#{self.frameNumber}, {self.width}x{self.height}, {mb:.1f}MB, valid={self.valid})"
