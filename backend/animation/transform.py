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
        px, py = self.position.get()
        sx, sy = self.scale.get()
        ax, ay = self.anchor.get()
        return {
            "position": {"x": px, "y": py},
            "scale": {"x": sx, "y": sy},
            "rotation": self.rotation.get(),
            "opacity": self.opacity.get(),
            "anchor": {"x": ax, "y": ay},
        }

    @classmethod
    def fromDict(cls, data: dict) -> "Transform":
        t = cls()
        p = data.get("position", {})
        t.position.setBase(p.get("x", 0.0), p.get("y", 0.0))
        s = data.get("scale", {})
        t.scale.setBase(s.get("x", 1.0), s.get("y", 1.0))
        t.rotation.setBaseValue(data.get("rotation", 0.0))
        t.opacity.setBaseValue(data.get("opacity", 1.0))
        a = data.get("anchor", {})
        t.anchor.setBase(a.get("x", 0.0), a.get("y", 0.0))
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
