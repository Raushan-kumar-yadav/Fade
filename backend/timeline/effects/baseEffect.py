from __future__ import annotations
from abc import ABC, abstractmethod
import uuid


class BaseEffect(ABC):
    

    def __init__(self, name: str = "Effect") -> None:
        self.effectId = str(uuid.uuid4())
        self.name     = name
        self.enabled  = True

    #   Contract  

    @abstractmethod
    def apply(self, canvas, frame: int) -> None:
        """Apply this effect onto the Skia canvas for the given frame."""
        ...

    @abstractmethod
    def toDict(self) -> dict:
        ...

    @classmethod
    @abstractmethod
    def fromDict(cls, data: dict) -> "BaseEffect":
        ...

    # Shared helpers  

    def _baseDict(self) -> dict:
        return {
            "effectId": self.effectId,
            "name": self.name,
            "enabled":  self.enabled,
        }

    def _applyBaseDict(self, data: dict) -> None:
        self.effectId = data["effectId"]
        self.enabled  = data.get("enabled", True)

    def __repr__(self) -> str:
        status = "on" if self.enabled else "off"
        return f"{self.__class__.__name__}({self.name!r}, {status})"
