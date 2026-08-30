"""
TTS Generator — supports Google Gemini TTS (cloud) and local Kokoro via Ollama.

Provider selection is driven by global_config generators.tts_provider:
  "google" → Gemini 3.1 Flash TTS (gemini-3.1-flash-tts-preview)
  "local"  → Ollama server (model from generators.tts_local_model, e.g. "kokoro")

Output: WAV file saved to output_dir.
"""

from __future__ import annotations
import os
import uuid
import wave
import base64
from pathlib import Path


_GEMINI_TTS_MODEL = "gemini-3.1-flash-tts-preview"

# Supported Gemini voices (30 options from August 2026 docs)
GEMINI_VOICES = [
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede",
    "Callirrhoe", "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba",
    "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar",
    "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi",
    "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat",
]


def _load_env() -> str:
    """Load .env and return GOOGLE_API_KEY."""
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=str(Path(__file__).parents[3] / ".env"))
    return os.getenv("GOOGLE_API_KEY", "").strip()


def _write_wav(filepath: str, pcm_bytes: bytes,
               channels: int = 1, rate: int = 24000, sample_width: int = 2) -> None:
    with wave.open(filepath, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm_bytes)


# ── Google Gemini TTS ─────────────────────────────────────────────────────────

class GeminiTTSGenerator:
    """
    Text-to-speech using the Gemini 3.1 Flash TTS model (August 2026 API).
    Requires GOOGLE_API_KEY with billing enabled.
    """

    def generate(
        self,
        text: str,
        output_dir: str = "",
        voice: str = "Kore",
    ) -> dict:
        """
        Generate speech audio from text.

        Returns: {"filepath": str, "title": str}

        Raises:
            PermissionError  — quota exhausted / billing required
            EnvironmentError — API key not set
            RuntimeError     — other API failure
        """
        api_key = _load_env()
        if not api_key:
            raise EnvironmentError(
                "GOOGLE_API_KEY not set. Add it to your .env file.\n"
                "Get a key at: https://aistudio.google.com/apikey"
            )

        if not output_dir:
            output_dir = str(Path.home() / ".fade" / "tts")
        os.makedirs(output_dir, exist_ok=True)

        if voice not in GEMINI_VOICES:
            voice = "Kore"

        print(f"[GeminiTTS] Generating speech — voice: {voice}, text: {text[:60]}…")

        try:
            from google import genai
        except ImportError:
            raise ImportError("google-genai not installed. Run: pip install google-genai")

        try:
            client = genai.Client(api_key=api_key)
            interaction = client.interactions.create(
                model=_GEMINI_TTS_MODEL,
                input=text,
                response_format={"type": "audio"},
                generation_config={
                    "speech_config": [{"voice": voice}]
                },
            )

            audio_block = interaction.output_audio
            if not audio_block:
                raise RuntimeError("Gemini TTS returned no audio in response.")

            pcm_bytes = base64.b64decode(audio_block.data)
            filename = f"tts_{uuid.uuid4().hex[:10]}.wav"
            filepath = os.path.join(output_dir, filename)
            _write_wav(filepath, pcm_bytes)

            print(f"[GeminiTTS] Saved → {filepath} ({len(pcm_bytes)//1024}KB)")
            return {"filepath": filepath, "title": f"TTS: {text[:50]}"}

        except Exception as e:
            err = str(e)
            if "429" in err or "quota" in err.lower():
                raise PermissionError(
                    "Gemini TTS quota exhausted.\n"
                    "TTS requires a paid Google AI plan.\n"
                    f"→ Enable billing at: https://aistudio.google.com\n"
                    f"Original error: {err[:200]}"
                )
            raise RuntimeError(f"Gemini TTS failed: {err[:300]}")


# ── Local TTS via Ollama ──────────────────────────────────────────────────────

class LocalTTSGenerator:
    """
    Text-to-speech using a locally running Ollama model (e.g. kokoro).

    Ollama TTS models expose a generate endpoint that returns audio bytes
    when the model supports audio output. Falls back to espeak if Ollama
    does not support audio for the selected model.
    """

    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self._url = ollama_url.rstrip("/")

    def generate(
        self,
        text: str,
        output_dir: str = "",
        model: str = "kokoro",
    ) -> dict:
        """
        Generate speech using a local Ollama TTS model.

        Returns: {"filepath": str, "title": str}

        Raises:
            ConnectionError — Ollama not running
            RuntimeError    — model not installed or audio not returned
        """
        import requests

        if not output_dir:
            output_dir = str(Path.home() / ".fade" / "tts")
        os.makedirs(output_dir, exist_ok=True)

        print(f"[LocalTTS] Generating via Ollama model={model}, text: {text[:60]}…")

        # Check Ollama is running
        try:
            r = requests.get(f"{self._url}/api/tags", timeout=3)
            r.raise_for_status()
            models = [m["name"] for m in r.json().get("models", [])]
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
                f"Available models: {', '.join(models[:5]) or 'none'}"
            )

        # Attempt Ollama TTS via generate endpoint (audio-capable models)
        try:
            resp = requests.post(
                f"{self._url}/api/generate",
                json={
                    "model": model,
                    "prompt": text,
                    "stream": False,
                    "options": {"response_format": "audio"},
                },
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()

            # Check if audio was returned (Ollama TTS models return base64 audio)
            audio_b64 = data.get("audio") or data.get("response_audio")
            if audio_b64:
                audio_bytes = base64.b64decode(audio_b64)
                filename = f"tts_local_{uuid.uuid4().hex[:10]}.wav"
                filepath = os.path.join(output_dir, filename)
                # Write raw bytes — may be wav already
                with open(filepath, "wb") as f:
                    f.write(audio_bytes)
                print(f"[LocalTTS] Saved → {filepath}")
                return {"filepath": filepath, "title": f"TTS: {text[:50]}"}

            # Fallback: model returned text, use espeak to synthesize
            spoken_text = data.get("response", text)
            return self._espeak_fallback(spoken_text, output_dir)

        except requests.HTTPError as e:
            raise RuntimeError(f"Ollama TTS request failed: {e.response.status_code} {e.response.text[:200]}")

    def _espeak_fallback(self, text: str, output_dir: str) -> dict:
        """Generate speech using espeak (installed on most Linux/Mac systems)."""
        import subprocess
        filename = f"tts_espeak_{uuid.uuid4().hex[:10]}.wav"
        filepath = os.path.join(output_dir, filename)
        try:
            subprocess.run(
                ["espeak", "-w", filepath, text],
                check=True, capture_output=True, timeout=30
            )
            print(f"[LocalTTS] espeak fallback → {filepath}")
            return {"filepath": filepath, "title": f"TTS: {text[:50]}"}
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            raise RuntimeError(
                f"Local TTS failed: Ollama model did not return audio and espeak is not available.\n"
                f"Install a TTS model in Ollama: ollama pull kokoro\n"
                f"Or install espeak: choco install espeak (Windows)\n"
                f"Error: {e}"
            )


# ── Unified factory ───────────────────────────────────────────────────────────

def get_tts_generator(provider: str = "google", ollama_url: str = "http://localhost:11434"):
    """Return the appropriate TTS generator based on provider setting."""
    if provider == "local":
        return LocalTTSGenerator(ollama_url=ollama_url)
    return GeminiTTSGenerator()
