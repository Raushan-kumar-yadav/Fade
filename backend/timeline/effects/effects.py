from __future__ import annotations
import math
import uuid
import skia


class BaseEffect:
    def __init__(self, name: str) -> None:
        self.effectId = str(uuid.uuid4())
        self.name     = name
        self.enabled  = True

    def apply(self, canvas: skia.Canvas, frame: int) -> None:
        raise NotImplementedError

    def params(self) -> dict:
        return {}

    def setParam(self, key: str, val: float) -> None:
        pass

    def toDict(self) -> dict:
        return {}

    def _baseDict(self) -> dict:
        return {"effectId": self.effectId, "name": self.name, "enabled": self.enabled}

    def _applyBaseDict(self, data: dict) -> None:
        if "effectId" in data:
            self.effectId = data["effectId"]
        self.enabled = data.get("enabled", True)

    @classmethod
    def fromDict(cls, data: dict) -> "BaseEffect":
        raise NotImplementedError


class BlurEffect(BaseEffect):
    NAME = "Blur"

    def __init__(self, blur_x: float = 8.0, blur_y: float = 8.0) -> None:
        super().__init__(self.NAME)
        self.blur_x = blur_x
        self.blur_y = blur_y

    def apply(self, canvas: skia.Canvas, frame: int) -> None:
        if not self.enabled or (self.blur_x == 0 and self.blur_y == 0):
            return
        f = skia.ImageFilters.Blur(max(0.01, self.blur_x), max(0.01, self.blur_y))
        p = skia.Paint()
        p.setImageFilter(f)
        canvas.saveLayer(None, p)
        canvas.restore()

    def toDict(self) -> dict:
        return {**self._baseDict(), "type": "blur", "blur_x": self.blur_x, "blur_y": self.blur_y}

    @classmethod
    def fromDict(cls, data: dict) -> "BlurEffect":
        e = cls(data.get("blur_x", 8.0), data.get("blur_y", 8.0))
        e._applyBaseDict(data)
        return e

    def params(self) -> dict:
        return {"blur_x": (self.blur_x, 0.0, 100.0), "blur_y": (self.blur_y, 0.0, 100.0)}

    def setParam(self, key: str, val: float) -> None:
        if key == "blur_x":   self.blur_x = val
        elif key == "blur_y": self.blur_y = val


class BrightnessContrastEffect(BaseEffect):
    NAME = "Brightness / Contrast"

    def __init__(self, brightness: float = 0.0, contrast: float = 1.0) -> None:
        super().__init__(self.NAME)
        self.brightness = brightness
        self.contrast   = contrast

    def _matrix(self) -> list[float]:
        c = self.contrast
        t = (1.0 - c) * 0.5 + self.brightness
        return [c, 0, 0, 0, t,  0, c, 0, 0, t,  0, 0, c, 0, t,  0, 0, 0, 1, 0]

    def apply(self, canvas: skia.Canvas, frame: int) -> None:
        if not self.enabled:
            return
        cf = skia.ColorFilters.Matrix(self._matrix())
        p  = skia.Paint()
        p.setColorFilter(cf)
        canvas.saveLayer(None, p)
        canvas.restore()

    def toDict(self) -> dict:
        return {**self._baseDict(), "type": "brightness_contrast",
                "brightness": self.brightness, "contrast": self.contrast}

    @classmethod
    def fromDict(cls, data: dict) -> "BrightnessContrastEffect":
        e = cls(data.get("brightness", 0.0), data.get("contrast", 1.0))
        e._applyBaseDict(data)
        return e

    def params(self) -> dict:
        return {"brightness": (self.brightness, -1.0, 1.0), "contrast": (self.contrast, 0.0, 3.0)}

    def setParam(self, key: str, val: float) -> None:
        if key == "brightness": self.brightness = val
        elif key == "contrast": self.contrast = val


class HSLEffect(BaseEffect):
    NAME = "HSL"

    def __init__(self, hue: float = 0.0, saturation: float = 1.0, lightness: float = 0.0) -> None:
        super().__init__(self.NAME)
        self.hue        = hue
        self.saturation = saturation
        self.lightness  = lightness

    def _matrix(self) -> list[float]:
        h    = math.radians(self.hue)
        s    = self.saturation
        lu   = self.lightness
        cosH = math.cos(h)
        sinH = math.sin(h)
        lr = 0.213; lg = 0.715; lb = 0.072
        m = [
            lr + cosH*(1-lr)*s  + sinH*(-lr)*s,   lg + cosH*(-lg)*s + sinH*(-lg)*s,   lb + cosH*(-lb)*s  + sinH*(1-lb)*s,  0, lu,
            lr + cosH*(-lr)*s   + sinH*(0.143)*s,  lg + cosH*(1-lg)*s+ sinH*(0.14)*s,  lb + cosH*(-lb)*s  + sinH*(-0.283)*s,0, lu,
            lr + cosH*(-lr)*s   + sinH*(-(1-lr))*s,lg + cosH*(-lg)*s + sinH*(lg)*s,    lb + cosH*(1-lb)*s + sinH*(lb)*s,   0, lu,
            0, 0, 0, 1, 0,
        ]
        return m

    def apply(self, canvas: skia.Canvas, frame: int) -> None:
        if not self.enabled:
            return
        cf = skia.ColorFilters.Matrix(self._matrix())
        p  = skia.Paint()
        p.setColorFilter(cf)
        canvas.saveLayer(None, p)
        canvas.restore()

    def toDict(self) -> dict:
        return {**self._baseDict(), "type": "hsl",
                "hue": self.hue, "saturation": self.saturation, "lightness": self.lightness}

    @classmethod
    def fromDict(cls, data: dict) -> "HSLEffect":
        e = cls(data.get("hue", 0.0), data.get("saturation", 1.0), data.get("lightness", 0.0))
        e._applyBaseDict(data)
        return e

    def params(self) -> dict:
        return {
            "hue":        (self.hue,        -180.0, 180.0),
            "saturation": (self.saturation,    0.0,   3.0),
            "lightness":  (self.lightness,    -1.0,   1.0),
        }

    def setParam(self, key: str, val: float) -> None:
        if key == "hue":          self.hue = val
        elif key == "saturation": self.saturation = val
        elif key == "lightness":  self.lightness = val


