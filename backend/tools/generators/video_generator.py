"""
Video Generator — supports Google Veo (cloud) and local Ollama video models.

Provider selection is driven by global_config generators.video_provider:
  "google" → Veo 3.1 via Gemini API (veo-3.1-generate-preview)
  "local"  → Ollama server (model from generators.video_local_model, e.g. "wan2.1")

Output: MP4 file saved to output_dir.
"""

from __future__ import annotations
import os
import uuid
import base64
import time
from pathlib import Path


_VEO_MODEL = "veo-3.1-generate-preview"
_VEO_MODEL_LITE = "veo-3.1-lite-generate-preview"


def _load_env() -> str:
    """Return GOOGLE_API_KEY — .env is loaded at startup by main.py."""
    return os.getenv("GOOGLE_API_KEY", "").strip()


# ── Google Veo Video Generator ────────────────────────────────────────────────

class GeminiVideoGenerator:
    """
    Video generation using Google Veo 3.1 via the Gemini API.
    Uses the long-running operation pattern (predictLongRunning).
    Requires GOOGLE_API_KEY with billing enabled.
    """

    def generate(
        self,
        prompt: str,
        output_dir: str = "",
        duration_seconds: int = 5,
        aspect_ratio: str = "16:9",
        model: str = _VEO_MODEL,
    ) -> dict:
        """
        Generate a video from a text prompt.

        Returns: {"filepath": str, "title": str}

        Raises:
            PermissionError  — quota exhausted / billing required
            EnvironmentError — API key not set
            RuntimeError     — other API failure
        """
        import requests

        api_key = _load_env()
        if not api_key:
            raise EnvironmentError(
                "GOOGLE_API_KEY not set. Add it to your .env file.\n"
                "Get a key at: https://aistudio.google.com/apikey"
            )

        if not output_dir:
            output_dir = str(Path.home() / ".fade" / "generations" / "video")
        os.makedirs(output_dir, exist_ok=True)

        duration_seconds = max(1, min(30, duration_seconds))
        print(f"[GeminiVideo] Generating video — model: {model}, prompt: {prompt[:80]}…")

        headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
        base_url = "https://generativelanguage.googleapis.com/v1beta/models"

        # Submit long-running operation
        try:
            r = requests.post(
                f"{base_url}/{model}:predictLongRunning",
                headers=headers,
                json={
                    "instances": [{"prompt": prompt}],
                    "parameters": {
                        "aspectRatio": aspect_ratio,
                        "durationSeconds": duration_seconds,
                        "outputOptions": {"mimeType": "video/mp4"},
                    }
                },
                timeout=60,
            )
            r.raise_for_status()
            operation = r.json()

        except requests.HTTPError as e:
            err = e.response.text
            if e.response.status_code == 429:
                raise PermissionError(
                    "Veo video generation quota exhausted.\n"
                    "Requires a paid Google AI plan.\n"
                    f"→ Enable billing at: https://aistudio.google.com\n"
                    f"Error: {err[:200]}"
                )
            if e.response.status_code == 404:
                if model != _VEO_MODEL_LITE:
                    print(f"[GeminiVideo] {model} not found, retrying with lite model…")
                    return self.generate(prompt, output_dir, duration_seconds, aspect_ratio, _VEO_MODEL_LITE)
            raise RuntimeError(f"Veo API error {e.response.status_code}: {err[:300]}")

        op_name = operation.get("name", "")
        if not op_name:
            raise RuntimeError(f"Veo did not return an operation name. Response: {operation}")

        print(f"[GeminiVideo] Operation started: {op_name}")

        # Poll until complete (Veo typically takes 30–120s)
        max_wait = 180
        poll_interval = 5
        elapsed = 0

        while elapsed < max_wait:
            time.sleep(poll_interval)
            elapsed += poll_interval

            try:
                poll_r = requests.get(
                    f"https://generativelanguage.googleapis.com/v1beta/{op_name}",
                    headers=headers,
                    timeout=30,
                )
                poll_r.raise_for_status()
                op_status = poll_r.json()
            except Exception as e:
                print(f"[GeminiVideo] Poll error (retrying): {e}")
                continue

            if op_status.get("done"):
                error = op_status.get("error")
                if error:
                    raise RuntimeError(f"Veo generation failed: {error.get('message', str(error))}")

                # Extract video from response
                response = op_status.get("response", {})
                predictions = response.get("predictions", [])
                for pred in predictions:
                    video_b64 = pred.get("bytesBase64Encoded") or pred.get("video", {}).get("bytesBase64Encoded")
                    if video_b64:
                        video_bytes = base64.b64decode(video_b64)
                        filename = f"veo_{uuid.uuid4().hex[:10]}.mp4"
                        filepath = os.path.join(output_dir, filename)
                        with open(filepath, "wb") as f:
                            f.write(video_bytes)
                        print(f"[GeminiVideo] Saved → {filepath} ({len(video_bytes)//1024}KB)")
                        return {"filepath": filepath, "title": f"Video: {prompt[:50]}"}

                raise RuntimeError(f"Veo completed but no video found in response: {op_status}")

            print(f"[GeminiVideo] Waiting… {elapsed}s elapsed")

        raise RuntimeError(f"Veo generation timed out after {max_wait}s.")


