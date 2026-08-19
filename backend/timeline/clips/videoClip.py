from __future__ import annotations
import uuid
from backend.timeline.clips.baseClip import BaseClip
from backend.animation.animatableProperty import AnimatableProperty


class BlendMode:
    NAMES = [
        "Normal", "Multiply", "Screen", "Overlay",
        "Darken", "Lighten", "ColorDodge", "ColorBurn",
        "HardLight", "SoftLight", "Difference", "Exclusion",
        "Hue", "Saturation", "Color", "Luminosity",
    ]

    @classmethod
    def skiaMode(cls, index: int):
        """Return the skia.BlendMode enum for a given index."""
        import skia
        _map = {
            0:  skia.BlendMode.kSrcOver,   # Normal
            1:  skia.BlendMode.kMultiply,
            2:  skia.BlendMode.kScreen,
            3:  skia.BlendMode.kOverlay,
            4:  skia.BlendMode.kDarken,
            5:  skia.BlendMode.kLighten,
            6:  skia.BlendMode.kColorDodge,
            7:  skia.BlendMode.kColorBurn,
            8:  skia.BlendMode.kHardLight,
            9:  skia.BlendMode.kSoftLight,
            10: skia.BlendMode.kDifference,
            11: skia.BlendMode.kExclusion,
        }
        return _map.get(index, skia.BlendMode.kSrcOver)


class VideoClip(BaseClip):
 

    CLIP_TYPE = "video"

    def __init__(
        self,
        clipId: str = "",
        startFrame: int = 0,
        duration: int = 90,
        mediaPath: str = "",         
        color: tuple = (74, 144, 226, 255),  
    ) -> None:
        super().__init__(
            clipId or str(uuid.uuid4()),
            startFrame,
            duration,
        )
        self.mediaPath = mediaPath
        self.color = color          

        # Animatable clip    
         
        self.cropLeft = AnimatableProperty(0.0)
        self.cropRight  = AnimatableProperty(0.0)
        self.cropTop = AnimatableProperty(0.0)
        self.cropBottom = AnimatableProperty(0.0)

        self.blendMode  = AnimatableProperty(0.0)

        self._lastFrame = -1    

    #   evaluateAll  

    def evaluateAll(self, frame: int) -> None:
        if frame == self._lastFrame:
            return
        self._lastFrame = frame

        lf = self.localFrame(frame)   
        self.transform.evaluateAll(lf)
        self.cropLeft.update(lf)
        self.cropRight.update(lf)
        self.cropTop.update(lf)
        self.cropBottom.update(lf)
        self.blendMode.update(lf)
        for effect in self.effects:
            if hasattr(effect, 'evaluateAll'):
                effect.evaluateAll(lf)

    #   Render  

    def render(self, canvas, frame: int) -> None:
        import skia
        self.evaluateAll(frame)

        canvas.save()
        self.transform.applyToCanvas(canvas)

        paint = skia.Paint()
        paint.setAlphaf(self.transform.opacity.get())
        paint.setBlendMode(BlendMode.skiaMode(int(self.blendMode.get())))

        if self.mediaPath:
            self._renderMedia(canvas, paint, frame)
        else:
            self._renderSolid(canvas, paint)

        canvas.restore()

    def _renderSolid(self, canvas, paint) -> None:
        """Draw a solid color rectangle — placeholder until real decoder is wired."""
        import skia
        r, g, b, a = self.color
        paint.setColor(skia.Color(r, g, b, a))
        # TODO: replace with actual clip bounds once layout system is added
        canvas.drawRect(skia.Rect.MakeXYWH(0, 0, 1920, 1080), paint)

    def _renderMedia(self, canvas, paint, frame: int) -> None:
        """Render decoded video frame — decoder will be wired here."""
        # TODO: call decoder.getFrame(self.mediaPath, frame) → skia.Image
        # For now fall back to solid
        self._renderSolid(canvas, paint)

    #   Thumbnail  

    def getThumbnail(self, frame: int, width: int = 160, height: int = 90) -> bytes:
        import skia
        surf   = skia.Surface(width, height)
        canvas = surf.getCanvas()
        r, g, b, a = self.color
        canvas.clear(skia.Color(r, g, b, a))
        img = surf.makeImageSnapshot()
        return img.encodeToData(skia.kJPEG, 75).bytes()

    #   Serialization  

    def toDict(self) -> dict:
        return {
            "type": self.CLIP_TYPE,
            "clipId": self.clipId,
            "startFrame": self.startFrame,
            "duration": self.duration,
            "mediaPath":  self.mediaPath,
            "color": list(self.color),
            "transform": self.transform.toDict(),
            "cropLeft": self.cropLeft.get(),
            "cropRight": self.cropRight.get(),
            "cropTop": self.cropTop.get(),
            "cropBottom": self.cropBottom.get(),
            "blendMode": int(self.blendMode.get()),
        }

    @classmethod
    def fromDict(cls, data: dict) -> "VideoClip":
        from backend.animation.transform import Transform
        c = cls(
            clipId = data["clipId"],
            startFrame = data["startFrame"],
            duration = data["duration"],
            mediaPath  = data.get("mediaPath", ""),
            color = tuple(data.get("color", [74, 144, 226, 255])),
        )
        if "transform" in data:
            c.transform = Transform.fromDict(data["transform"])
        c.cropLeft.setBaseValue(data.get("cropLeft", 0.0))
        c.cropRight.setBaseValue(data.get("cropRight", 0.0))
        c.cropTop.setBaseValue(data.get("cropTop", 0.0))
        c.cropBottom.setBaseValue(data.get("cropBottom", 0.0))
        c.blendMode.setBaseValue(float(data.get("blendMode", 0)))
        return c
