from __future__ import annotations
from abc import ABC, abstractmethod
from backend.animation.transform import Transform
from backend.animation import anim_debug as _dbg


class BaseClip(ABC):
     

    def __init__(self, clipId: str, startFrame: int, duration: int) -> None:
        self.clipId = clipId
        self.startFrame = startFrame
        self.duration = duration
        self.effects: list = []   # list[BaseEffect]
        self.isSelected  = False
        self.isLocked = False
        self.transform = Transform()
        self.blendMode: int = 0   

        # Mask    
         
        from backend.timeline.clips.textClip import MaskLayer   
        self.masks: list = []     

    # geometry  
    @property
    def endFrame(self) -> int:
        return self.startFrame + self.duration

    def overlaps(self, frame: int) -> bool:
        return self.startFrame <= frame < self.endFrame

    def evaluateAll(self, frame: int, _timeline=None) -> None:
        """Update all animatable properties for the given timeline frame."""
        lf = self.localFrame(frame)

        if _dbg.ANIM_DEBUG and frame % _dbg._LOG_EVERY_N == 0:
            print(f"[ANIM] evaluateAll  clip={self.clipId[:8]}({type(self).__name__})  "
                  f"timeline_frame={frame}  local_frame={lf}", flush=True)

         
        if _timeline is None:
            try:
                from backend.state import engine as _eng
                _timeline = _eng.activeTimeline if _eng else None
            except Exception:
                pass

         
        if hasattr(self, '_anim_params'):
            for key, ap in self._anim_params.items():
                val = ap.evaluate(frame) if ap.is_animated() else ap._base[0]
                self.applyParam(key, val)

         
        self.transform.evaluateAll(lf, _clip=self, _timeline=_timeline)

        for effect in self.effects:
            if hasattr(effect, 'evaluateAll'):
                effect.evaluateAll(lf)


    def applyParam(self, key: str, val: float) -> None:
        """Write an animated value into the correct transform property.
        Sets both _baseValue (so transform.evaluateAll reads it) and
        _currentValue (so .get() immediately returns the right value)."""
        t = self.transform
        if key == "opacity":
            t.opacity.setBaseValue(val)
            t.opacity._currentValue = val
        elif key == "pos_x":
            t.position.setBase(val, t.position.y.baseValue)
            t.position.x._currentValue = val
        elif key == "pos_y":
            t.position.setBase(t.position.x.baseValue, val)
            t.position.y._currentValue = val
        elif key == "scale_x":
            t.scale.setBase(val, t.scale.y.baseValue)
            t.scale.x._currentValue = val
        elif key == "scale_y":
            t.scale.setBase(t.scale.x.baseValue, val)
            t.scale.y._currentValue = val
        elif key == "rotation":
            t.rotation.setBaseValue(val)
            t.rotation._currentValue = val
        elif key == "anchor_x":
            t.anchor.setBase(val, t.anchor.y.baseValue)
            t.anchor.x._currentValue = val
        elif key == "anchor_y":
            t.anchor.setBase(t.anchor.x.baseValue, val)
            t.anchor.y._currentValue = val
        elif key == "blend_mode":
            bm = getattr(self, "blendMode", None)
            if hasattr(bm, "setBaseValue"):
                bm.setBaseValue(float(round(val)))
                bm._currentValue = float(round(val))
            else:
                self.blendMode = int(round(val))


    #   Mask helpers  

    def addMask(self, mask) -> None:
        self.masks.append(mask)

    def removeMask(self, maskId: str) -> bool:
        before = len(self.masks)
        self.masks = [m for m in self.masks if m.maskId != maskId]
        return len(self.masks) < before

    def getMask(self, maskId: str):
        return next((m for m in self.masks if m.maskId == maskId), None)

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
