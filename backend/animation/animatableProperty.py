from __future__ import annotations
from backend.animation.scalarTrack import ScalarTrack
from backend.animation.keyframe import Keyframe, Interpolation, makeBezierKeyframe
from backend.animation import anim_debug as _dbg


class AnimatableProperty:
    """A float property that can hold keyframes for animation."""

    def __init__(self, defaultValue: float = 0.0) -> None:
        self._baseValue: float = defaultValue
        self._currentValue: float = defaultValue
        self._isAnimated: bool = False
        self._track: ScalarTrack = ScalarTrack()
        # Expression system
        self._expression: str | None = None
        self._expr_compiled = None          # compiled code object — cached on set
        self._expr_error: str = ""          # last eval error message

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

    #   Evaluation

    def update(self, frame: int, _prop: str = "?",
                _clip=None, _timeline=None) -> None:
        # Step 1: keyframe interpolation (existing path)
        if not self._isAnimated or self._track.empty():
            base = self._baseValue
        else:
            base = self._track.evaluateAt(frame, self._baseValue)

        # Step 2: expression override
        if self._expr_compiled is not None:
            try:
                from backend.animation.expression_context import build_context, SAFE_BUILTINS
                ctx = build_context(frame, base, _clip, _timeline)
                result = eval(self._expr_compiled,
                              {"__builtins__": SAFE_BUILTINS}, ctx)
                self._currentValue = float(result)
                self._expr_error = ""
            except Exception as exc:
                # Silently fall back — never break the render loop
                self._currentValue = base
                self._expr_error = str(exc)
        else:
            self._currentValue = base

    def evaluate(self, frame: int, _prop: str = "?",
                 _clip=None, _timeline=None) -> float:
        """Return the value at *frame* without mutating _currentValue.
        Applies expression if one is active (used for Inspector display value).
        """
        if not self._isAnimated or self._track.empty():
            base = self._baseValue
        else:
            base = self._track.evaluateAt(frame, self._baseValue)

        if self._expr_compiled is not None:
            try:
                from backend.animation.expression_context import build_context, SAFE_BUILTINS
                ctx    = build_context(frame, base, _clip, _timeline)
                result = eval(self._expr_compiled, {"__builtins__": SAFE_BUILTINS}, ctx)
                return float(result)
            except Exception:
                return base  # fall back silently
        return base

    def is_animated(self) -> bool:
        return self._isAnimated and not self._track.empty()

    #   Read

    def get(self) -> float:
        return self._currentValue

    def __float__(self) -> float:
        return self._currentValue

    def __repr__(self) -> str:
        animated = f", {len(self._track)} kf" if self._isAnimated else ""
        return f"AnimatableProperty({self._currentValue:.3f}{animated})"

    #   Expression helpers

    def set_expression(self, expr: str | None) -> None:
        """Set (or clear) the expression string. Compiles immediately on set."""
        if not expr:
            self._expression = None
            self._expr_compiled = None
            self._expr_error = ""
            return
        self._expression = expr.strip()
        try:
            self._expr_compiled = compile(self._expression, "<expression>", "eval")
            self._expr_error = ""
        except SyntaxError as exc:
            self._expr_compiled = None
            self._expr_error = f"SyntaxError: {exc}"

    def get_expression(self) -> str | None:
        return self._expression

    def expression_error(self) -> str:
        return self._expr_error

    #   Serialization  

    def toDict(self) -> dict:
        d: dict = {"base": self._baseValue, "animated": self._isAnimated}
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
        if self._expression:
            d["expression"] = self._expression
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
        # Restore expression if saved
        expr = data.get("expression")
        if expr:
            ap.set_expression(expr)
        return ap


class Vec2Property:
    """A 2D animatable property (x, y)."""

    def __init__(self, x: float = 0.0, y: float = 0.0) -> None:
        self.x = AnimatableProperty(x)
        self.y = AnimatableProperty(y)

    def update(self, frame: int, _prefix: str = "?",
                _clip=None, _timeline=None) -> None:
        self.x.update(frame, _prop=f"{_prefix}_x", _clip=_clip, _timeline=_timeline)
        self.y.update(frame, _prop=f"{_prefix}_y", _clip=_clip, _timeline=_timeline)

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