class ColorGradeEffect(BaseEffect):
    NAME = "Color Grade"

    def __init__(self, temperature: float = 0.0, tint: float = 0.0) -> None:
        super().__init__(self.NAME)
        self.temperature = temperature
        self.tint        = tint

    def apply(self, canvas: skia.Canvas, frame: int) -> None:
        if not self.enabled:
            return
        t   = self.temperature
        tnt = self.tint
        matrix = [
            1+t,  0,      0,     0, 0,
            0,    1+tnt,  0,     0, 0,
            0,    0,      1-t,   0, 0,
            0,    0,      0,     1, 0,
        ]
        cf = skia.ColorFilters.Matrix(matrix)
        p  = skia.Paint()
        p.setColorFilter(cf)
        canvas.saveLayer(None, p)
        canvas.restore()

    def toDict(self) -> dict:
        return {**self._baseDict(), "type": "color_grade",
                "temperature": self.temperature, "tint": self.tint}

    @classmethod
    def fromDict(cls, data: dict) -> "ColorGradeEffect":
        e = cls(data.get("temperature", 0.0), data.get("tint", 0.0))
        e._applyBaseDict(data)
        return e

    def params(self) -> dict:
        return {"temperature": (self.temperature, -1.0, 1.0), "tint": (self.tint, -1.0, 1.0)}

    def setParam(self, key: str, val: float) -> None:
        if key == "temperature": self.temperature = val
        elif key == "tint":      self.tint = val


class SharpenEffect(BaseEffect):
    NAME = "Sharpen"

    def __init__(self, amount: float = 0.5) -> None:
        super().__init__(self.NAME)
        self.amount = amount

    def apply(self, canvas: skia.Canvas, frame: int) -> None:
        if not self.enabled or self.amount == 0:
            return
        a = self.amount * 2.0
        kernel = [0, -a, 0, -a, 1 + 4*a, -a, 0, -a, 0]
        f = skia.ImageFilters.MatrixConvolution(
            (3, 3), kernel, 1.0, 0.0, (1, 1),
            skia.TileMode.kClamp, False, None,
        )
        p = skia.Paint()
        p.setImageFilter(f)
        canvas.saveLayer(None, p)
        canvas.restore()

    def toDict(self) -> dict:
        return {**self._baseDict(), "type": "sharpen", "amount": self.amount}

    @classmethod
    def fromDict(cls, data: dict) -> "SharpenEffect":
        e = cls(data.get("amount", 0.5))
        e._applyBaseDict(data)
        return e

    def params(self) -> dict:
        return {"amount": (self.amount, 0.0, 1.0)}

    def setParam(self, key: str, val: float) -> None:
        if key == "amount": self.amount = val


class VignetteEffect(BaseEffect):
    NAME = "Vignette"

    def __init__(self, intensity: float = 0.5, softness: float = 0.5) -> None:
        super().__init__(self.NAME)
        self.intensity = intensity
        self.softness  = softness

    def apply(self, canvas: skia.Canvas, frame: int) -> None:
        if not self.enabled or self.intensity == 0:
            return
        bounds = canvas.getLocalClipBounds()
        if bounds is None:
            return
        cx = (bounds.left() + bounds.right())  / 2
        cy = (bounds.top()  + bounds.bottom()) / 2
        rx = (bounds.right()  - bounds.left()) / 2
        ry = (bounds.bottom() - bounds.top())  / 2
        r  = math.sqrt(rx * rx + ry * ry)
        inner  = r * (1.0 - self.intensity)
        outer  = r * (1.0 + self.softness * 0.5)
        shader = skia.GradientShader.MakeRadial(
            center=(cx, cy), radius=outer,
            colors=[skia.ColorSetARGB(0, 0, 0, 0),
                    skia.ColorSetARGB(int(self.intensity * 220), 0, 0, 0)],
            positions=[inner / outer, 1.0],
        )
        p = skia.Paint()
        p.setShader(shader)
        p.setBlendMode(skia.BlendMode.kSrcOver)
        canvas.drawPaint(p)

    def toDict(self) -> dict:
        return {**self._baseDict(), "type": "vignette",
                "intensity": self.intensity, "softness": self.softness}

    @classmethod
    def fromDict(cls, data: dict) -> "VignetteEffect":
        e = cls(data.get("intensity", 0.5), data.get("softness", 0.5))
        e._applyBaseDict(data)
        return e

    def params(self) -> dict:
        return {"intensity": (self.intensity, 0.0, 1.0), "softness": (self.softness, 0.0, 1.0)}

    def setParam(self, key: str, val: float) -> None:
        if key == "intensity": self.intensity = val
        elif key == "softness":  self.softness = val


