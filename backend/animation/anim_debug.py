 
from __future__ import annotations
import math

 
ANIM_DEBUG: bool = False

 
_LOG_EVERY_N: int = 1   


def debug_enabled() -> bool:
    return ANIM_DEBUG


def set_debug(enabled: bool, every_n: int = 1) -> None:
    global ANIM_DEBUG, _LOG_EVERY_N
    ANIM_DEBUG = enabled
    _LOG_EVERY_N = max(1, every_n)
    print(f"[ANIM_DEBUG] {'ENABLED' if enabled else 'DISABLED'} (log every {_LOG_EVERY_N} frame(s))", flush=True)


def should_log(frame: int) -> bool:
    return ANIM_DEBUG and (frame % _LOG_EVERY_N == 0)


def log_evaluate_all(clip_id: str, clip_type: str, timeline_frame: int, local_frame: int) -> None:
    if not ANIM_DEBUG:
        return
    if timeline_frame % _LOG_EVERY_N != 0:
        return
    print(f"[ANIM] evaluateAll  clip={clip_id[:8]}({clip_type})  "
          f"timeline_frame={timeline_frame}  local_frame={local_frame}", flush=True)


def log_property(clip_id: str, prop_name: str, frame: int, value: float,
                 interp_name: str = "", kf_frames: list[int] | None = None) -> None:
    if not ANIM_DEBUG:
        return
    if frame % _LOG_EVERY_N != 0:
        return
    kf_hint = f"  kfs={kf_frames}" if kf_frames else ""
    print(f"[ANIM]   {prop_name:15s}  lf={frame:4d}  val={value:9.4f}  interp={interp_name}{kf_hint}", flush=True)


def log_bezier_segment(prop_name: str, frame: float,
                       p0x: float, p1x: float, p2x: float, p3x: float,
                       p0y: float, p1y: float, p2y: float, p3y: float,
                       u: float, result: float) -> None:
    """Verbose bezier segment log — only when debug is on and every-N matches."""
    if not ANIM_DEBUG:
        return
    if int(frame) % _LOG_EVERY_N != 0:
        return
    linear = p0y + (p3y - p0y) * (frame - p0x) / max(p3x - p0x, 1e-9)
    deviation = result - linear
    print(f"[ANIM]     bezier({prop_name})  f={frame:.0f}  u={u:.4f}  "
          f"result={result:.4f}  linear={linear:.4f}  dev={deviation:+.4f}  "
          f"CP=[{p0x:.0f},{p1x:.1f},{p2x:.1f},{p3x:.0f}]Y=[{p0y:.3f},{p1y:.3f},{p2y:.3f},{p3y:.3f}]",
          flush=True)


# Curve tracer  

def dump_curve_trace(track, prop_name: str = "prop", n_samples: int = 60) -> dict:
     
    kfs = track.keyframes()
    if len(kfs) < 2:
        return {"error": "Need at least 2 keyframes to trace a curve", "keyframes": len(kfs)}

    f_start = kfs[0].frame
    f_end = kfs[-1].frame
    span = max(f_end - f_start, 1)

    samples = []
    max_dev = 0.0
    for i in range(n_samples + 1):
        f = f_start + span * i / n_samples
        val = track.evaluateAt(int(round(f)))
         
        t_norm  = (f - f_start) / span
        lin_val = kfs[0].value + t_norm * (kfs[-1].value - kfs[0].value)
        dev = val - lin_val
        if abs(dev) > abs(max_dev):
            max_dev = dev
        samples.append({
            "frame": round(f, 1),
            "value": round(val, 5),
            "linear": round(lin_val, 5),
            "dev": round(dev, 5),
        })

    # Analyse linearity 
    devs  = [s["dev"] for s in samples]
    is_linear = abs(max_dev) < 0.01 * abs(kfs[-1].value - kfs[0].value + 1e-9)

    keyframe_info = []
    for kf in kfs:
        from backend.animation.keyframe import Interpolation
        keyframe_info.append({
            "frame": kf.frame,
            "value": kf.value,
            "interp": kf.interp.name,
            "handleOutFrame": kf.handleOutFrame,
            "handleOutValue": kf.handleOutValue,
            "handleInFrame": kf.handleInFrame,
            "handleInValue": kf.handleInValue,
            "manualHandles": kf.manualHandles,
        })

    return {
        "prop": prop_name,
        "keyframes": keyframe_info,
        "span_frames":   span,
        "max_deviation": round(max_dev, 5),
        "is_linear": is_linear,
        "verdict": "LINEAR ⚠️ — S-curve not working!" if is_linear else f"CURVED ✅ (max dev={max_dev:+.3f})",
        "samples": samples,
    }
