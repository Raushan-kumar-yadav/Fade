from __future__ import annotations
import uuid
from backend.timeline.clips.baseClip import BaseClip
from backend.animation.animatableProperty import AnimatableProperty


class ImageClip(BaseClip):
    """
    A still-image clip.

    Decoding strategy
    -----------------
    ImageDecoder is called exactly *once* per asset; the result is
    cached as self._cachedFrame.  On the first render the BGRA
    bytes are baked into a skia.Image (self._skiaImage) and
    re-used every frame - zero re-allocation after the first draw.

    The clip does NOT need a DecodeScheduler because there is no
    temporal sequence to pump; the one and only frame is always valid.
    """

    CLIP_TYPE = "image"

    def __init__(
        self,
        clipId: str = "",
        startFrame: int = 0,
        duration: int = 90,
        assetId: str = "",
        filepath: str = "",
        color: tuple = (80, 80, 80, 255),
    ) -> None:
        super().__init__(
            clipId or str(uuid.uuid4()),
            startFrame,
            duration,
        )
        self.assetId  = assetId
        self.filepath = filepath
        self.color    = color

        self.cropLeft   = AnimatableProperty(0.0)
        self.cropRight  = AnimatableProperty(0.0)
        self.cropTop    = AnimatableProperty(0.0)
        self.cropBottom = AnimatableProperty(0.0)
        self.blendMode  = AnimatableProperty(0.0)

        self._cachedFrame     = None
        self._skiaImage       = None
        self._decodeAttempted = False

    def evaluateAll(self, frame: int) -> None:
        super().evaluateAll(frame)
        lf = self.localFrame(frame)
        self.cropLeft.update(lf)
        self.cropRight.update(lf)
        self.cropTop.update(lf)
        self.cropBottom.update(lf)
        self.blendMode.update(lf)

    def _ensureDecoded(self) -> None:
        if self._decodeAttempted:
            return
        self._decodeAttempted = True
        if not self.filepath:
            return
        try:
            from backend.media.decoder.imageDecoder import ImageDecoder
            decoder = ImageDecoder(self.filepath)
            frame   = decoder.decodeFrame(0)
            if frame and frame.valid:
                self._cachedFrame = frame
                self._skiaImage   = self._buildSkiaImage(frame)
                print(f"[ImageClip] decoded {self.filepath} ({frame.width}x{frame.height})", flush=True)
        except Exception as e:
            print(f"[ImageClip] decode error {self.filepath}: {e}", flush=True)

    @staticmethod
    def _buildSkiaImage(decoded):
        try:
            import skia
            info   = skia.ImageInfo.MakeN32Premul(decoded.width, decoded.height)
            skdata = skia.Data.MakeWithoutCopy(decoded.dataRGBA)
            return skia.Image.MakeRasterData(info, skdata, decoded.width * 4)
        except Exception as e:
            print(f"[ImageClip] Skia build error: {e}", flush=True)
            return None

    def render(self, canvas, frame: int) -> None:
        import skia
        self.evaluateAll(frame)
        self._ensureDecoded()

        canvas.save()
        self.transform.applyToCanvas(canvas)

        paint = skia.Paint()
        paint.setAlphaf(self.transform.opacity.get())

        from backend.timeline.clips.videoClip import BlendMode
        paint.setBlendMode(BlendMode.skiaMode(int(self.blendMode.get())))

        if self._skiaImage is not None:
            try:
                dst  = skia.Rect.MakeXYWH(0, 0, 1920, 1080)
                opts = skia.SamplingOptions(skia.FilterMode.kLinear)
                canvas.drawImageRect(self._skiaImage, dst, opts, paint)
            except Exception as e:
                print(f"[ImageClip] drawImageRect error: {e}", flush=True)
                self._renderSolid(canvas, paint)
        else:
            self._renderSolid(canvas, paint)

        canvas.restore()

    def _renderSolid(self, canvas, paint) -> None:
        import skia
        r, g, b, a = self.color
        paint.setColor(skia.Color(r, g, b, a))
        canvas.drawRect(skia.Rect.MakeXYWH(0, 0, 1920, 1080), paint)

    def getThumbnail(self, frame: int, width: int = 160, height: int = 90) -> bytes:
        import skia
        self._ensureDecoded()
        surf   = skia.Surface(width, height)
        canvas = surf.getCanvas()
        if self._skiaImage is not None:
            try:
                dst  = skia.Rect.MakeXYWH(0, 0, width, height)
                opts = skia.SamplingOptions(skia.FilterMode.kLinear)
                canvas.drawImageRect(self._skiaImage, dst, opts)
            except Exception:
                r, g, b, a = self.color
                canvas.clear(skia.Color(r, g, b, a))
        else:
            r, g, b, a = self.color
            canvas.clear(skia.Color(r, g, b, a))
        img = surf.makeImageSnapshot()
        return img.encodeToData(skia.kJPEG, 75).bytes()

    def toDict(self) -> dict:
        return {
            "type":       self.CLIP_TYPE,
            "clipId":     self.clipId,
            "startFrame": self.startFrame,
            "duration":   self.duration,
            "assetId":    self.assetId,
            "filepath":   self.filepath,
            "color":      list(self.color),
            "transform":  self.transform.toDict(),
            "cropLeft":   self.cropLeft.toDict(),
            "cropRight":  self.cropRight.toDict(),
            "cropTop":    self.cropTop.toDict(),
            "cropBottom": self.cropBottom.toDict(),
            "blendMode":  self.blendMode.toDict(),
            "masks":      [m.toDict() for m in self.masks],
            "effects":    [e.toDict() for e in self.effects],
        }

    @classmethod
    def fromDict(cls, data: dict) -> "ImageClip":
        from backend.animation.transform import Transform
        from backend.animation.animatableProperty import AnimatableProperty
        from backend.timeline.clips.textClip import MaskLayer
        from backend.timeline.effects.skslEffect import SkslEffect
        c = cls(
            clipId     = data["clipId"],
            startFrame = data["startFrame"],
            duration   = data["duration"],
            assetId    = data.get("assetId", ""),
            filepath   = data.get("filepath", ""),
            color      = tuple(data.get("color", [80, 80, 80, 255])),
        )
        if "transform" in data:
            c.transform = Transform.fromDict(data["transform"])

        def _ap(key: str, default: float) -> AnimatableProperty:
            raw = data.get(key, default)
            if isinstance(raw, dict):
                return AnimatableProperty.fromDict(raw, default)
            ap = AnimatableProperty(default)
            ap.setBaseValue(float(raw))
            return ap

        c.cropLeft   = _ap("cropLeft",  0.0)
        c.cropRight  = _ap("cropRight", 0.0)
        c.cropTop    = _ap("cropTop",   0.0)
        c.cropBottom = _ap("cropBottom",0.0)
        c.blendMode  = _ap("blendMode", 0.0)
        c.masks = [MaskLayer.fromDict(m) for m in data.get("masks", [])]
        for ed in data.get("effects", []):
            if ed.get("type", "").startswith("sksl:") or "typeId" in ed:
                try:
                    c.effects.append(SkslEffect.fromDict(ed))
                except Exception as ex:
                    print(f"[ImageClip] effect restore failed: {ex}")
        return c

