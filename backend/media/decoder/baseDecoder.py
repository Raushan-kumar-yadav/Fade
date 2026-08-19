from __future__ import annotations
from abc import ABC, abstractmethod
from backend.media.decoder.decodedFrame import DecodedFrame


class BaseDecoder(ABC):
   

    def __init__(self, filepath: str) -> None:
        self.filepath = filepath

    @abstractmethod
    def decodeFrame(self, frame: int) -> DecodedFrame | None:
        """
        Decode and return the frame at the given frame number.
        Returns None on EOF or decode error.
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """Release all resources held by this decoder."""
        ...

    @abstractmethod
    def getDurationFrames(self) -> int:
        """Total number of frames in the source."""
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.filepath!r})"
