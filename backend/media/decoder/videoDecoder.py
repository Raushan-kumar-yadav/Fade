 
from __future__ import annotations
import os
from typing import Optional
from backend.media.decoder.baseDecoder import BaseDecoder
from backend.media.decoder.decodedFrame import DecodedFrame
from backend.media.decoder.ffmpegDecoder import FFmpegVideoDecoder, DecodedFrameFF

# Set FADE_DECODER=ffmpeg to force subprocess, FADE_DECODER=pyav to force PyAV.
# Default: auto (PyAV if installed, else ffmpeg subprocess)
_DECODER_MODE = os.environ.get("FADE_DECODER", "auto").lower()


def _make_inner(filepath: str, fps: float, scale_factor: float):
    """Instantiate the best available decoder backend."""
    use_pyav = False
    if _DECODER_MODE == "pyav":
        use_pyav = True
    elif _DECODER_MODE == "auto":
        try:
            import av  # noqa: F401
            use_pyav = True
        except ImportError:
            use_pyav = False

    if use_pyav:
        try:
            from backend.media.decoder.pyavDecoder import PyAVDecoder
            return PyAVDecoder(filepath, fps=fps, scale_factor=scale_factor)
        except Exception as e:
            print(f"[VideoDecoder] PyAV failed ({e}), falling back to FFmpeg subprocess")

    return FFmpegVideoDecoder(filepath, fps, scale_factor=scale_factor)


class VideoDecoder(BaseDecoder):
    """
    Adapter that wraps either PyAVDecoder (in-process, fast) or
    FFmpegVideoDecoder (subprocess, fallback).

    Selection order:
      1. FADE_DECODER=pyav   → always use PyAV
      2. FADE_DECODER=ffmpeg → always use subprocess
      3. FADE_DECODER=auto   → PyAV if installed, else subprocess (default)
    """

    def __init__(self, filepath: str, fps: float = 0.0, scale_factor: float = 0.5) -> None:
        super().__init__(filepath)
        self._inner = _make_inner(filepath, fps, scale_factor)
        self._fps   = self._inner.fps

    def decodeFrame(self, frame: int) -> Optional[DecodedFrame]:
        ff: Optional[DecodedFrameFF] = self._inner.decodeFrame(frame)
        if ff is None or not ff.valid:
            return None

        import skia
        info  = skia.ImageInfo.MakeN32Premul(ff.width, ff.height)
        skdata = skia.Data.MakeWithoutCopy(ff.dataRGBA)
        image  = skia.Image.MakeRasterData(info, skdata, ff.width * 4)

        return DecodedFrame(
            frameNumber = ff.frameNumber,
            width       = ff.width,
            height      = ff.height,
            dataRGBA    = ff.dataRGBA,
            valid       = True,
            skiaImage   = image,
        )

    def getDurationFrames(self) -> int:
        return self._inner.getDurationFrames()

    @property
    def fps(self) -> float:
        return self._fps

    def flushSubprocess(self) -> None:
        if hasattr(self._inner, "stopSubprocess"):
            self._inner.stopSubprocess()

    def close(self) -> None:
        self._inner.close()
