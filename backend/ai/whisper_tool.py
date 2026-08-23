"""
backend/ai/whisper_tool.py
Whisper transcription using a bundled model directory.
Model files are expected at: backend/ai/whisper_models/<model_name>/
e.g. backend/ai/whisper_models/small/  (contains model.pt etc.)
"""
from __future__ import annotations
import os
import pathlib
from typing import TYPE_CHECKING

# Path to bundled whisper models shipped with the software
_HERE = pathlib.Path(__file__).parent
WHISPER_MODELS_DIR = _HERE / "whisper_models"

# Default model to use
DEFAULT_MODEL = os.environ.get("FADE_WHISPER_MODEL", "small")


def _load_model(model_name: str):
    """Load Whisper model from the bundled software directory."""
    import whisper
    model_path = WHISPER_MODELS_DIR / model_name
    if model_path.exists():
        # Load from local bundled path
        return whisper.load_model(model_name, download_root=str(WHISPER_MODELS_DIR))
    else:
        # Fallback: load from default cache (will download if missing)
        print(f"[Whisper] Bundled model not found at {model_path}, using HuggingFace cache.", flush=True)
        return whisper.load_model(model_name)


_model_cache: dict[str, object] = {}


def get_model(model_name: str = DEFAULT_MODEL):
    """Return a cached Whisper model instance."""
    if model_name not in _model_cache:
        print(f"[Whisper] Loading model '{model_name}'...", flush=True)
        _model_cache[model_name] = _load_model(model_name)
        print(f"[Whisper] Model '{model_name}' ready.", flush=True)
    return _model_cache[model_name]


def transcribe(filepath: str, model_name: str = DEFAULT_MODEL,
               language: str | None = None) -> list[dict]:
    """
    Transcribe audio from a media file.

    Returns a list of segments:
        [{"start_s": float, "end_s": float, "text": str}, ...]
    """
    import whisper
    model = get_model(model_name)

    options = {}
    if language:
        options["language"] = language

    print(f"[Whisper] Transcribing {filepath} ...", flush=True)
    result = model.transcribe(filepath, word_timestamps=False, **options)

    segments = []
    for seg in result.get("segments", []):
        segments.append({
            "start_s":  round(seg["start"], 3),
            "end_s":    round(seg["end"], 3),
            "text":     seg["text"].strip(),
        })

    print(f"[Whisper] Done — {len(segments)} segments", flush=True)
    return segments


def segments_to_srt(segments: list[dict]) -> str:
    """Convert Whisper segments to SRT subtitle format."""
    def fmt(secs: float) -> str:
        h = int(secs // 3600)
        m = int((secs % 3600) // 60)
        s = int(secs % 60)
        ms = int((secs % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for i, seg in enumerate(segments, 1):
        lines.append(str(i))
        lines.append(f"{fmt(seg['start_s'])} --> {fmt(seg['end_s'])}")
        lines.append(seg["text"])
        lines.append("")
    return "\n".join(lines)
