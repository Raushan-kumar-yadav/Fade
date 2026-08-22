 

from __future__ import annotations
import threading
from typing import Optional

try:
    import av
    AV_AVAILABLE = True
except ImportError:
    AV_AVAILABLE = False

from backend.media.decoder.ffmpegDecoder import DecodedFrameFF, _probe


class PyAVDecoder:
    """In-process libav decoder. No subprocess pipe."""

    SEEK_FWD_THRESH: int = 60   

    def __init__(self, filepath: str, fps: float = 0.0, scale_factor: float = 0.5) -> None:
        if not AV_AVAILABLE:
            raise RuntimeError("PyAV not installed. Run: pip install av")

        self._filepath = filepath
        self._scale_factor = max(0.125, min(1.0, scale_factor))
        self._lock = threading.Lock()

        info = _probe(filepath)
        self._fps  = info["fps"] or fps or 30.0
        self._width_src  = info["width"]
        self._height_src = info["height"]
        self._total_frames = info["nb_frames"] or int(round(info["duration"] * self._fps))

        self._width  = max(2, round(self._width_src  * self._scale_factor) // 2 * 2)
        self._height = max(2, round(self._height_src * self._scale_factor) // 2 * 2)

        self._container = av.open(filepath)
        self._stream = self._container.streams.video[0]
        self._stream.thread_type = "AUTO"
        self._stream.codec_context.thread_count = 0   # use all cores

        self._last_frame: int = -1

        pct = int(self._scale_factor * 100)
        print(
            f"[PyAVDecoder] {filepath}: "
            f"{self._width_src}x{self._height_src} @ {self._fps:.3f}fps "
            f"({self._total_frames} frames) [preview {pct}%: {self._width}x{self._height}]"
        )

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    def getDurationFrames(self) -> int:
        return self._total_frames

    def decodeFrame(self, frame_number: int) -> Optional[DecodedFrameFF]:
        with self._lock:
            return self._decodeFrame(frame_number)

    def close(self) -> None:
        with self._lock:
            try:
                self._container.close()
            except Exception:
                pass

    def __del__(self) -> None:
        self.close()

    def _decodeFrame(self, frame_number: int) -> Optional[DecodedFrameFF]:
        need_seek = (
            frame_number < self._last_frame
            or frame_number > self._last_frame + self.SEEK_FWD_THRESH
        )

        if need_seek:
            tb = self._stream.time_base
            if tb and float(tb) > 0:
                ts = int(frame_number / (self._fps * float(tb)))
            else:
                ts = int(frame_number / self._fps * 1_000_000)
            try:
                self._container.seek(ts, stream=self._stream, backward=True)
            except Exception as e:
                print(f"[PyAVDecoder] seek error frame={frame_number}: {e}")
                return None
            self._last_frame = frame_number - 1

        try:
            for packet in self._container.demux(self._stream):
                for av_frame in packet.decode():
                    self._last_frame += 1
                    if self._last_frame < frame_number:
                        continue
                    raw = self._to_bgra(av_frame)
                    if raw is None:
                        return None
                    return DecodedFrameFF(
                        frameNumber = frame_number,
                        width = self._width,
                        height = self._height,
                        dataRGBA = raw,
                        valid = True,
                    )
        except Exception as e:
            print(f"[PyAVDecoder] error frame={frame_number}: {e}")
        return None

    def _to_bgra(self, frame: "av.VideoFrame") -> Optional[bytes]:
        try:
            if self._scale_factor < 1.0:
                out = frame.reformat(width=self._width, height=self._height, format="bgra")
            else:
                out = frame.reformat(format="bgra")
             
            import time
            time.sleep(0)
            return bytes(out.to_ndarray().tobytes())
        except Exception as e:
            print(f"[PyAVDecoder] conversion error: {e}")
            return None


