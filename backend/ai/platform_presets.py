"""
Social media platform dimension + duration presets.
Used by Director agent when creating compositions for campaigns.
"""

PLATFORMS: dict[str, dict] = {
    "youtube": {
        "label": "YouTube (Landscape)",
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "max_duration_s": 60,
        "aspect": "16:9",
        "notes": "Standard HD landscape. Best for long-form content.",
    },
    "youtube_short": {
        "label":        "YouTube Shorts",
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "max_duration_s": 60,
        "aspect": "9:16",
        "notes": "Vertical short-form, up to 60 seconds.",
    },
    "instagram_post": {
        "label":        "Instagram Post (Square)",
        "width": 1080,
        "height": 1080,
        "fps": 30,
        "max_duration_s": 60,
        "aspect": "1:1",
        "notes": "Square format. Best for feed posts.",
    },
    "instagram_landscape": {
        "label": "Instagram Post (Landscape)",
        "width": 1080,
        "height": 608,
        "fps": 30,
        "max_duration_s": 60,
        "aspect": "1.91:1",
        "notes": "Landscape feed post.",
    },
    "instagram_story": {
        "label": "Instagram Story / Reels",
        "width": 1080,
        "height":       1920,
        "fps": 30,
        "max_duration_s": 90,
        "aspect": "9:16",
        "notes": "Full-screen vertical. Reels up to 90 seconds.",
    },
    "tiktok": {
        "label": "TikTok",
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "max_duration_s": 180,
        "aspect": "9:16",
        "notes": "Vertical video. Up to 3 minutes.",
    },
    "twitter": {
        "label": "Twitter / X",
        "width": 1280,
        "height": 720,
        "fps": 30,
        "max_duration_s": 140,
        "aspect": "16:9",
        "notes": "Landscape. Max 140 seconds for video.",
    },
    "linkedin": {
        "label": "LinkedIn",
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "max_duration_s": 600,
        "aspect": "16:9",
        "notes": "Professional landscape format.",
    },
    "pinterest": {
        "label": "Pinterest",
        "width": 1000,
        "height": 1500,
        "fps": 30,
        "max_duration_s": 15,
        "aspect": "2:3",
        "notes": "Tall portrait. Best for static images.",
    },
    "facebook": {
        "label": "Facebook",
        "width": 1280,
        "height": 720,
        "fps": 30,
        "max_duration_s": 240,
        "aspect": "16:9",
        "notes": "Standard landscape video.",
    },
    "facebook_story": {
        "label": "Facebook Story",
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "max_duration_s": 20,
        "aspect": "9:16",
        "notes": "Vertical story, up to 20 seconds.",
    },
}


# Aliases for common shorthand
PLATFORM_ALIASES = {
    "yt": "youtube",
    "ig": "instagram_post",
    "reel": "instagram_story",
    "reels": "instagram_story",
    "story": "instagram_story",
    "tt": "tiktok",
    "fb": "facebook",
    "tw": "twitter",
    "x": "twitter",
    "short":    "youtube_short",
    "shorts":   "youtube_short",
    "pin": "pinterest",
    "li": "linkedin",
}


def get_preset(platform: str) -> dict | None:
    key = PLATFORM_ALIASES.get(platform.lower(), platform.lower())
    return PLATFORMS.get(key)


def list_presets_summary() -> str:
    lines = ["Available platform presets:"]
    for key, p in PLATFORMS.items():
        lines.append(
            f"  {key:25s} {p['width']}×{p['height']} @ {p['fps']}fps  "
            f"max {p['max_duration_s']}s  ({p['aspect']})"
        )
    return "\n".join(lines)
