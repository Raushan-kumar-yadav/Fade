from __future__ import annotations
from abc import ABC, abstractmethod
import uuid
from backend.timeline.clips.baseClip import BaseClip


class BaseTrack(ABC):
 

    def __init__(self, name: str = "Track") -> None:
        self.trackId  = str(uuid.uuid4())
        self.name = name
        self.muted = False
        self.locked = False
        self.clips: list[BaseClip] = []

    #   Clip management  

    def addClip(self, clip: BaseClip) -> None:
        """Insert clip and keep the list sorted by startFrame."""
        self.clips.append(clip)
        self.clips.sort(key=lambda c: c.startFrame)

    def removeClip(self, clipId: str) -> None:
        self.clips = [c for c in self.clips if c.clipId != clipId]

    def getClip(self, clipId: str) -> BaseClip | None:
        return next((c for c in self.clips if c.clipId == clipId), None)

    def clipAt(self, frame: int) -> BaseClip | None:
        """Return the clip that covers this frame, or None."""
        return next((c for c in self.clips if c.overlaps(frame)), None)

    #   Contract  

    @abstractmethod
    def render(self, canvas, frame: int) -> None:
        
        ...

    @abstractmethod
    def toDict(self) -> dict:
        ...

    @classmethod
    @abstractmethod
    def fromDict(cls, data: dict) -> "BaseTrack":
        ...

    #   Shared serialization helpers  

    def _baseDict(self) -> dict:
         
        return {
            "trackId": self.trackId,
            "name": self.name,
            "muted": self.muted,
            "locked": self.locked,
            "clips": [c.toDict() for c in self.clips],
        }

    def _applyBaseDict(self, data: dict) -> None:
        
        self.trackId = data["trackId"]
        self.muted = data.get("muted", False)
        self.locked  = data.get("locked", False)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"{self.name!r}, "
            f"{len(self.clips)} clips, "
            f"muted={self.muted})"
        )
