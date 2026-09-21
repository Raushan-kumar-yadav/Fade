 
from __future__ import annotations
import os
import uuid
import wave
import base64
from pathlib import Path


_GEMINI_TTS_MODEL = "gemini-3.1-flash-tts-preview"

# Supported Gemini voices  
GEMINI_VOICES = [
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede",
    "Callirrhoe", "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba",
    "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar",
    "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi",
    "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat",
]


def _load_env() -> str:
     
    return os.getenv("GOOGLE_API_KEY", "").strip()


def _write_wav(filepath: str, pcm_bytes: bytes,
               channels: int = 1, rate: int = 24000, sample_width: int = 2) -> None:
    with wave.open(filepath, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm_bytes)


# Google Gemini TTS  

class GeminiTTSGenerator:
     

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
            RuntimeError — other API failure
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


 
 
KOKORO_VOICES: dict[str, list[str]] = {
     
    "en-us": [
        "af_heart",      
        "af_alloy",
        "af_aoede",
        "af_bella",
        "af_jessica",
        "af_kore",
        "af_nicole",
        "af_nova",
        "af_river",
        "af_sarah",
        "af_sky",
        "am_adam",
        "am_echo",
        "am_eric",
        "am_fenrir",
        "am_liam",
        "am_michael",
        "am_onyx",
        "am_puck",
        "am_santa",
    ],
     
    "en-gb": [
        "bf_alice",
        "bf_emma",
        "bf_isabella",
        "bf_lily",
        "bm_daniel",
        "bm_fable",
        "bm_george",
        "bm_lewis",
    ],
    # Japanese  (lang_code='j')
    "ja": ["jf_alpha", "jf_gongitsune", "jf_nezuko", "jf_tebukuro", "jm_kumo"],
    # Korean  (lang_code='z')
    "ko": ["zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi",
           "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang"],
    # Spanish  (lang_code='e')
    "es": ["ef_dora", "em_alex", "em_santa"],
    # French  (lang_code='f')
    "fr": ["ff_siwis"],
    # Hindi  (lang_code='h')
    "hi": ["hf_alpha", "hf_beta", "hm_omega", "hm_psi"],
    # Italian  (lang_code='i')
    "it": ["if_sara", "im_nicola"],
    # Portuguese  (lang_code='p')
    "pt": ["pf_dora", "pm_alex", "pm_santa"],
    # Mandarin Chinese  (lang_code='c')
    "zh": ["cf_xiaobei", "cf_xiaoni", "cm_yunxi"],
}

# Flat set for O(1) validation
_ALL_KOKORO_VOICES: set[str] = {v for voices in KOKORO_VOICES.values() for v in voices}

# Voice-name prefix → kokoro-onnx lang code (BCP-47 style)
_VOICE_LANG_MAP: dict[str, str] = {
    "af_": "en-us", "am_": "en-us",   # American English
    "bf_": "en-gb", "bm_": "en-gb",   # British English
    "jf_": "ja", "jm_": "ja",       # Japanese
    "zf_": "ko", "zm_": "ko",       # Korean  
    "ef_": "es", "em_": "es",       # Spanish
    "ff_": "fr", "fm_": "fr",       # French
    "hf_": "hi", "hm_": "hi",       # Hindi
    "if_": "it", "im_": "it",       # Italian
    "pf_": "pt", "pm_": "pt",       # Portuguese
    "cf_": "zh", "cm_": "zh",       # Mandarin Chinese
}


def _voice_to_lang(voice: str) -> str:
    """Infer kokoro-onnx BCP-47 lang code from voice name prefix."""
    return _VOICE_LANG_MAP.get(voice[:3], "en-us")



