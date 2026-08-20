from __future__ import annotations
from abc import ABC, abstractmethod
from enum import Enum


class MediaType(Enum):
    video = "video"
    image = "image"
    audio = "audio"
    subtitle = "subtitle"
    unknown  = "unknown"


class BaseAsset(ABC):
 

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
