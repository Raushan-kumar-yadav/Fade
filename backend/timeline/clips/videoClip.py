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
        mediaOffset: int = 0,
    ) -> None:
        super().__init__(
            clipId or str(uuid.uuid4()),
            startFrame,
            duration,
        )
        self.color = color
        self.assetId = assetId
        self.mediaOffset: int = mediaOffset   

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
        self._lastValidFrame: "DecodedFrame | None" = None   

    #   evaluateAll  

    def evaluateAll(self, frame: int) -> None:
        if frame == self._lastFrame:
            return
        self._lastFrame = frame
        
        # Call BaseClip.evaluateAll to handle 
        super().evaluateAll(frame)

        lf = self.localFrame(frame)   
        self.cropLeft.update(lf)
        self.cropRight.update(lf)
        self.cropTop.update(lf)
        self.cropBottom.update(lf)
        self.blendMode.update(lf)

    def sourceFrame(self, frame: int) -> int:
        localFrame = self.localFrame(frame) + self.mediaOffset
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
         
        import skia

        if self._scheduler is None:
            self._renderSolid(canvas, paint)
            return

        #   global frame to local  
        localFrame = self.sourceFrame(frame)

        #  cache lookup  
        decoded = self._scheduler.tryGetFrame(self.assetId, localFrame)

        # On cache miss   
        if not (decoded and decoded.valid):
            decoded = self._lastValidFrame

        if decoded and decoded.valid:
            expected = decoded.width * decoded.height * 4
            if len(decoded.dataRGBA) != expected:
                self._renderSolid(canvas, paint)
            else:
                try:
                    if getattr(decoded, 'skiaImage', None) is not None:
                        image = decoded.skiaImage
                        dst  = skia.Rect.MakeXYWH(0, 0, 1920, 1080)
                        opts = skia.SamplingOptions(skia.FilterMode.kLinear)
                        canvas.drawImageRect(image, dst, opts, paint)
                        self._lastValidFrame = decoded
                    else:
                        info = skia.ImageInfo.MakeN32Premul(decoded.width, decoded.height)
                        skdata = skia.Data.MakeWithoutCopy(decoded.dataRGBA)
                        image = skia.Image.MakeRasterData(info, skdata, decoded.width * 4)
                        if image is not None:
                            dst  = skia.Rect.MakeXYWH(0, 0, 1920, 1080)
                            opts = skia.SamplingOptions(skia.FilterMode.kLinear)
                            canvas.drawImageRect(image, dst, opts, paint)
                            self._lastValidFrame = decoded
                        else:
                            self._renderSolid(canvas, paint)
                except Exception as e:
                    print(f"[VideoClip] drawImage error frame={frame} local={localFrame}: {e}")
                    self._renderSolid(canvas, paint)
        else:
            # No frame available at all  
            self._renderSolid(canvas, paint)

 

    def setScheduler(self, scheduler: "DecodeScheduler", fps: float = 30.0) -> None:
         
        self._scheduler  = scheduler
        self._projectFps = fps

    #   Thumbnail  

    def getThumbnail(self, frame: int, width: int = 160, height: int = 90) -> bytes:
        import skia
        surf = skia.Surface(width, height)
        canvas = surf.getCanvas()
        r, g, b, a = self.color
        canvas.clear(skia.Color(r, g, b, a))
        img = surf.makeImageSnapshot()
        return img.encodeToData(skia.kJPEG, 75).bytes()

    #   Serialization

    def toDict(self) -> dict:
        from backend.state import _library  # noqa 
        filepath = ""
        try:
            filepath = _library[self.assetId].filepath if self.assetId in _library else ""
        except Exception:
            pass
        return {
            "type": self.CLIP_TYPE,
            "clipId": self.clipId,
            "startFrame": self.startFrame,
            "duration": self.duration,
            "assetId": self.assetId,
            "filepath": filepath,
            "color": list(self.color),
            "mediaOffset": self.mediaOffset,
            "transform": self.transform.toDict(),
            "cropLeft": self.cropLeft.toDict(),
            "cropRight": self.cropRight.toDict(),
            "cropTop": self.cropTop.toDict(),
            "cropBottom": self.cropBottom.toDict(),
            "blendMode": self.blendMode.toDict(),
            "masks": [m.toDict() for m in self.masks],
            "effects": [e.toDict() for e in self.effects],
        }

    @classmethod
    def fromDict(cls, data: dict) -> "VideoClip":
        from backend.animation.transform import Transform
        from backend.animation.animatableProperty import AnimatableProperty
        from backend.timeline.clips.textClip import MaskLayer
        from backend.timeline.effects.skslEffect import SkslEffect

        c = cls(
            clipId = data["clipId"],
            startFrame = data["startFrame"],
            duration = data["duration"],
            assetId = data.get("assetId", ""),
            color = tuple(data.get("color", [74, 144, 226, 255])),
            mediaOffset = data.get("mediaOffset", 0),
        )
        # Store filepath 
        c.filepath = data.get("filepath", "")

        if "transform" in data:
            c.transform = Transform.fromDict(data["transform"])

        # Animated properties 
        def _ap(key: str, default: float) -> AnimatableProperty:
            raw = data.get(key, default)
            if isinstance(raw, dict):
                return AnimatableProperty.fromDict(raw, default)
            ap = AnimatableProperty(default)
            ap.setBaseValue(float(raw))
            return ap

        c.cropLeft = _ap("cropLeft",  0.0)
        c.cropRight = _ap("cropRight", 0.0)
        c.cropTop = _ap("cropTop",   0.0)
        c.cropBottom = _ap("cropBottom",0.0)
        c.blendMode = _ap("blendMode", 0.0)

        c.masks   = [MaskLayer.fromDict(m) for m in data.get("masks", [])]

        # Restore effects
        for ed in data.get("effects", []):
            t = ed.get("type", "")
            if t.startswith("sksl:") or "typeId" in ed:
                try:
                    c.effects.append(SkslEffect.fromDict(ed))
                except Exception as ex:
                    print(f"[VideoClip] effect restore failed: {ex}")

        return c

