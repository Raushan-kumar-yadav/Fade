"""
Gemini Image Generator — updated for August 2026 Interactions API.

Uses:  gemini-3.1-flash-image  (Nano Banana 2 — best versatile image model)
SDK:   google-genai  (pip install google-genai)
Auth:  GOOGLE_API_KEY in .env

Error codes:
  429 → quota exhausted (free tier has 0 image gen quota — needs paid plan)
  404 → model deprecated (old gemini-2.0-flash-exp-image-generation is gone)
"""

import os
import uuid
import base64
from pathlib import Path


_GEMINI_IMAGE_MODEL = "gemini-3.1-flash-image"   # Nano Banana 2
_GEMINI_IMAGE_MODEL_LITE = "gemini-3.1-flash-lite-image"  # cheaper fallback


class GeminiImageGenerator:
    """
    Sends a text prompt to Gemini and returns generated image(s) saved as PNG files.
    Uses the new google-genai Interactions API (August 2026).
    """

    def __init__(self):
         
        self._api_key = os.getenv("GOOGLE_API_KEY", "").strip()
        if not self._api_key:
            raise EnvironmentError(
                "GOOGLE_API_KEY is not set. Add it to your .env file.\n"
                "Get a key at: https://aistudio.google.com/apikey"
            )
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from google import genai
                self._client = genai.Client(api_key=self._api_key)
            except ImportError:
                raise ImportError(
                    "google-genai package not installed.\n"
                    "Run: pip install google-genai"
                )
        return self._client

    def generate(
        self,
        prompt: str,
        output_dir: str = "",
        num_images: int = 1,
        model: str = _GEMINI_IMAGE_MODEL,
    ) -> list[dict]:
        """
        Generate images from a text prompt.

        Returns a list of dicts: [{"filepath": str, "title": str}]

        Raises:
            EnvironmentError   — API key not set
            PermissionError    — quota exhausted (need paid plan for image gen)
            RuntimeError       — any other API failure
        """
        if not output_dir:
            output_dir = str(Path.home() / ".Fade" / "generations")
        os.makedirs(output_dir, exist_ok=True)
        num_images = max(1, min(num_images, 4))

        print(f"[GeminiImageGenerator] Generating image — prompt: {prompt[:80]}")
        print(f"[GeminiImageGenerator] Model: {model}")

        client = self._get_client()
        results = []

        for i in range(num_images):
            try:
                interaction = client.interactions.create(
                    model=model,
                    input=prompt,
                )

                img_block = interaction.output_image
                if not img_block:
                    print(f"[GeminiImageGenerator] WARNING: No image in response #{i+1}")
                    print(f"  Response text: {getattr(interaction, 'output_text', 'N/A')}")
                    continue

                image_bytes = base64.b64decode(img_block.data)
                filename = f"gemini_{uuid.uuid4().hex[:10]}.png"
                filepath = os.path.join(output_dir, filename)
                with open(filepath, "wb") as f:
                    f.write(image_bytes)

                print(f"[GeminiImageGenerator] Saved → {filepath} ({len(image_bytes)//1024}KB)")
                results.append({
                    "filepath": filepath,
                    "title": f"AI: {prompt[:50]}",
                })

            except Exception as e:
                err_str = str(e)

                # Quota / billing errors — give actionable message
                if "429" in err_str or "quota" in err_str.lower() or "rate" in err_str.lower():
                    raise PermissionError(
                        "Gemini image generation quota exhausted.\n"
                        "Image generation requires a paid Google AI plan.\n"
                        "→ Enable billing at: https://aistudio.google.com\n"
                        f"Original error: {err_str[:200]}"
                    )

                # Model not found
                if "404" in err_str or "not found" in err_str.lower():
                    if model != _GEMINI_IMAGE_MODEL_LITE:
                        print(f"[GeminiImageGenerator] Model {model} not found, trying lite model...")
                        return self.generate(prompt, output_dir, num_images, _GEMINI_IMAGE_MODEL_LITE)
                    raise RuntimeError(f"Image model not available: {err_str[:200]}")

                raise RuntimeError(f"Gemini image generation failed: {err_str[:300]}")

        return results
