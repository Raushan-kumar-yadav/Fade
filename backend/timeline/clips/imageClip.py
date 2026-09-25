from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from backend.timeline.clips.baseClip import BaseClip
from backend.animation.animatableProperty import AnimatableProperty


# ---------------------------------------------------------------------------
# BrushStroke
# ---------------------------------------------------------------------------

@dataclass
class BrushStroke:
    """
    A single brush stroke owned by an ImageClip.

    Each stroke is a list of (x, y) positions in composition space, along
    with visual style attributes.  Multiple strokes are stored as
    ImageClip.brush_strokes so that every Brush action on the same clip is
    kept together and individually undoable via the CommandStack.
    """
    points: list = field(default_factory=list)   # list of {"x": float, "y": float}
    size: float = 10.0
    color: list = field(default_factory=lambda: [1.0, 1.0, 1.0, 1.0])  # RGBA 0-1
    opacity: float = 1.0

    def toDict(self) -> dict:
        return {
            "points": self.points,
            "size":   self.size,
            "color":  self.color,
            "opacity": self.opacity,
        }

    @classmethod
    def fromDict(cls, d: dict) -> "BrushStroke":
        return cls(
            points  = d.get("points", []),
            size    = d.get("size", 10.0),
            color   = d.get("color", [1.0, 1.0, 1.0, 1.0]),
            opacity = d.get("opacity", 1.0),
        )


# ---------------------------------------------------------------------------
# ImageClip
# ---------------------------------------------------------------------------

class ImageClip(BaseClip):
    

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

        self.cropLeft = AnimatableProperty(0.0)
        self.cropRight  = AnimatableProperty(0.0)
        self.cropTop = AnimatableProperty(0.0)
        self.cropBottom = AnimatableProperty(0.0)
        self.blendMode = AnimatableProperty(0.0)

        self._cachedFrame = None
        self._skiaImage = None
        self._decodeAttempted = False

        # Brush strokes painted onto this clip (leader's BrushPoint model)
        self.brush_strokes: list[BrushStroke] = []

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
            info = skia.ImageInfo.MakeN32Premul(decoded.width, decoded.height)
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
                dst = skia.Rect.MakeXYWH(0, 0, 1920, 1080)
                opts = skia.SamplingOptions(skia.FilterMode.kLinear)
                canvas.drawImageRect(self._skiaImage, dst, opts, paint)
            except Exception as e:
                print(f"[ImageClip] drawImageRect error: {e}", flush=True)
                self._renderSolid(canvas, paint)
        else:
            self._renderSolid(canvas, paint)

        # Draw brush strokes on top of the image
        self._renderBrushStrokes(canvas)

        canvas.restore()

    def _renderBrushStrokes(self, canvas) -> None:
        """Paint all owned BrushStroke objects onto the 1920x1080 compositor canvas.

        BrushStroke points are stored in composition space (e.g. 1080x1920 for a
        portrait comp).  The compositor always outputs 1920x1080.  We apply the
        same object-fit:contain (letterbox) transform that the frontend uses so the
        strokes land exactly where the user drew them.

        Transform (mirrors frontend viewportUtils.ts compositionToViewport):
            scale   = min(1920 / compW, 1080 / compH)
            offsetX = (1920 - compW * scale) / 2
            offsetY = (1080 - compH * scale) / 2
            renderX = compX * scale + offsetX
            renderY = compY * scale + offsetY

        For a 1920x1080 composition scale=1, offsets=0, so existing behaviour is
        completely preserved.
        """
        if not self.brush_strokes:
            return
        try:
            import skia
            from backend.rendering.nodes.penNode import build_skpath
            from backend.animation.animPath import PathVertex
        except Exception:
            return

        # --- Composition dimensions (used for the letterbox transform) -----------
        RENDER_W, RENDER_H = 1920, 1080
        try:
            from backend.state import engine as _engine
            tl = _engine.activeTimeline
            comp_w = float(getattr(tl, 'width',  RENDER_W)) if tl else float(RENDER_W)
            comp_h = float(getattr(tl, 'height', RENDER_H)) if tl else float(RENDER_H)
        except Exception:
            comp_w, comp_h = float(RENDER_W), float(RENDER_H)

        # object-fit:contain scale + letter-box offsets
        scale   = min(RENDER_W / comp_w, RENDER_H / comp_h)
        offset_x = (RENDER_W - comp_w * scale) / 2.0
        offset_y = (RENDER_H - comp_h * scale) / 2.0

        # --- Draw each stroke ---------------------------------------------------
        for stroke in self.brush_strokes:
            pts = stroke.points
            if len(pts) < 2:
                continue

            # Map composition-space points → 1920x1080 renderer space
            vertices = [
                PathVertex(
                    x=p["x"] * scale + offset_x,
                    y=p["y"] * scale + offset_y,
                )
                for p in pts
            ]
            path = build_skpath(vertices, is_closed=False)

            r, g, b, a = stroke.color
            paint = skia.Paint()
            paint.setAntiAlias(True)
            paint.setStyle(skia.Paint.kStroke_Style)
            # Scale stroke width so it looks the same relative to the image on screen
            paint.setStrokeWidth(stroke.size * scale)
            paint.setStrokeCap(skia.Paint.kRound_Cap)
            paint.setStrokeJoin(skia.Paint.kRound_Join)
            paint.setColor4f(skia.Color4f(r, g, b, a * stroke.opacity))
            canvas.drawPath(path, paint)


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
            "type": self.CLIP_TYPE,
            "clipId": self.clipId,
            "startFrame": self.startFrame,
            "duration": self.duration,
            "assetId": self.assetId,
            "filepath": self.filepath,
            "color": list(self.color),
            "transform": self.transform.toDict(),
            "cropLeft": self.cropLeft.toDict(),
            "cropRight": self.cropRight.toDict(),
            "cropTop": self.cropTop.toDict(),
            "cropBottom": self.cropBottom.toDict(),
            "blendMode": self.blendMode.toDict(),
            "masks": [m.toDict() for m in self.masks],
            "effects": [e.toDict() for e in self.effects],
            "brush_strokes": [s.toDict() for s in self.brush_strokes],
        }

    @classmethod
    def fromDict(cls, data: dict) -> "ImageClip":
        from backend.animation.transform import Transform
        from backend.animation.animatableProperty import AnimatableProperty
        from backend.timeline.clips.textClip import MaskLayer
        from backend.timeline.effects.skslEffect import SkslEffect
        c = cls(
            clipId = data["clipId"],
            startFrame = data["startFrame"],
            duration = data["duration"],
            assetId = data.get("assetId", ""),
            filepath = data.get("filepath", ""),
            color = tuple(data.get("color", [80, 80, 80, 255])),
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

        c.cropLeft = _ap("cropLeft",  0.0)
        c.cropRight = _ap("cropRight", 0.0)
        c.cropTop = _ap("cropTop",   0.0)
        c.cropBottom = _ap("cropBottom",0.0)
        c.blendMode = _ap("blendMode", 0.0)
        c.masks = [MaskLayer.fromDict(m) for m in data.get("masks", [])]
        for ed in data.get("effects", []):
            if ed.get("type", "").startswith("sksl:") or "typeId" in ed:
                try:
                    c.effects.append(SkslEffect.fromDict(ed))
                except Exception as ex:
                    print(f"[ImageClip] effect restore failed: {ex}")
        c.brush_strokes = [BrushStroke.fromDict(s) for s in data.get("brush_strokes", [])]
        return c

