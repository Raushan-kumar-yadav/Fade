from __future__ import annotations
from backend.animation.scalarTrack import ScalarTrack
from backend.animation.keyframe import Keyframe, Interpolation, makeBezierKeyframe
from backend.animation import anim_debug as _dbg


class AnimatableProperty:
    """A float property that can hold keyframes for animation and evaluate simple expressions."""

    def __init__(self, defaultValue: float = 0.0) -> None:
        self._baseValue: float = defaultValue
        self._currentValue: float = defaultValue
        self._isAnimated: bool = False
        self._track: ScalarTrack = ScalarTrack()
        self.expression: str | None = None

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
        if not self._isAnimated and not self.expression:
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

    #   Evaluation
    
    def _evaluate_expression(self, frame: int, context: dict, _prop: str) -> float | None:
        if not self.expression or not context:
            return None
        expr = self.expression.strip()
        if expr.startswith("tracking:"):
            clip_id = expr.split(":", 1)[1]
            timeline = context.get("timeline")
            clip = timeline.findClip(clip_id)[0] if timeline and clip_id != "self" else context.get("clip")
            if not clip or not hasattr(clip, "trackingData") or not clip.trackingData:
                return None
            tdata = clip.trackingData
            # Tracking data typically provides absolute frame numbers (not local)
            # wait, the tracker receives absolute start/end frame. Let's use the timeline frame.
            abs_frame = context.get("timelineFrame", frame)
            frames = tdata.get("frames", {})
            f_str = str(abs_frame)
            if f_str in frames:
                val = frames[f_str]
                if _prop.endswith("_x"): return val.get("x", self._baseValue)
                elif _prop.endswith("_y"): return val.get("y", self._baseValue)
                elif _prop == "rotation": return val.get("angle", self._baseValue)
                elif _prop.endswith("scale_x"): return val.get("scale_x", self._baseValue)
                elif _prop.endswith("scale_y"): return val.get("scale_y", self._baseValue)
        elif expr.startswith("link:"):
            parts = expr.split(":")
            if len(parts) >= 3:
                clip_id = parts[1]
                target_prop = parts[2]
                timeline = context.get("timeline")
                if not timeline: return None
                clip = timeline.findClip(clip_id)[0]
                if not clip: return None
                prop_parts = target_prop.split(".")
                obj = clip.transform
                for p in prop_parts:
                    if hasattr(obj, p):
                        obj = getattr(obj, p)
                    else:
                        return None
                if hasattr(obj, "evaluate"):
                    return obj.evaluate(frame, context=context)
                if hasattr(obj, "get"):
                    val = obj.get()
                    if isinstance(val, (int, float)): return float(val)
        return None

    def update(self, frame: int, _prop: str = "?", context: dict = None) -> None:
        if self.expression and context:
            val = self._evaluate_expression(frame, context, _prop)
            if val is not None:
                self._currentValue = val
                return

        if not self._isAnimated or self._track.empty():
            self._currentValue = self._baseValue
        else:
            self._currentValue = self._track.evaluateAt(frame, self._baseValue)

    def evaluate(self, frame: int, _prop: str = "?", context: dict = None) -> float:
        if self.expression and context:
            val = self._evaluate_expression(frame, context, _prop)
            if val is not None:
                return val

        if not self._isAnimated or self._track.empty():
            return self._baseValue
        return self._track.evaluateAt(frame, self._baseValue)

    def is_animated(self) -> bool:
        return (self._isAnimated and not self._track.empty()) or bool(self.expression)

    #   Read

    def get(self) -> float:
        return self._currentValue

    def __float__(self) -> float:
        return self._currentValue

    def __repr__(self) -> str:
        animated = f", {len(self._track)} kf" if self._isAnimated else ""
        expr_str = f", expr='{self.expression}'" if self.expression else ""
        return f"AnimatableProperty({self._currentValue:.3f}{animated}{expr_str})"

    #   Serialization  

    def toDict(self) -> dict:
        d: dict = {"base": self._baseValue, "animated": self._isAnimated}
        if self.expression:
            d["expression"] = self.expression
        if self._isAnimated and not self._track.empty():
            d["keyframes"] = [
                {
                    "frame": kf.frame,
                    "value": kf.value,
                    "interp": int(kf.interp),
                    "hiF": kf.handleInFrame,
                    "hiV": kf.handleInValue,
                    "hoF": kf.handleOutFrame,
                    "hoV": kf.handleOutValue,
                    "manual": kf.manualHandles,
                }
                for kf in self._track.keyframes()
            ]
        return d

    @classmethod
    def fromDict(cls, data: dict, defaultValue: float = 0.0) -> "AnimatableProperty":
        ap = cls(defaultValue)
        if isinstance(data, (int, float)):
            # Legacy 
            ap._baseValue = float(data)
            ap._currentValue = ap._baseValue
            return ap
        ap._baseValue = data.get("base", defaultValue)
        ap._currentValue = ap._baseValue
        ap._isAnimated = data.get("animated", False)
        ap.expression = data.get("expression")
        for kd in data.get("keyframes", []):
            kf = Keyframe(
                frame = kd["frame"],
                value = kd["value"],
                interp = Interpolation(kd.get("interp", 2)),
                handleInFrame  = kd.get("hiF", -5.0),
                handleInValue  = kd.get("hiV", 0.0),
                handleOutFrame = kd.get("hoF", 5.0),
                handleOutValue = kd.get("hoV", 0.0),
                manualHandles  = kd.get("manual", False),
            )
             
            ap._track._insertDirect(kf)
        return ap


class Vec2Property:
    """A 2D animatable property (x, y)."""

    def __init__(self, x: float = 0.0, y: float = 0.0) -> None:
        self.x = AnimatableProperty(x)
        self.y = AnimatableProperty(y)

    def update(self, frame: int, _prefix: str = "?", context: dict = None) -> None:
        self.x.update(frame, _prop=f"{_prefix}_x", context=context)
        self.y.update(frame, _prop=f"{_prefix}_y", context=context)

    def get(self) -> tuple[float, float]:
        return (self.x.get(), self.y.get())
        
    def evaluate(self, frame: int, _prefix: str = "?", context: dict = None) -> tuple[float, float]:
        return (self.x.evaluate(frame, f"{_prefix}_x", context), self.y.evaluate(frame, f"{_prefix}_y", context))

    @property
    def expression(self):
        return self.x.expression
        
    @expression.setter
    def expression(self, expr):
        self.x.expression = expr
        self.y.expression = expr

    def setBase(self, x: float, y: float) -> None:
        self.x.setBaseValue(x)
        self.y.setBaseValue(y)

    def addKeyframe(self, frame: int, x: float, y: float,
                    interp: Interpolation = Interpolation.Bezier) -> None:
        self.x.addKeyframe(frame, x, interp)
        self.y.addKeyframe(frame, y, interp)

    def __repr__(self) -> str:
        return f"Vec2Property({self.x.get():.2f}, {self.y.get():.2f})"

 

    def toDict(self) -> dict:
        return {"x": self.x.toDict(), "y": self.y.toDict()}

    @classmethod
    def fromDict(cls, data: dict, dx: float = 0.0, dy: float = 0.0) -> "Vec2Property":
        v = cls(dx, dy)
        xd = data.get("x", dx)
        yd = data.get("y", dy)
        if isinstance(xd, dict):
            v.x = AnimatableProperty.fromDict(xd, dx)
        else:
            v.x.setBaseValue(float(xd))
        if isinstance(yd, dict):
            v.y = AnimatableProperty.fromDict(yd, dy)
        else:
            v.y.setBaseValue(float(yd))
        return v


