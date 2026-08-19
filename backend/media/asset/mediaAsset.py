from __future__ import annotations
import os
import uuid
from backend.media.asset.baseAsset import BaseAsset, MediaType

# File extension  
_EXT_MAP: dict[str, MediaType] = {
    ".mp4": MediaType.video, ".mov": MediaType.video, ".avi": MediaType.video,
    ".mkv": MediaType.video, ".webm": MediaType.video, ".mxf": MediaType.video,
    ".jpg": MediaType.image, ".jpeg": MediaType.image, ".png": MediaType.image,
    ".tiff": MediaType.image, ".tif": MediaType.image, ".bmp": MediaType.image,
    ".exr": MediaType.image, ".webp": MediaType.image,
    ".mp3": MediaType.audio, ".wav": MediaType.audio, ".aac": MediaType.audio,
    ".flac": MediaType.audio, ".ogg": MediaType.audio, ".m4a": MediaType.audio,
}


class MediaAsset(BaseAsset):
    

    def __init__(
        self,
        filepath: str,
        assetId:  str = "",
    ) -> None:
        filename = os.path.basename(filepath)
        super().__init__(assetId or str(uuid.uuid4()), filepath, filename)
        self._mediaType = _EXT_MAP.get(
            os.path.splitext(filename)[1].lower(), MediaType.unknown
        )
        # Populated lazily  
        self.durationFrames: int   = 0
        self.fps: float = 0.0
        self.width: int   = 0
        self.height: int   = 0

    @property
    def mediaType(self) -> MediaType:
        return self._mediaType

    def toDict(self) -> dict:
        return {
            "assetId":  self.assetId,
            "filepath": self.filepath,
            "filename": self.filename,
            "type": self._mediaType.value,
        }

    @classmethod
    def fromDict(cls, data: dict) -> "MediaAsset":
        a = cls(filepath=data["filepath"], assetId=data["assetId"])
        return a
