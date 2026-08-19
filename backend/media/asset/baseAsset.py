from __future__ import annotations
from abc import ABC, abstractmethod
from enum import Enum


class MediaType(Enum):
    video    = "video"
    image    = "image"
    audio    = "audio"
    subtitle = "subtitle"
    unknown  = "unknown"


class BaseAsset(ABC):
    """
    Abstract base for every media asset.
    Python port of C++ BaseAsset.hpp.

    A clip does NOT own media data — it holds an assetId string.
    The DecodeScheduler uses that assetId to look up the correct
    BaseAsset and pull decoded frames from the shared FrameCache.

    This mirrors the C++ design exactly:
      - Clips store a pointer/id to a MediaAsset
      - Multiple clips referencing the same file share one cache entry
      - No frame data is duplicated
    """

    def __init__(self, assetId: str, filepath: str, filename: str) -> None:
        self.assetId  = assetId
        self.filepath = filepath
        self.filename = filename

    @property
    @abstractmethod
    def mediaType(self) -> MediaType:
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.filename!r}, id={self.assetId!r})"