class KokoroTTSGenerator:
    """
    Local TTS using Kokoro via the `kokoro-onnx` package (Python 3.14 compatible).

    Uses ONNX Runtime — no spacy, no Cython, no GPU required.
    Models (~300MB) are auto-downloaded from HuggingFace on first use.

    Requirements:
        pip install kokoro-onnx soundfile
        Windows: install espeak-ng for phonemization of non-English text:
                 https://github.com/espeak-ng/espeak-ng/releases/download/1.52.0/espeak-ng.msi
    """

    # Lazy-loaded Kokoro ONNX instance  
    _kokoro: object = None
    _model_path: str = ""
    _voices_path: str = ""

    def _get_kokoro(self):
        """Lazy-init the Kokoro ONNX model (auto-downloads on first use)."""
        if self._kokoro is None:
            try:
                from kokoro_onnx import Kokoro
            except ImportError:
                raise ImportError(
                    "kokoro-onnx is not installed.\n"
                    "Run: pip install kokoro-onnx soundfile\n"
                    "  (espeakng-loader is bundled automatically on Windows)\n"
                    "For multilingual support, espeak-ng must also be installed:\n"
                    "  https://github.com/espeak-ng/espeak-ng/releases/download/1.52.0/espeak-ng.msi"
                )

            import urllib.request
             
            import sys as _sys_tts
            _tts_file = Path(__file__)
            if getattr(_sys_tts, 'frozen', False):
                 
                _resource_root = Path(_sys_tts.executable).parent.parent
            else:
                _project_root = _tts_file.parent.parent.parent.parent   
                _resource_root = _project_root
            ai_models_dir = _resource_root / "AIModels" / "kokoro"
            ai_models_dir.mkdir(parents=True, exist_ok=True)

             
             
            _GH_BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1"
            _MODELS = [
                ("kokoro-v1.0.int8.onnx", f"{_GH_BASE}/kokoro-v1.0.int8.onnx"),
                ("voices-v1.0.bin", f"{_GH_BASE}/voices-v1.0.bin"),
            ]

            model_path  = ai_models_dir / "kokoro-v1.0.int8.onnx"
            voices_path = ai_models_dir / "voices-v1.0.bin"

            for fname, url in _MODELS:
                dest = ai_models_dir / fname
                if not dest.exists():
                    # Check old  
                    old_path = Path.home() / ".cache" / "kokoro-onnx" / fname
                    if old_path.exists():
                        print(f"[KokoroTTS] Migrating {fname} from cache to AIModels/...", flush=True)
                        import shutil
                        shutil.copy2(str(old_path), str(dest))
                        print(f"[KokoroTTS] Migration done: {dest}", flush=True)
                        continue
                    size_hint = "~109MB" if "int8" in fname else "~156MB"
                    print(f"[KokoroTTS] Downloading {fname} ({size_hint}) → AIModels/kokoro/ ...", flush=True)
                    try:
                        
                        import subprocess, shutil
                        if shutil.which("curl"):
                            subprocess.run(
                                ["curl", "-L", "--progress-bar", "-o", str(dest), url],
                                check=True,
                            )
                        else:
                            urllib.request.urlretrieve(url, str(dest))
                    except Exception as e:
                        if dest.exists():
                            dest.unlink()    
                        raise RuntimeError(
                            f"Failed to download Kokoro model file: {fname}\n"
                            f"URL: {url}\n"
                            f"Error: {e}\n"
                            f"You can also download it manually and place at: {dest}"
                        )
                    size_mb = dest.stat().st_size // (1024 * 1024)
                    print(f"[KokoroTTS] OK {fname} ({size_mb}MB) saved to AIModels/", flush=True)


            print("[KokoroTTS] Loading ONNX model ...", flush=True)
            kokoro_instance = Kokoro(str(model_path), str(voices_path))

             
             
            import types, numpy as _np
            _orig_create_audio = kokoro_instance._create_audio.__func__

            def _patched_create_audio(self, phonemes, voice, speed):
                 
                speed = float(speed)
                 
                import numpy as np
                from kokoro_onnx import Kokoro as _K
                 
                MAX_PH = 510
                if len(phonemes) > MAX_PH:
                    phonemes = phonemes[:MAX_PH]
                tokens = np.array(self.tokenizer.tokenize(phonemes), dtype=np.int64)
                voice_style = voice[len(tokens)]
                tokens_padded = [[0, *tokens.tolist(), 0]]
                input_names = [i.name for i in self.sess.get_inputs()]
                if "input_ids" in input_names:
                    inputs = {
                        "input_ids": tokens_padded,
                        "style": np.array(voice_style, dtype=np.float32),
                        "speed": np.array([speed], dtype=np.float32),   
                    }
                else:
                    inputs = {
                        "tokens": tokens_padded,
                        "style": voice_style,
                        "speed": np.ones(1, dtype=np.float32) * speed,
                    }
                import time
                SAMPLE_RATE = 24000
                audio = self.sess.run(None, inputs)[0]
                return audio, SAMPLE_RATE

            kokoro_instance._create_audio = types.MethodType(
                _patched_create_audio, kokoro_instance
            )
             

            KokoroTTSGenerator._kokoro = kokoro_instance
            print("[KokoroTTS] Model ready.", flush=True)

        return self._kokoro


    def generate(
        self,
        text: str,
        output_dir: str = "",
        voice: str = "af_heart",
        speed: float = 1.0,
    ) -> dict:
         
        import numpy as np

        # Soft fallback for unknown voice
        if voice not in _ALL_KOKORO_VOICES:
            print(f"[KokoroTTS] Unknown voice '{voice}', falling back to 'af_heart'", flush=True)
            voice = "af_heart"

        if not output_dir:
            output_dir = str(Path.home() / ".fade" / "tts")
        os.makedirs(output_dir, exist_ok=True)

        kokoro = self._get_kokoro()
        lang_code = _voice_to_lang(voice)  # 'a' = English, 'j' = Japanese, etc.

        snippet = text[:80] + ("…" if len(text) > 80 else "")
        print(f"[KokoroTTS] voice={voice} speed={speed} lang={lang_code}  \"{snippet}\"", flush=True)

        try:
            samples, sample_rate = kokoro.create(text, voice=voice, speed=speed, lang=lang_code)
            duration_s = float(len(samples)) / float(sample_rate)
        except Exception as e:
            err = str(e)
            if "espeak" in err.lower() or "phonem" in err.lower():
                raise RuntimeError(
                    "Kokoro needs espeak-ng for phonemization.\n"
                    "Download & install from:\n"
                    "  https://github.com/espeak-ng/espeak-ng/releases/download/1.52.0/espeak-ng.msi\n"
                    f"Then restart Fade.\nOriginal error: {err[:200]}"
                )
            raise RuntimeError(f"Kokoro synthesis failed: {err[:300]}")

        filename = f"kokoro_{voice}_{uuid.uuid4().hex[:8]}.wav"
        filepath = os.path.join(output_dir, filename)

        try:
            import soundfile as sf
            sf.write(filepath, samples, sample_rate)
        except ImportError:
            # Fallback: convert float32 → int16 WAV
            pcm = (np.asarray(samples) * 32767).astype("int16").tobytes()
            _write_wav(filepath, pcm, channels=1, rate=sample_rate, sample_width=2)

        kb = os.path.getsize(filepath) // 1024
        print(f"[KokoroTTS] OK {filepath} ({kb}KB, {duration_s:.1f}s)", flush=True)
        return {
            "filepath":   filepath,
            "title":      f"TTS [{voice}]: {text[:50]}",
            "voice":      voice,
            "duration_s": round(duration_s, 2),
        }

    @staticmethod
    def list_voices(lang: str = "") -> dict:
        """Return voice dict, optionally filtered by language key."""
        if lang:
            return {lang: KOKORO_VOICES.get(lang, [])}
        return KOKORO_VOICES



