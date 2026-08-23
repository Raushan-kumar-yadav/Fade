from __future__ import annotations
import math
from backend.animation.animatableProperty import AnimatableProperty, Vec2Property


class Transform:
    """
    Standard clip transform — position, scale, rotation, opacity, anchor.
    Mirrors C++ ClipTransform / m_transform in VideoClip.

    All properties are AnimatableProperty — they can hold keyframes
    and are evaluated every frame by calling evaluateAll(localFrame).
    """

    def __init__(self) -> None:
        # Position in pixels  
        self.position = Vec2Property(0.0, 0.0)

        # Scale  
        self.scale = Vec2Property(1.0, 1.0)

        # Rotation  
        self.rotation = AnimatableProperty(0.0)

        # Opacity  
        self.opacity = AnimatableProperty(1.0)

        # Anchor point  
        self.anchor = Vec2Property(0.0, 0.0)

    #   Evaluation  

    def evaluateAll(self, frame: int) -> None:
        """Update all properties for the given (clip-local) frame."""
        self.position.update(frame)
        self.scale.update(frame)
        self.rotation.update(frame)
        self.opacity.update(frame)
        self.anchor.update(frame)

    #   Computed  

    def getModelMatrix(self) -> list[list[float]]:
    
        tx, ty = self.position.get()
        sx, sy = self.scale.get()
        deg = self.rotation.get()
        rad = math.radians(deg)
        cosA = math.cos(rad)
        sinA = math.sin(rad)

        return [
            [sx * cosA,  -sx * sinA,  tx],
            [sy * sinA,   sy * cosA,  ty],
            [0.0, 0.0, 1.0],
        ]

    def applyToCanvas(self, canvas) -> None:
        """Apply transform directly to a Skia canvas."""
        import skia
        tx, ty = self.position.get()
        sx, sy = self.scale.get()
        deg = self.rotation.get()
        ax, ay = self.anchor.get()

        canvas.translate(tx + ax, ty + ay)
        canvas.rotate(deg)
        canvas.scale(sx, sy)
        canvas.translate(-ax, -ay)

    #   Serialization

    def toDict(self) -> dict:
        return {
            "position": self.position.toDict(),
            "scale":    self.scale.toDict(),
            "rotation": self.rotation.toDict(),
            "opacity":  self.opacity.toDict(),
            "anchor":   self.anchor.toDict(),
        }

    @classmethod
    def fromDict(cls, data: dict) -> "Transform":
        from backend.animation.animatableProperty import Vec2Property, AnimatableProperty
        t = cls()
        pd = data.get("position", {})
        # Backwards-compat: old format stored {"x": float, "y": float}
        if isinstance(pd.get("x"), dict) or isinstance(pd.get("y"), dict):
            t.position = Vec2Property.fromDict(pd, 0.0, 0.0)
        else:
            t.position.setBase(float(pd.get("x", 0.0)), float(pd.get("y", 0.0)))

        sd = data.get("scale", {})
        if isinstance(sd.get("x"), dict) or isinstance(sd.get("y"), dict):
            t.scale = Vec2Property.fromDict(sd, 1.0, 1.0)
        else:
            t.scale.setBase(float(sd.get("x", 1.0)), float(sd.get("y", 1.0)))

        ad = data.get("anchor", {})
        if isinstance(ad.get("x"), dict) or isinstance(ad.get("y"), dict):
            t.anchor = Vec2Property.fromDict(ad, 0.0, 0.0)
        else:
            t.anchor.setBase(float(ad.get("x", 0.0)), float(ad.get("y", 0.0)))

        rd = data.get("rotation", 0.0)
        t.rotation = AnimatableProperty.fromDict(rd if isinstance(rd, dict) else {"base": rd}, 0.0)

        od = data.get("opacity", 1.0)
        t.opacity = AnimatableProperty.fromDict(od if isinstance(od, dict) else {"base": od}, 1.0)

        return t

    def __repr__(self) -> str:
        px, py = self.position.get()
        sx, sy = self.scale.get()
        return (
            f"Transform("
            f"pos=({px:.1f},{py:.1f}), "
            f"scale=({sx:.2f},{sy:.2f}), "
            f"rot={self.rotation.get():.1f}°, "
            f"opacity={self.opacity.get():.2f})"
        )
