"""
SkSL RuntimeEffect system.

Loads .json manifests + .sksl shaders from the sksl/ subdirectory and
executes them via skia.RuntimeShaderBuilder, giving each effect access to
the current canvas pixels as a 'source' uniform shader.

Special multi-pass effects (e.g. DeepGlow) are handled by subclasses.
"""
from __future__ import annotations
import json
import struct
import uuid
from pathlib import Path
from functools import lru_cache

import skia

SKSL_DIR = Path(__file__).parent / "sksl"


# ── Manifest loader ───────────────────────────────────────────────────────────

@lru_cache(maxsize=32)
def _load_manifest(typeId: str) -> dict:
    p = SKSL_DIR / f"{typeId}.json"
    return json.loads(p.read_text(encoding="utf-8"))


@lru_cache(maxsize=32)
def _compile_sksl(typeId: str) -> skia.RuntimeEffect:
    manifest = _load_manifest(typeId)
    sksl_file = SKSL_DIR / manifest["shader"]
    src = sksl_file.read_text(encoding="utf-8")
    effect = skia.RuntimeEffect.MakeForShader(src)
    if effect is None:
        raise RuntimeError(f"SkSL compile failed for '{typeId}'")
    return effect


# ── Param helpers ─────────────────────────────────────────────────────────────

def _default_params(manifest: dict) -> dict:
    out = {}
    for p in manifest.get("params", []):
        out[p["id"]] = p["default"]
    return out


def _param_range(manifest: dict, pid: str) -> tuple:
    for p in manifest.get("params", []):
        if p["id"] == pid:
            mn = p.get("min", 0.0)
            mx = p.get("max", 1.0)
            if isinstance(mn, list):
                return (0.0, 1.0)   # vec — return scalar range for UI
            return (mn, mx)
    return (0.0, 1.0)


def _apply_uniforms(builder: skia.RuntimeShaderBuilder, param_values: dict,
                    manifest: dict, frame: int, fps: float) -> None:
    """Push all param values into the builder, handling vec2/vec4 types."""
    for p in manifest.get("params", []):
        pid  = p["id"]
        ptype = p.get("type", "FloatSlider")
        val  = param_values.get(pid, p.get("default", 0.0))

        if ptype == "FloatSlider" or ptype == "ToggleBool":
            builder.setUniform(pid, float(val))
        elif ptype == "Vec2Input":
            v = val if isinstance(val, list) else [0.0, 0.0]
            builder.setUniform(pid, [float(v[0]), float(v[1])])
        elif ptype == "Vec4Input":
            v = val if isinstance(val, list) else [1.0, 1.0, 1.0, 1.0]
            builder.setUniform(pid, [float(v[0]), float(v[1]), float(v[2]), float(v[3])])

    # Inject time uniforms if the shader declares them
    try:
        builder.setUniform("time", float(frame) / max(fps, 1.0))
    except Exception:
        pass
    try:
        builder.setUniform("frame", float(frame))
    except Exception:
        pass


def _snapshot_as_shader(canvas: skia.Canvas) -> skia.Shader | None:
    surf = canvas.getSurface()
    if surf is None:
        return None
    img = surf.makeImageSnapshot()
    return img.makeShader(skia.TileMode.kClamp, skia.TileMode.kClamp)


# ── Base SkSL Effect ──────────────────────────────────────────────────────────

class SkslEffect:
    def __init__(self, typeId: str) -> None:
        self.effectId    = str(uuid.uuid4())
        self.typeId      = typeId
        self.enabled     = True
        self._manifest   = _load_manifest(typeId)
        self.name        = self._manifest["displayName"]
        self._values     = _default_params(self._manifest)
        self._fps        = 30.0

    def setFps(self, fps: float) -> None:
        self._fps = fps

    def setParam(self, key: str, val) -> None:
        self._values[key] = val

    def apply(self, canvas: skia.Canvas, frame: int) -> None:
        if not self.enabled:
            return
        try:
            effect  = _compile_sksl(self.typeId)
            builder = skia.RuntimeShaderBuilder(effect)
            src     = _snapshot_as_shader(canvas)
            if src:
                builder.setChild("source", src)
            _apply_uniforms(builder, self._values, self._manifest, frame, self._fps)
            shader = builder.makeShader()
            if shader is None:
                return
            paint = skia.Paint()
            paint.setShader(shader)
            canvas.drawPaint(paint)
        except Exception as e:
            print(f"[SkslEffect:{self.typeId}] {e}")

    def params(self) -> dict:
        out = {}
        for p in self._manifest.get("params", []):
            pid   = p["id"]
            ptype = p.get("type", "FloatSlider")
            val   = self._values.get(pid, p.get("default", 0.0))
            mn, mx = _param_range(self._manifest, pid)
            if ptype in ("FloatSlider", "ToggleBool"):
                out[pid] = (float(val), float(mn), float(mx))
            # vec types are exposed as separate scalar channels
            elif ptype == "Vec2Input":
                v = val if isinstance(val, list) else [0.0, 0.0]
                out[f"{pid}_x"] = (float(v[0]), -4000.0, 4000.0)
                out[f"{pid}_y"] = (float(v[1]), -4000.0, 4000.0)
            elif ptype == "Vec4Input":
                v = val if isinstance(val, list) else [1.0, 1.0, 1.0, 1.0]
                out[f"{pid}_r"] = (float(v[0]), 0.0, 1.0)
                out[f"{pid}_g"] = (float(v[1]), 0.0, 1.0)
                out[f"{pid}_b"] = (float(v[2]), 0.0, 1.0)
                out[f"{pid}_a"] = (float(v[3]), 0.0, 1.0)
        return out

    def _resolveVecParam(self, key: str, val) -> None:
        """Handle flattened vec param keys like 'color1_r' → color1[0]."""
        for p in self._manifest.get("params", []):
            pid   = p["id"]
            ptype = p.get("type", "FloatSlider")
            if ptype == "Vec2Input" and key in (f"{pid}_x", f"{pid}_y"):
                cur = list(self._values.get(pid, [0.0, 0.0]))
                idx = 0 if key.endswith("_x") else 1
                cur[idx] = float(val)
                self._values[pid] = cur
                return
            if ptype == "Vec4Input":
                for i, ch in enumerate(("_r", "_g", "_b", "_a")):
                    if key == f"{pid}{ch}":
                        cur = list(self._values.get(pid, [1.0, 1.0, 1.0, 1.0]))
                        cur[i] = float(val)
                        self._values[pid] = cur
                        return

    def toDict(self) -> dict:
        return {
            "effectId": self.effectId,
            "typeId":   self.typeId,
            "name":     self.name,
            "enabled":  self.enabled,
            "type":     f"sksl:{self.typeId}",
            "values":   self._values,
        }

    @classmethod
    def fromDict(cls, data: dict) -> "SkslEffect":
        typeId = data["typeId"]
        e = cls(typeId)
        e.effectId = data.get("effectId", e.effectId)
        e.enabled  = data.get("enabled", True)
        for k, v in data.get("values", {}).items():
            e._values[k] = v
        return e