# ── Local TTS via Ollama (legacy) ─────────────────────────────────────────────

class LocalTTSGenerator:
    """Ollama-based TTS (legacy). Prefer KokoroTTSGenerator for local use."""

    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self._url = ollama_url.rstrip("/")

    def generate(self, text: str, output_dir: str = "", model: str = "kokoro") -> dict:
        import requests

        if not output_dir:
            output_dir = str(Path.home() / ".fade" / "tts")
        os.makedirs(output_dir, exist_ok=True)

        print(f"[LocalTTS] Ollama model={model}, text: {text[:60]}…")

        try:
            r = requests.get(f"{self._url}/api/tags", timeout=3)
            r.raise_for_status()
            models = [m["name"] for m in r.json().get("models", [])]
        except Exception as e:
            raise ConnectionError(f"Ollama not reachable at {self._url}.\nRun: ollama serve\nError: {e}")

        if not any(model in m for m in models):
            raise RuntimeError(
                f"Ollama model '{model}' not installed.\n"
                f"Run: ollama pull {model}\nAvailable: {', '.join(models[:5]) or 'none'}"
            )

        try:
            resp = requests.post(
                f"{self._url}/api/generate",
                json={"model": model, "prompt": text, "stream": False,
                      "options": {"response_format": "audio"}},
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            audio_b64 = data.get("audio") or data.get("response_audio")
            if audio_b64:
                audio_bytes = base64.b64decode(audio_b64)
                filename = f"tts_local_{uuid.uuid4().hex[:10]}.wav"
                filepath = os.path.join(output_dir, filename)
                with open(filepath, "wb") as f:
                    f.write(audio_bytes)
                return {"filepath": filepath, "title": f"TTS: {text[:50]}"}
            return self._espeak_fallback(data.get("response", text), output_dir)
        except requests.HTTPError as e:
            raise RuntimeError(f"Ollama TTS failed: {e.response.status_code} {e.response.text[:200]}")

    def _espeak_fallback(self, text: str, output_dir: str) -> dict:
        import subprocess
        filename = f"tts_espeak_{uuid.uuid4().hex[:10]}.wav"
        filepath = os.path.join(output_dir, filename)
        try:
            subprocess.run(["espeak", "-w", filepath, text],
                           check=True, capture_output=True, timeout=30)
            return {"filepath": filepath, "title": f"TTS: {text[:50]}"}
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            raise RuntimeError(f"espeak fallback failed: {e}")


# Unified factory  

def get_tts_generator(provider: str = "google", ollama_url: str = "http://localhost:11434"):
    """
    Return the appropriate TTS generator.

    provider:
      'google'  → GeminiTTSGenerator  (cloud, needs GOOGLE_API_KEY)
      'kokoro'  → KokoroTTSGenerator  (local, pip install kokoro soundfile)
      'local'   → LocalTTSGenerator   (Ollama-based, legacy)
    """
    if provider == "kokoro":
        return KokoroTTSGenerator()
    if provider == "local":
        return LocalTTSGenerator(ollama_url=ollama_url)
    return GeminiTTSGenerator()
