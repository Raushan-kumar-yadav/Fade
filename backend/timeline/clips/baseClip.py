from __future__ import annotations
from abc import ABC, abstractmethod
from backend.animation.transform import Transform


class BaseClip(ABC):
    """
    Abstract base for every clip type (Video, Audio, Text, Solid, Shape …)
 
    """

    def __init__(self, clipId: str, startFrame: int, duration: int) -> None:
        self.clipId = clipId
        self.startFrame = startFrame
        self.duration = duration
        self.effects: list = []   # list[BaseEffect]
        self.isSelected  = False
        self.isLocked = False

        
        self.transform = Transform()

    # Derived geometry  
    @property
    def endFrame(self) -> int:
        return self.startFrame + self.duration

    def overlaps(self, frame: int) -> bool:
        return self.startFrame <= frame < self.endFrame

    def evaluateAll(self, frame: int) -> None:
        """Update all animatable properties for the given timeline frame."""
        lf = self.localFrame(frame)
        self.transform.evaluateAll(lf)
        
        if hasattr(self, '_anim_params'):
            for key, ap in self._anim_params.items():
                if ap.is_animated():
                    val = ap.evaluate(frame)
                    self.applyParam(key, val)
                else:
                    self.applyParam(key, ap._base[0])

        for effect in self.effects:
            if hasattr(effect, 'evaluateAll'):
                effect.evaluateAll(lf)

    def applyParam(self, key: str, val: float) -> None:
        """Apply a computed animation param to the clip's actual properties."""
        if key == "opacity":   self.transform.opacity.setBaseValue(val)
        elif key == "pos_x":   self.transform.position.setBase(val, self.transform.position.y.baseValue)
        elif key == "pos_y":   self.transform.position.setBase(self.transform.position.x.baseValue, val)
        elif key == "scale_x": self.transform.scale.setBase(val, self.transform.scale.y.baseValue)
        elif key == "scale_y": self.transform.scale.setBase(self.transform.scale.x.baseValue, val)
        elif key == "rotation":self.transform.rotation.setBaseValue(val)
        elif key == "anchor_x":self.transform.anchor.setBase(val, self.transform.anchor.y.baseValue)
        elif key == "anchor_y":self.transform.anchor.setBase(self.transform.anchor.x.baseValue, val)

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