# ── Local Video Generator via Ollama ─────────────────────────────────────────

class LocalVideoGenerator:
    """
    Video generation using a local Ollama model (e.g. wan2.1, cogvideox).
    
    Note: Most Ollama video models are experimental. This uses the generate
    endpoint and expects base64-encoded video in the response.
    """

    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self._url = ollama_url.rstrip("/")

    def generate(
        self,
        prompt: str,
        output_dir: str = "",
        model: str = "wan2.1",
        duration_seconds: int = 5,
    ) -> dict:
        """
        Generate a video using a local Ollama model.

        Returns: {"filepath": str, "title": str}
        Raises: ConnectionError, RuntimeError
        """
        import requests

        if not output_dir:
            output_dir = str(Path.home() / ".fade" / "generations" / "video")
        os.makedirs(output_dir, exist_ok=True)

        print(f"[LocalVideo] Generating via Ollama model={model}, prompt: {prompt[:60]}…")

        # Verify Ollama is running
        try:
            tags_r = requests.get(f"{self._url}/api/tags", timeout=3)
            tags_r.raise_for_status()
            models = [m["name"] for m in tags_r.json().get("models", [])]
        except Exception as e:
            raise ConnectionError(
                f"Ollama server not reachable at {self._url}.\n"
                f"Make sure Ollama is running: ollama serve\n"
                f"Error: {e}"
            )

        if not any(model in m for m in models):
            raise RuntimeError(
                f"Ollama model '{model}' is not installed.\n"
                f"Install it with: ollama pull {model}\n"
                f"Available: {', '.join(models[:5]) or 'none'}"
            )

        try:
            resp = requests.post(
                f"{self._url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "duration_seconds": duration_seconds,
                        "response_format": "video",
                    },
                },
                timeout=300,  # video gen is slow locally
            )
            resp.raise_for_status()
            data = resp.json()

            video_b64 = data.get("video") or data.get("response_video")
            if video_b64:
                video_bytes = base64.b64decode(video_b64)
                filename = f"video_local_{uuid.uuid4().hex[:10]}.mp4"
                filepath = os.path.join(output_dir, filename)
                with open(filepath, "wb") as f:
                    f.write(video_bytes)
                print(f"[LocalVideo] Saved → {filepath}")
                return {"filepath": filepath, "title": f"Video: {prompt[:50]}"}

            raise RuntimeError(
                f"Ollama model '{model}' did not return video data.\n"
                f"Make sure the model supports video generation.\n"
                f"Response keys: {list(data.keys())}"
            )

        except requests.HTTPError as e:
            raise RuntimeError(f"Ollama video request failed: {e.response.status_code} {e.response.text[:200]}")


# ── Unified factory ───────────────────────────────────────────────────────────

def get_video_generator(provider: str = "google", ollama_url: str = "http://localhost:11434"):
    """Return the appropriate video generator based on provider setting."""
    if provider == "local":
        return LocalVideoGenerator(ollama_url=ollama_url)
    return GeminiVideoGenerator()
