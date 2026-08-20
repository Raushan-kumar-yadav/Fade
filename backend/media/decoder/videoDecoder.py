from __future__ import annotations
import threading
import av
from backend.media.decoder.baseDecoder import BaseDecoder
from backend.media.decoder.decodedFrame import DecodedFrame


class VideoDecoder(BaseDecoder):
    """
    PyAV-based video decoder.
    Thread-safe: all container operations are guarded by a per-instance lock
    because PyAV av.Container is NOT thread-safe.
    """

    SEEK_THRESHOLD = 5

    def __init__(self, filepath: str, fps: float = 30.0) -> None:
        super().__init__(filepath)
        self._fps = fps
        self._lock = threading.Lock()   # guards all container access
        self._container = av.open(filepath)
        self._videoStream = self._container.streams.video[0]
        self._lastDecodedFrame = -1
        self._demuxIter = None

        if self._videoStream.average_rate:
            self._fps = float(self._videoStream.average_rate)

    def decodeFrame(self, frame: int) -> DecodedFrame | None:
        with self._lock:
            needsSeek = (
                self._demuxIter is None
                or frame < self._lastDecodedFrame
                or frame > self._lastDecodedFrame + self.SEEK_THRESHOLD
            )
            if needsSeek:
                self._seek_locked(frame)
            return self._decodeUntil_locked(frame)

    def _seek_locked(self, frame: int) -> None:
        """Must be called while self._lock is held."""
        timeSeconds = frame / self._fps
        timestamp   = int(timeSeconds / self._videoStream.time_base)
        self._container.seek(timestamp, stream=self._videoStream)
        self._demuxIter = self._container.demux(self._videoStream)

    def _decodeUntil_locked(self, targetFrame: int) -> DecodedFrame | None:
        """Must be called while self._lock is held."""
        targetPts  = int((targetFrame / self._fps) / self._videoStream.time_base)
        lastAvFrame = None

        try:
            for packet in self._demuxIter:
                for avFrame in packet.decode():
                    if avFrame.pts is None:
                        continue
                    lastAvFrame = avFrame
                    if avFrame.pts >= targetPts:
                        break
                if lastAvFrame and lastAvFrame.pts >= targetPts:
                    break
        except StopIteration:
            pass
        except Exception as exc:
            print(f"[VideoDecoder] decode error frame={targetFrame}: {exc}")
            return None

        if lastAvFrame is None:
            return None

       
        try:
            import numpy as np
            reformatter = av.video.reformatter.VideoReformatter()
            bgraFrame   = reformatter.reformat(lastAvFrame, format="bgra")
            # to_ndarray strips stride → compact (h, w, 4) BGRA array
            arr = bgraFrame.to_ndarray()          # shape (h, w, 4), dtype uint8
            arr = np.ascontiguousarray(arr)       # ensure C-contiguous
            raw = arr.tobytes()                   # exactly w*h*4 bytes, no padding
            w, h = bgraFrame.width, bgraFrame.height
        except Exception as exc:
            print(f"[VideoDecoder] reformat error: {exc}")
            return None

        self._lastDecodedFrame = targetFrame

        return DecodedFrame(
            frameNumber = targetFrame,
            width       = w,
            height      = h,
            dataRGBA    = raw,   # BGRA packed, no stride — matches MakeN32Premul
            valid       = True,
        )

    def getDurationFrames(self) -> int:
        dur = self._videoStream.duration or 0
        tb  = self._videoStream.time_base
        return int(dur * float(tb) * self._fps)

    def close(self) -> None:
        with self._lock:
            self._container.close()
            self._demuxIter = None
