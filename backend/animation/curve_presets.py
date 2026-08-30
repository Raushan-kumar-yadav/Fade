 
from __future__ import annotations

CURVE_PRESETS: dict[str, dict] = {
    # Built-in interpolation modes
    "linear": {
        "interp": "linear",
        "out_frame_frac":  0.333, "out_value_frac": 0.0,
        "in_frame_frac":  -0.333, "in_value_frac":  0.0,
        "description": "Constant speed from start to end.",
    },
    "constant": {
        "interp": "constant",
        "out_frame_frac": 0.0, "out_value_frac": 0.0,
        "in_frame_frac": 0.0, "in_value_frac":  0.0,
        "description": "Instant jump — holds value until next keyframe.",
    },
    "ease_in": {
        "interp": "ease_in",
        "out_frame_frac": 0.333, "out_value_frac": 0.0,
        "in_frame_frac":  -0.333, "in_value_frac":  0.0,
        "description": "Slow start, fast end. Great for exits.",
    },
    "ease_out": {
        "interp": "ease_out",
        "out_frame_frac":  0.333, "out_value_frac": 0.0,
        "in_frame_frac":  -0.333, "in_value_frac":  0.0,
        "description": "Fast start, slow end. Great for entrances.",
    },
    "ease_both": {
        # Switched to bezier so handles are respected (ease_both interp hardcodes 1/3).
        # 0.45 handles = noticeably sharper S than the default 0.333.
        "interp": "bezier",
        "out_frame_frac":  0.45, "out_value_frac": 0.0,
        "in_frame_frac":  -0.45, "in_value_frac":  0.0,
        "description": "Sharp S-curve. Slow start, fast middle, slow landing.",
    },
    # Bezier custom curves
    "smooth": {
        # 0.48 handles — near-maximum symmetric Bezier (0.5 = control points meet at mid).
        # Noticeably more aggressive S than ease_both.
        "interp": "bezier",
        "out_frame_frac":  0.48, "out_value_frac": 0.0,
        "in_frame_frac":  -0.48, "in_value_frac":  0.0,
        "description": "Very smooth deep S-curve. Holds at extremes, rushes through center.",
    },
    "sharp_s": {
        # Maximum symmetric Bezier S — control points almost touch at the midpoint.
        # Object barely moves for first ~45% of time, then snaps to destination.
        "interp": "bezier",
        "out_frame_frac":  0.48, "out_value_frac": 0.0,
        "in_frame_frac":  -0.48, "in_value_frac":  0.0,
        "description": "Sharpest symmetric S-curve. Maximum slow/fast/slow contrast.",
    },
    "sharp_in": {
        "interp": "bezier",
        "out_frame_frac":  0.05, "out_value_frac": 0.0,
        "in_frame_frac":  -0.5,  "in_value_frac":  0.0,
        "description": "Holds then snaps — very late acceleration.",
    },
    "sharp_out": {
        "interp": "bezier",
        "out_frame_frac":  0.5,  "out_value_frac": 0.0,
        "in_frame_frac":  -0.05, "in_value_frac":  0.0,
        "description": "Fast burst then grinds to a stop.",
    },
    "snap": {
        "interp": "bezier",
        "out_frame_frac":  0.6,  "out_value_frac": 0.0,
        "in_frame_frac":  -0.1,  "in_value_frac":  0.0,
        "description": "Snappy UI feel — very quick ease_out with sharp arrival.",
    },
    "cinematic": {
        "interp": "bezier",
        "out_frame_frac":  0.2,  "out_value_frac": 0.0,
        "in_frame_frac":  -0.65, "in_value_frac":  0.0,
        "description": "Film-like timing — snappy start, very slow cinematic landing.",
    },
    "slow_mo": {
        "interp": "bezier",
        "out_frame_frac":  0.5,  "out_value_frac": 0.0,
        "in_frame_frac":  -0.5,  "in_value_frac":  0.0,
        "description": "Extended S-curve with very long handles. Dreamy slow motion.",
    },
    "overshoot": {
        "interp": "bezier",
        "out_frame_frac":  0.5,  "out_value_frac": 0.0,
        "in_frame_frac":  -0.2,  "in_value_frac":  0.3,
        "description": "Slightly overshoots target then settles. Bouncy feel.",
    },
    "anticipate": {
        "interp": "bezier",
        "out_frame_frac":  0.3,  "out_value_frac": -0.2,
        "in_frame_frac":  -0.3,  "in_value_frac":  0.0,
        "description": "Pulls back before moving forward. Classic cartoon anticipation.",
    },
    "bounce_out": {
        "interp": "bezier",
        "out_frame_frac":  0.4,  "out_value_frac": 0.0,
        "in_frame_frac":  -0.15, "in_value_frac":  0.35,
        "description": "Bounces at end. Good for position drops and UI pop-ins.",
    },
    "elastic_out": {
        "interp": "bezier",
        "out_frame_frac":  0.4,  "out_value_frac": 0.0,
        "in_frame_frac":  -0.1,  "in_value_frac":  0.5,
        "description": "Elastic overshoot at end — spring-like arrival.",
    },
    "elastic_in": {
        "interp": "bezier",
        "out_frame_frac":  0.1,  "out_value_frac": -0.5,
        "in_frame_frac":  -0.4,  "in_value_frac":  0.0,
        "description": "Elastic pull-back at start before launching forward.",
    },
    "fade_in": {
        "interp": "bezier",
        "out_frame_frac":  0.1,  "out_value_frac": 0.0,
        "in_frame_frac":  -0.5,  "in_value_frac":  0.0,
        "description": "Holds near zero then rises quickly. Perfect for opacity.",
    },
    "fade_out": {
        "interp": "bezier",
        "out_frame_frac":  0.5,  "out_value_frac": 0.0,
        "in_frame_frac":  -0.1,  "in_value_frac":  0.0,
        "description": "Drops quickly then levels off to zero. Perfect for fade-outs.",
    },
    "spring": {
        "interp": "bezier",
        "out_frame_frac":  0.6,  "out_value_frac": 0.0,
        "in_frame_frac":  -0.2,  "in_value_frac":  0.4,
        "description": "Spring oscillation — overshoots and wobbles back.",
    },
}


def list_presets() -> list[dict]:
    return [
        {"name": name, "interp": p["interp"], "description": p["description"]}
        for name, p in sorted(CURVE_PRESETS.items())
    ]


_INTERP_MAP = {
    "constant": 0, "linear": 1, "bezier": 2,
    "ease_in": 3, "ease_out": 4, "ease_both": 5,
}


def apply_preset_to_segment(
    preset_name: str,
    seg_frames: float,
    seg_value: float,
    *,
    out_kf,
    in_kf,
) -> None:
     
    from backend.animation.keyframe import Interpolation
    p = CURVE_PRESETS.get(preset_name)
    if p is None:
        names = ", ".join(sorted(CURVE_PRESETS))
        raise ValueError(f"Unknown curve preset '{preset_name}'. Available: {names}")

    interp = Interpolation(_INTERP_MAP.get(p["interp"], 5))

    out_kf.interp = interp
    in_kf.interp  = interp

    # Store computed bezier handles 
    out_kf.handleOutFrame =  p["out_frame_frac"] * max(seg_frames, 1.0)
    out_kf.handleOutValue =  p["out_value_frac"]  * seg_value
    in_kf.handleInFrame =  p["in_frame_frac"]  * max(seg_frames, 1.0)
    in_kf.handleInValue =  p["in_value_frac"]   * seg_value

    # Mark as manually-set 
    out_kf.manualHandles = True
    in_kf.manualHandles  = True