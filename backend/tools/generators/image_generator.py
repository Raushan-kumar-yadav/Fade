 
import os
import uuid
import base64
import requests
from pathlib import Path


_GEMINI_IMAGE_MODEL = "gemini-2.0-flash-preview-image-generation"
_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiImageGenerator:
    """
    Sends a text prompt to Gemini and returns generated image(s) saved as PNG files.
    """

    def __init__(self):
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=str(Path(__file__).parents[3] / ".env"))
        self._api_key = os.getenv("GOOGLE_API_KEY", "").strip()
        if not self._api_key:
            raise EnvironmentError(
                "GOOGLE_API_KEY is not set. Add it to your .env file."
            )

    def generate(
        self,
        prompt: str,
        output_dir: str = "",
        num_images: int = 1,
    ) -> list[dict]:
         
        if not output_dir:
            output_dir = str(Path.home() / ".fade" / "generations")
        os.makedirs(output_dir, exist_ok=True)
        num_images = max(1, min(num_images, 4))

        print(f"[GeminiImageGenerator] Generating image — prompt: {prompt[:80]}")

        url = f"{_GEMINI_BASE}/{_GEMINI_IMAGE_MODEL}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "X-goog-api-key": self._api_key,
        }

        # Request both text and image modalities; Gemini will return inline image data
        body = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "responseModalities": ["TEXT", "IMAGE"],
            },
        }

        results = []
        for _ in range(num_images):
            resp = requests.post(url, json=body, headers=headers, timeout=60)
            resp.raise_for_status()
            data = resp.json()

            # Walk the response parts looking for inline image data
            candidates = data.get("candidates", [])
            for candidate in candidates:
                content = candidate.get("content", {})
                for part in content.get("parts", []):
                    inline = part.get("inlineData")
                    if not inline:
                        continue
                    mime = inline.get("mimeType", "image/png")
                    ext = "." + mime.split("/")[-1]  # e.g. ".png"
                    image_bytes = base64.b64decode(inline["data"])

                    filename = f"gemini_{uuid.uuid4().hex[:10]}{ext}"
                    filepath = os.path.join(output_dir, filename)
                    with open(filepath, "wb") as f:
                        f.write(image_bytes)

                    print(f"[GeminiImageGenerator] Saved → {filepath}")
                    results.append({
                        "filepath": filepath,
                        "title": f"AI: {prompt[:50]}",
                    })

        return results