class ChromaKeyEffect(BaseEffect):
    NAME = "Chroma Key"

    def __init__(self, key_r: float = 0.0, key_g: float = 1.0, key_b: float = 0.0,
                 threshold: float = 0.3, softness: float = 0.1) -> None:
        super().__init__(self.NAME)
        self.key_r     = key_r
        self.key_g     = key_g
        self.key_b     = key_b
        self.threshold = threshold
        self.softness  = softness

    def apply(self, canvas: skia.Canvas, frame: int) -> None:
        if not self.enabled:
            return
        sksl = f"""
        uniform shader content;
        half4 main(float2 xy) {{
            half4 c = content.eval(xy);
            half3 key = half3({self.key_r:.3f}, {self.key_g:.3f}, {self.key_b:.3f});
            half dist = distance(c.rgb / max(c.a, 0.001), key);
            half alpha = smoothstep({self.threshold:.3f},
                                    {self.threshold + self.softness:.3f}, dist);
            return half4(c.rgb, c.a * alpha);
        }}
        """
        try:
            result = skia.RuntimeEffect.MakeForShader(sksl)
            if not result.effect:
                return
            surf = canvas.getSurface()
            if surf is None:
                return
            img    = surf.makeImageSnapshot()
            shader = result.effect.makeShader(
                uniforms={},
                children=[img.makeShader(skia.TileMode.kClamp, skia.TileMode.kClamp)],
            )
            p = skia.Paint()
            p.setShader(shader)
            canvas.drawPaint(p)
        except Exception:
            pass

    def toDict(self) -> dict:
        return {**self._baseDict(), "type": "chroma_key",
                "key_r": self.key_r, "key_g": self.key_g, "key_b": self.key_b,
                "threshold": self.threshold, "softness": self.softness}

    @classmethod
    def fromDict(cls, data: dict) -> "ChromaKeyEffect":
        e = cls(data.get("key_r", 0.0), data.get("key_g", 1.0), data.get("key_b", 0.0),
                data.get("threshold", 0.3), data.get("softness", 0.1))
        e._applyBaseDict(data)
        return e

    def params(self) -> dict:
        return {
            "key_r":     (self.key_r,     0.0, 1.0),
            "key_g":     (self.key_g,     0.0, 1.0),
            "key_b":     (self.key_b,     0.0, 1.0),
            "threshold": (self.threshold, 0.0, 1.0),
            "softness":  (self.softness,  0.0, 0.5),
        }

    def setParam(self, key: str, val: float) -> None:
        if   key == "key_r":     self.key_r = val
        elif key == "key_g":     self.key_g = val
        elif key == "key_b":     self.key_b = val
        elif key == "threshold": self.threshold = val
        elif key == "softness":  self.softness = val


EFFECT_REGISTRY: dict[str, type] = {
    "blur":                BlurEffect,
    "brightness_contrast": BrightnessContrastEffect,
    "hsl":                 HSLEffect,
    "color_grade":         ColorGradeEffect,
    "sharpen":             SharpenEffect,
    "vignette":            VignetteEffect,
    "chroma_key":          ChromaKeyEffect,
}

EFFECT_META = [
    {"type": "blur",                "name": "Blur",                 "icon": "◈", "category": "Stylize",  "desc": "Gaussian blur"},
    {"type": "brightness_contrast", "name": "Brightness/Contrast",  "icon": "◑", "category": "Color",    "desc": "Adjust luminance"},
    {"type": "hsl",                 "name": "HSL",                  "icon": "◐", "category": "Color",    "desc": "Hue / Saturation / Lightness"},
    {"type": "color_grade",         "name": "Color Grade",          "icon": "◧", "category": "Color",    "desc": "Temperature & tint"},
    {"type": "sharpen",             "name": "Sharpen",              "icon": "◇", "category": "Stylize",  "desc": "Unsharp mask"},
    {"type": "vignette",            "name": "Vignette",             "icon": "◉", "category": "Cinematic","desc": "Dark edge falloff"},
    {"type": "chroma_key",          "name": "Chroma Key",           "icon": "◫", "category": "Keying",   "desc": "Green / blue screen removal"},
]


def effectFromDict(data: dict) -> BaseEffect:
    cls = EFFECT_REGISTRY.get(data.get("type", ""))
    if cls is None:
        raise ValueError(f"Unknown effect type: {data.get('type')}")
    return cls.fromDict(data)
