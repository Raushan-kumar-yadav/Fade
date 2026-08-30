 
from __future__ import annotations
import os
import pathlib

# Path to bundled whisper models  
_HERE = pathlib.Path(__file__).parent
WHISPER_MODELS_DIR = _HERE / "whisper_models"

# Default model to use
DEFAULT_MODEL = os.environ.get("FADE_WHISPER_MODEL", "small")

#   Model cache  
_model_cache: dict[str, object] = {}


def _load_faster_whisper(model_name: str):
    """Load model via faster-whisper (CTranslate2, int8, 4-8x faster on CPU)."""
    from faster_whisper import WhisperModel
    local_path = WHISPER_MODELS_DIR / model_name
    if local_path.exists():
        print(f"[Whisper] faster-whisper: loading from local {local_path}", flush=True)
        return WhisperModel(str(local_path), device="cpu", compute_type="int8")
    print(f"[Whisper] faster-whisper: downloading '{model_name}' (int8/cpu)", flush=True)
    return WhisperModel(model_name, device="cpu", compute_type="int8")


def _load_openai_whisper(model_name: str):
    """Fallback: original openai-whisper (slower but always available)."""
    import whisper
    model_path = WHISPER_MODELS_DIR / f"{model_name}.pt"
    if model_path.exists():
        print(f"[Whisper] openai-whisper: loading bundled {model_path}", flush=True)
        return whisper.load_model(model_name, download_root=str(WHISPER_MODELS_DIR))
    print(f"[Whisper] openai-whisper: downloading '{model_name}'", flush=True)
    return whisper.load_model(model_name)


def _load_model(model_name: str):
    from backend.config.global_config import cfg
    backend = cfg.get("ai.whisper_backend", "faster")
    if backend == "faster":
        try:
            model = _load_faster_whisper(model_name)
            model._backend = "faster"
            return model
        except Exception as e:
            print(f"[Whisper] faster-whisper failed ({e}), falling back to openai-whisper", flush=True)
    model = _load_openai_whisper(model_name)
    model._backend = "openai"
    return model


def get_model(model_name: str | None = None):
    """Return a cached Whisper model instance, honouring global_config settings."""
    from backend.config.global_config import cfg
    model_name = model_name or cfg.get("ai.whisper_model", DEFAULT_MODEL)
    if model_name not in _model_cache:
        print(f"[Whisper] Loading model '{model_name}'...", flush=True)
        _model_cache[model_name] = _load_model(model_name)
        backend = getattr(_model_cache[model_name], "_backend", "?")
        print(f"[Whisper] Model '{model_name}' ready (backend={backend}).", flush=True)
    return _model_cache[model_name]


def transcribe(filepath: str, model_name: str | None = None,
               language: str | None = None) -> list[dict]:
    from backend.config.global_config import cfg
    model_name = model_name or cfg.get("ai.whisper_model", DEFAULT_MODEL)

    model = get_model(model_name)
    backend = getattr(model, "_backend", "openai")

    print(f"[Whisper] Transcribing {filepath} (backend={backend})...", flush=True)

    if backend == "faster":
        # faster-whisper API
        segments_iter, info = model.transcribe(
            filepath,
            language=language,
            word_timestamps=False,
            vad_filter=True,           # skip silent parts — extra speedup
            vad_parameters={"min_silence_duration_ms": 500},
        )
        print(f"[Whisper] Detected language: {info.language} ({info.language_probability:.0%})", flush=True)
        segments = []
        for seg in segments_iter:
            segments.append({
                "start_s": round(seg.start, 3),
                "end_s":   round(seg.end, 3),
                "text":    seg.text.strip(),
            })
    else:
        # openai-whisper API
        options = {}
        if language:
            options["language"] = language
        result = model.transcribe(filepath, word_timestamps=False, **options)
        segments = []
        for seg in result.get("segments", []):
            segments.append({
                "start_s": round(seg["start"], 3),
                "end_s": round(seg["end"], 3),
                "text": seg["text"].strip(),
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
