from __future__ import annotations
from abc import ABC, abstractmethod


class BaseClip(ABC):
    """
    Abstract base for every clip type (Video, Audio, Text, Solid, Shape …)
 
    """

    def __init__(self, clipId: str, startFrame: int, duration: int) -> None:
        self.clipId = clipId
        self.startFrame  = startFrame
        self.duration = duration
        self.effects: list = []   
        self.isSelected  = False
        self.isLocked = False

    # Derived geometry  
    @property
    def endFrame(self) -> int:
        return self.startFrame + self.duration

    def overlaps(self, frame: int) -> bool:
        return self.startFrame <= frame < self.endFrame

    def localFrame(self, frame: int) -> int:
        """Convert timeline frame to clip-local frame."""
        return frame - self.startFrame

    @abstractmethod
    def render(self, canvas, frame: int) -> None:
        """Render this clip onto the Skia canvas at the given timeline frame."""
        ...

    @abstractmethod
    def getThumbnail(self, frame: int, width: int = 160, height: int = 90) -> bytes:
        """Return JPEG bytes for timeline thumbnail strip."""
        ...

    @abstractmethod
    def toDict(self) -> dict:
        """Serialize to JSON-safe dict for project file saving."""
        ...

    @classmethod
    @abstractmethod
    def fromDict(cls, data: dict) -> "BaseClip":
        """Deserialize from project file dict."""
        ...

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"id={self.clipId!r}, "
            f"start={self.startFrame}, "
            f"dur={self.duration})"
        )
