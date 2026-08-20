from __future__ import annotations
import uuid
from typing import TYPE_CHECKING
from backend.timeline.clips.baseClip import BaseClip
from backend.animation.animatableProperty import AnimatableProperty

if TYPE_CHECKING:
    from backend.media.scheduler.decodeScheduler import DecodeScheduler
    from backend.media.asset.mediaAsset import MediaAsset


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
        color: tuple = (74, 144, 226, 255),
        # Asset reference  
        assetId: str = "",
    ) -> None:
        super().__init__(
            clipId or str(uuid.uuid4()),
            startFrame,
            duration,
        )
        self.color = color
        self.assetId = assetId     # pointer to MediaAsset in the AssetLibrary

        # Injected by Engine after construction
        self._scheduler: "DecodeScheduler | None" = None
        self._projectFps: float = 30.0

        # Animatable clip params
        self.cropLeft = AnimatableProperty(0.0)
        self.cropRight = AnimatableProperty(0.0)
        self.cropTop = AnimatableProperty(0.0)
        self.cropBottom = AnimatableProperty(0.0)
        self.blendMode  = AnimatableProperty(0.0)

        self._lastFrame = -1
        self._lastValidFrame: "DecodedFrame | None" = None  # hold-last-frame on cache miss

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

    def sourceFrame(self, frame: int) -> int:
        localFrame = self.localFrame(frame)
        if self._scheduler is None:
            return localFrame
        return self._scheduler.sourceFrame(
            self.clipId,
            localFrame,
            self._projectFps,
        )

    #   Render  

    def render(self, canvas, frame: int) -> None:
        import skia
        self.evaluateAll(frame)

        canvas.save()
        self.transform.applyToCanvas(canvas)

        paint = skia.Paint()
        paint.setAlphaf(self.transform.opacity.get())
        paint.setBlendMode(BlendMode.skiaMode(int(self.blendMode.get())))

        if self.assetId:
            self._renderMedia(canvas, paint, frame)
        else:
            self._renderSolid(canvas, paint)

        canvas.restore()

    def _renderSolid(self, canvas, paint) -> None:
        import skia
        r, g, b, a = self.color
        paint.setColor(skia.Color(r, g, b, a))
        canvas.drawRect(skia.Rect.MakeXYWH(0, 0, 1920, 1080), paint)

    def _renderMedia(self, canvas, paint, frame: int) -> None:
        """
        Ask the DecodeScheduler for this frame from the shared FrameCache.
        frame = global timeline frame; convert to local clip frame for cache lookup.
        On a cache miss, re-uses the last successfully decoded frame so the
        viewport never shows the solid blue placeholder during playback.
        """
        import skia

        if self._scheduler is None:
            self._renderSolid(canvas, paint)
            return

        # Convert global frame to local frame (0-based from clip start)
        localFrame = self.sourceFrame(frame)

        # Fast path: cache lookup by assetId + localFrame
        decoded = self._scheduler.tryGetFrame(self.assetId, localFrame)

        # On cache miss, fall back to last valid frame (hold-last-frame)
        if not (decoded and decoded.valid):
            decoded = self._lastValidFrame

        if decoded and decoded.valid:
            expected = decoded.width * decoded.height * 4
            if len(decoded.dataRGBA) != expected:
                self._renderSolid(canvas, paint)
            else:
                try:
                    info   = skia.ImageInfo.MakeN32Premul(decoded.width, decoded.height)
                    skdata = skia.Data.MakeWithCopy(decoded.dataRGBA)
                    image  = skia.Image.MakeRasterData(info, skdata, decoded.width * 4)
                    if image is not None:
                        # Scale decoded frame to fill the full compositor canvas.
                        dst  = skia.Rect.MakeXYWH(0, 0, 1920, 1080)
                        opts = skia.SamplingOptions(skia.FilterMode.kLinear)
                        canvas.drawImageRect(image, dst, opts, paint)
                        # Cache for next cache-miss fallback
                        self._lastValidFrame = decoded
                    else:
                        self._renderSolid(canvas, paint)
                    del skdata
                except Exception as e:
                    print(f"[VideoClip] drawImage error frame={frame} local={localFrame}: {e}")
                    self._renderSolid(canvas, paint)
        else:
            # No frame available at all (clip just loaded) — show solid placeholder
            self._renderSolid(canvas, paint)

 

    def setScheduler(self, scheduler: "DecodeScheduler", fps: float = 30.0) -> None:
        """Injected by Engine when a clip is added to the timeline."""
        self._scheduler  = scheduler
        self._projectFps = fps

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
            "assetId": self.assetId,
            "color": list(self.color),
            "transform":   self.transform.toDict(),
            "cropLeft": self.cropLeft.get(),
            "cropRight":  self.cropRight.get(),
            "cropTop": self.cropTop.get(),
            "cropBottom": self.cropBottom.get(),
            "blendMode":  int(self.blendMode.get()),
        }

    @classmethod
    def fromDict(cls, data: dict) -> "VideoClip":
        from backend.animation.transform import Transform
        c = cls(
            clipId = data["clipId"],
            startFrame = data["startFrame"],
            duration = data["duration"],
            assetId = data.get("assetId", ""),
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
