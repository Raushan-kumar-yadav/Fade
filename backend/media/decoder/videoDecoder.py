 
from __future__ import annotations
from typing import Optional
from backend.media.decoder.baseDecoder import BaseDecoder
from backend.media.decoder.decodedFrame import DecodedFrame
from backend.media.decoder.ffmpegDecoder import FFmpegVideoDecoder, DecodedFrameFF


class VideoDecoder(BaseDecoder):
    """Wraps FFmpegVideoDecoder (subprocess) and adapts its output to DecodedFrame."""

    def __init__(self, filepath: str, fps: float = 30.0) -> None:
        super().__init__(filepath)
        self._inner = FFmpegVideoDecoder(filepath, fps)
        self._fps   = self._inner.fps

    def decodeFrame(self, frame: int) -> Optional[DecodedFrame]:
        ff: Optional[DecodedFrameFF] = self._inner.decodeFrame(frame)
        if ff is None or not ff.valid:
            return None

        # subprocess outputs BGRA  
        return DecodedFrame(
            frameNumber = ff.frameNumber,
            width = ff.width,
            height = ff.height,
            dataRGBA = ff.dataRGBA,   # BGRA, no swap needed
            valid = True,
        )

    def getDurationFrames(self) -> int:
        return self._inner.getDurationFrames()

    def close(self) -> None:
        self._inner.close()
