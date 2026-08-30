 
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
        "out_frame_frac":  0.0, "out_value_frac": 0.0,
        "in_frame_frac":   0.0, "in_value_frac":  0.0,
        "description": "Instant jump — holds value until next keyframe.",
    },
    "ease_in": {
        "interp": "ease_in",
        "out_frame_frac":  0.333, "out_value_frac": 0.0,
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
        "interp": "ease_both",
        "out_frame_frac":  0.333, "out_value_frac": 0.0,
        "in_frame_frac":  -0.333, "in_value_frac":  0.0,
        "description": "Slow in AND slow out. Default S-curve. Best for most motion.",
    },
    # Bezier custom curves
    "smooth": {
        "interp": "bezier",
        "out_frame_frac":  0.4,  "out_value_frac": 0.0,
        "in_frame_frac":  -0.4,  "in_value_frac":  0.0,
        "description": "Gentle S-curve. Smoother than ease_both, very natural.",
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
        "out_frame_frac":  0.25, "out_value_frac": 0.0,
        "in_frame_frac":  -0.55, "in_value_frac":  0.0,
        "description": "Film-like timing, ease_out biased. Great for camera moves.",
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