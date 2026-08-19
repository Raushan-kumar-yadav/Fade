from __future__ import annotations
import av
from backend.media.decoder.baseDecoder import BaseDecoder
from backend.media.decoder.decodedFrame import DecodedFrame


class VideoDecoder(BaseDecoder):
    

    SEEK_THRESHOLD = 5   

    def __init__(self, filepath: str, fps: float = 30.0) -> None:
        super().__init__(filepath)
        self._fps = fps
        self._container = av.open(filepath)
        self._videoStream = self._container.streams.video[0]
        self._lastDecodedFrame = -1
        self._demuxIter = None   # current active demux iterator

        # Read stream FPS if available
        if self._videoStream.average_rate:
            self._fps = float(self._videoStream.average_rate)

    def decodeFrame(self, frame: int) -> DecodedFrame | None:
        needsSeek = (
            self._demuxIter is None
            or frame < self._lastDecodedFrame
            or frame > self._lastDecodedFrame + self.SEEK_THRESHOLD
        )

        if needsSeek:
            self._seek(frame)

        # Decode forward until we reach the target frame
        return self._decodeUntil(frame)

    def _seek(self, frame: int) -> None:
        timeSeconds = frame / self._fps
        timestamp = int(timeSeconds / self._videoStream.time_base)
        self._container.seek(timestamp, stream=self._videoStream)
        self._demuxIter = self._container.demux(self._videoStream)

    def _decodeUntil(self, targetFrame: int) -> DecodedFrame | None:
        targetPts = int((targetFrame / self._fps) / self._videoStream.time_base)
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

        if lastAvFrame is None:
            return None

        # Convert to RGBA via PyAV reformatter  
        reformatter = av.video.reformatter.VideoReformatter()
        rgbaFrame = reformatter.reformat(lastAvFrame, format="rgba")
        raw = bytes(rgbaFrame.planes[0])

        self._lastDecodedFrame = targetFrame

        return DecodedFrame(
            frameNumber = targetFrame,
            width = rgbaFrame.width,
            height = rgbaFrame.height,
            dataRGBA = raw,
            valid = True,
        )

    def getDurationFrames(self) -> int:
        dur = self._videoStream.duration or 0
        tb  = self._videoStream.time_base
        return int(dur * float(tb) * self._fps)

    def close(self) -> None:
        self._container.close()
        self._demuxIter = None