# ── Deep Glow (3-stage pipeline) ──────────────────────────────────────────────

class DeepGlowEffect(SkslEffect):
    """
    3-stage AE-style Deep Glow:
      Stage 1  threshold extraction  (deep_glow.sksl)
      Stage 2  Gaussian blur         (ImageFilters.Blur)
      Stage 3  composite             (deep_glow_composite.sksl)
    """

    def __init__(self) -> None:
        super().__init__("deep_glow")

    def apply(self, canvas: skia.Canvas, frame: int) -> None:
        if not self.enabled:
            return
        try:
            surf = canvas.getSurface()
            if surf is None:
                return
            w = surf.width()
            h = surf.height()

            # Snapshot original
            orig_img = surf.makeImageSnapshot()
            orig_shader = orig_img.makeShader(skia.TileMode.kClamp, skia.TileMode.kClamp)

            # ── Stage 1: threshold extraction ─────────────────────────
            stage1_surf = skia.Surface(w, h)
            stage1_cv   = stage1_surf.getCanvas()
            stage1_cv.clear(skia.Color4f(0, 0, 0, 0))

            thresh_effect = _compile_sksl("deep_glow")
            thresh_builder = skia.RuntimeShaderBuilder(thresh_effect)
            thresh_builder.setChild("source", orig_shader)
            _apply_uniforms(thresh_builder, self._values, self._manifest, frame, self._fps)
            thresh_shader = thresh_builder.makeShader()
            p1 = skia.Paint(); p1.setShader(thresh_shader)
            stage1_cv.drawPaint(p1)

            # ── Stage 2: blur the threshold result ────────────────────
            radius = float(self._values.get("radius", 40.0))
            blur_filter = skia.ImageFilters.Blur(radius, radius)
            stage2_surf = skia.Surface(w, h)
            stage2_cv   = stage2_surf.getCanvas()
            stage2_cv.clear(skia.Color4f(0, 0, 0, 0))
            blur_paint  = skia.Paint()
            blur_paint.setImageFilter(blur_filter)
            stage2_cv.saveLayer(None, blur_paint)
            stage1_img  = stage1_surf.makeImageSnapshot()
            stage2_cv.drawImage(stage1_img, 0, 0)
            stage2_cv.restore()

            # ── Stage 3: composite blurred glow over original ─────────
            glow_img    = stage2_surf.makeImageSnapshot()
            glow_shader = glow_img.makeShader(skia.TileMode.kClamp, skia.TileMode.kClamp)

            comp_effect  = _compile_sksl("deep_glow_composite")
            comp_builder = skia.RuntimeShaderBuilder(comp_effect)
            comp_builder.setChild("source",   orig_shader)
            comp_builder.setChild("bloom",     glow_shader)

            # Pass through scalar params from deep_glow manifest
            intensity  = float(self._values.get("intensity",  2.0))
            blend_mode = float(self._values.get("blendMode",  0.0))
            opacity    = float(self._values.get("opacity",    1.0))
            try:
                comp_builder.setUniform("intensity",  intensity)
                comp_builder.setUniform("blendMode",  blend_mode)
                comp_builder.setUniform("opacity",    opacity)
            except Exception:
                pass

            comp_shader = comp_builder.makeShader()
            if comp_shader is None:
                return
            final_paint = skia.Paint()
            final_paint.setShader(comp_shader)
            canvas.drawPaint(final_paint)

        except Exception as e:
            print(f"[DeepGlow] {e}")


# ── Registry ──────────────────────────────────────────────────────────────────

def _make_sksl(typeId: str) -> "SkslEffect":
    if typeId == "deep_glow":
        return DeepGlowEffect()
    return SkslEffect(typeId)


SKSL_MANIFEST_IDS = [
    p.stem for p in SKSL_DIR.glob("*.json")
    if json.loads(p.read_text(encoding="utf-8")).get("internal") is not True
]

SKSL_META = []
for mid in sorted(SKSL_MANIFEST_IDS):
    try:
        m = _load_manifest(mid)
        SKSL_META.append({
            "type":        f"sksl:{mid}",
            "name":        m["displayName"],
            "icon":        "◈",
            "category":    m.get("category", "Other"),
            "desc":        f"GPU shader — {m.get('category','')}",
            "isSksl":      True,
        })
    except Exception:
        pass
