 
from __future__ import annotations
import os
import uuid
from pathlib import Path


# Stable Image API endpoints
_ENDPOINTS = {
    "core":  "https://api.stability.ai/v2beta/stable-image/generate/core",
    "ultra": "https://api.stability.ai/v2beta/stable-image/generate/ultra",
    "sd3":   "https://api.stability.ai/v2beta/stable-image/generate/sd3",
}

# Valid aspect ratios accepted by the v2beta API
_VALID_RATIOS = {
    "1:1", "16:9", "9:16", "4:3", "3:4",
    "21:9", "9:21", "2:3", "3:2",
}


def _best_ratio(width: int, height: int) -> str:
    """Pick the closest supported aspect ratio for given pixel dimensions."""
    target = width / max(height, 1)
    ratios = {
        "1:1": 1.0,  "16:9": 16/9,  "9:16": 9/16,
        "4:3": 4/3,  "3:4": 3/4,   "21:9": 21/9,
        "9:21": 9/21, "2:3": 2/3,  "3:2": 3/2,
    }
    return min(ratios, key=lambda r: abs(ratios[r] - target))


class StabilityImageGenerator:
    """
    Generate images using the Stability AI v2beta API.

    Usage:
        gen = StabilityImageGenerator()
        results = gen.generate("a cat on mars", output_dir="...", num_images=1)
        # returns [{"filepath": "/path/to/image.png", "title": "..."}]
    """

    def __init__(self):
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=str(Path(__file__).parents[3] / ".env"))
        self._api_key = os.getenv("STABILITY_API_KEY", "").strip()
        if not self._api_key:
            raise EnvironmentError(
                "STABILITY_API_KEY is not set.\n"
                "Add it to your .env file:\n"
                "  STABILITY_API_KEY=sk-xxxxxxxx\n"
                "Get a key at: https://platform.stability.ai"
            )

    def generate(
        self,
        prompt: str,
        output_dir: str = "",
        num_images: int = 1,
        model: str = "core",          # "core" | "ultra" | "sd3"
        width: int = 1024,
        height: int = 1024,
        negative_prompt: str = "blurry, low quality, watermark, deformed, ugly",
        style_preset: str = "",        # e.g. "photographic", "anime", "digital-art"
        seed: int = 0,                 # 0 = random
    ) -> list[dict]:
         
        import requests

        if not output_dir:
            output_dir = str(Path.home() / ".fade" / "generations")
        os.makedirs(output_dir, exist_ok=True)

        model = model if model in _ENDPOINTS else "core"
        endpoint = _ENDPOINTS[model]
        aspect_ratio = _best_ratio(width, height)

        num_images = max(1, min(num_images, 10))
        results = []

        for i in range(num_images):
            print(
                f"[Stability] Generating {i+1}/{num_images} — "
                f"model={model}, ratio={aspect_ratio}, prompt={prompt[:60]}…",
                flush=True,
            )

            form: dict = {
                "prompt": (None, prompt),
                "negative_prompt": (None, negative_prompt),
                "aspect_ratio": (None, aspect_ratio),
                "output_format": (None, "png"),
            }
            if seed:
                form["seed"] = (None, str(seed + i))
            if style_preset:
                form["style_preset"] = (None, style_preset)

            try:
                resp = requests.post(
                    endpoint,
                    headers={
                        "authorization": f"Bearer {self._api_key}",
                        "accept": "image/*",
                    },
                    files=form,
                    timeout=120,
                )
            except requests.ConnectionError as e:
                raise RuntimeError(f"Network error calling Stability API: {e}")

            # Handle error responses
            if resp.status_code in (401, 403):
                raise PermissionError(
                    f"Stability AI authentication failed ({resp.status_code}).\n"
                    f"Check your STABILITY_API_KEY in .env.\n"
                    f"Response: {resp.text[:200]}"
                )
            if resp.status_code == 402:
                raise PermissionError(
                    "Stability AI: out of credits.\n"
                    "Top up at: https://platform.stability.ai/account/credits"
                )
            if not resp.ok:
                raise RuntimeError(
                    f"Stability AI API error {resp.status_code}: {resp.text[:300]}"
                )

            # Response body is raw PNG bytes when accept: image/*
            image_bytes = resp.content
            if len(image_bytes) < 1000:
                raise RuntimeError(
                    f"Stability returned unexpectedly small response ({len(image_bytes)} bytes): "
                    f"{image_bytes[:200]}"
                )

            filename = f"stability_{uuid.uuid4().hex[:10]}.png"
            filepath = os.path.join(output_dir, filename)
            with open(filepath, "wb") as f:
                f.write(image_bytes)

            print(
                f"[Stability] Saved → {filepath} ({len(image_bytes) // 1024} KB)",
                flush=True,
            )
            results.append({"filepath": filepath, "title": f"AI: {prompt[:50]}"})

        return results

