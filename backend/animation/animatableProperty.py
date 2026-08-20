from __future__ import annotations
from backend.animation.scalarTrack import ScalarTrack
from backend.animation.keyframe import Keyframe, Interpolation, makeBezierKeyframe


class AnimatableProperty:
  

    def __init__(self, defaultValue: float = 0.0) -> None:
        self._baseValue: float = defaultValue
        self._currentValue: float = defaultValue
        self._isAnimated: bool = False
        self._track: ScalarTrack = ScalarTrack()

    #   Control  

    def setAnimated(self, animated: bool) -> None:
        self._isAnimated = animated
        if not animated:
            self._baseValue = self._currentValue
            self._track.clear()

    @property
    def isAnimated(self) -> bool:
        return self._isAnimated

    def setBaseValue(self, value: float) -> None:
        self._baseValue = value
        if not self._isAnimated:
            self._currentValue = value

    @property
    def baseValue(self) -> float:
        return self._baseValue

    #   Keyframe editing  

    def addKeyframe(self, frame: int, value: float,
                    interp: Interpolation = Interpolation.Bezier) -> None:
        self._isAnimated = True
        self._track.insertKeyframe(makeBezierKeyframe(frame, value)
                                   if interp == Interpolation.Bezier
                                   else Keyframe(frame, value, interp))

    def removeKeyframe(self, frame: int) -> bool:
        return self._track.removeKeyframe(frame)

    def hasKeyframe(self, frame: int) -> bool:
        return self._track.hasKeyframe(frame)

    def clearAnimation(self) -> None:
        self._track.clear()
        self._isAnimated = False

    @property
    def track(self) -> ScalarTrack:
        return self._track

    # Evaluation 

    def update(self, frame: int) -> None:
        if not self._isAnimated or self._track.empty():
            self._currentValue = self._baseValue
        else:
            self._currentValue = self._track.evaluateAt(frame, self._baseValue)

    # Read  

    def get(self) -> float:
        return self._currentValue

    def __float__(self) -> float:
        return self._currentValue

    def __repr__(self) -> str:
        animated = f", {len(self._track)} kf" if self._isAnimated else ""
        return f"AnimatableProperty({self._currentValue:.3f}{animated})"


class Vec2Property:
 
    def __init__(self, x: float = 0.0, y: float = 0.0) -> None:
        self.x = AnimatableProperty(x)
        self.y = AnimatableProperty(y)

    def update(self, frame: int) -> None:
        self.x.update(frame)
        self.y.update(frame)

    def get(self) -> tuple[float, float]:
        return (self.x.get(), self.y.get())

    def setBase(self, x: float, y: float) -> None:
        self.x.setBaseValue(x)
        self.y.setBaseValue(y)

    def addKeyframe(self, frame: int, x: float, y: float,
                    interp: Interpolation = Interpolation.Bezier) -> None:
        self.x.addKeyframe(frame, x, interp)
        self.y.addKeyframe(frame, y, interp)

    def __repr__(self) -> str:
        return f"Vec2Property({self.x.get():.2f}, {self.y.get():.2f})"
