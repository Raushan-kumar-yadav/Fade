 
from __future__ import annotations
import os
import pathlib

# Path to bundled whisper models — centralized in AIModels/
_HERE = pathlib.Path(__file__).parent
_PROJECT_ROOT = _HERE.parent.parent  # backend/ai/ -> backend/ -> Fade/
WHISPER_MODELS_DIR = _PROJECT_ROOT / "AIModels" / "whisper"

DEFAULT_MODEL = os.environ.get("FADE_WHISPER_MODEL", "small")

_model_cache: dict[str, object] = {}


_device_cache: tuple[str, str] | None = None


def _detect_device() -> tuple[str, str]:
    """
    Pick the fastest device+compute_type that ctranslate2 can actually use.
    Runs a real inference probe (not just model load) to confirm cuBLAS loads.
    Cached after first call.
    """
    global _device_cache
    if _device_cache is not None:
        return _device_cache
    try:
        import ctranslate2
        import numpy as np
        cuda_types = ctranslate2.get_supported_compute_types("cuda")
        best = next((ct for ct in ("float16", "int8_float16", "int8") if ct in cuda_types), None)
        if best:
            from faster_whisper import WhisperModel as _WM
            _probe = _WM("tiny", device="cuda", compute_type=best)
            
             
            _silent = np.zeros(16000, dtype=np.float32)  # 1 second silence @ 16kHz
            _segs, _info = _probe.transcribe(_silent, language="en")
            list(_segs)  # consume lazy iterator → triggers cuBLAS GEMM
            del _probe
            print(f"[Whisper] CUDA probe OK — using {best}/cuda", flush=True)
            _device_cache = ("cuda", best)
            return _device_cache
    except Exception as _e:
        print(f"[Whisper] CUDA probe failed ({type(_e).__name__}: {_e}) — using CPU", flush=True)
    _device_cache = ("cpu", "int8")
    return _device_cache


def force_cpu() -> None:
    """Reset device cache to CPU — call when a cuBLAS/CUDA runtime error occurs at inference time."""
    global _device_cache
    _device_cache = ("cpu", "int8")
    # Evict any CUDA-loaded models from cache
    for k in list(_model_cache.keys()):
        _model_cache.pop(k, None)
    print("[Whisper] Forced CPU fallback — model cache cleared", flush=True)


def _load_faster_whisper(model_name: str):
    """Load model via faster-whisper (CTranslate2). Auto-selects GPU when available."""
    device, compute_type = _detect_device()
    from faster_whisper import WhisperModel
    local_path = WHISPER_MODELS_DIR / model_name
    if local_path.exists():
        print(f"[Whisper] faster-whisper: loading from local {local_path} ({device}/{compute_type})", flush=True)
        return WhisperModel(str(local_path), device=device, compute_type=compute_type)
    print(f"[Whisper] faster-whisper: loading '{model_name}' ({device}/{compute_type})", flush=True)
    return WhisperModel(model_name, device=device, compute_type=compute_type)


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
        segments_iter, info = model.transcribe(
            filepath,
            language=language,
            word_timestamps=False,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )
        print(f"[Whisper] Detected language: {info.language} ({info.language_probability:.0%})", flush=True)
        segments = []
        for seg in segments_iter:
            segments.append({
                "start_s": round(seg.start, 3),
                "end_s": round(seg.end, 3),
                "text": seg.text.strip(),
            })
    else:
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


def transcribe_with_words(
    filepath: str,
    model_name: str | None = None,
    language: str | None = None,
    vad: bool = True,
    min_silence_ms: int = 500,
) -> list[dict]:
     
    from backend.config.global_config import cfg
    model_name = model_name or cfg.get("ai.whisper_model", DEFAULT_MODEL)
    model = get_model(model_name)
    backend = getattr(model, "_backend", "openai")

    print(f"[Whisper] Transcribing with word timestamps: {filepath} (backend={backend})", flush=True)

    segments: list[dict] = []

    if backend == "faster":
        segments_iter, info = model.transcribe(
            filepath,
            language=language,
            word_timestamps=True,
            vad_filter=vad,
            vad_parameters={"min_silence_duration_ms": min_silence_ms},
        )
        print(f"[Whisper] Language: {info.language} ({info.language_probability:.0%})", flush=True)
        for seg in segments_iter:
            words = []
            for w in (seg.words or []):
                words.append({
                    "word":    w.word.strip(),
                    "start_s": round(w.start, 3),
                    "end_s":   round(w.end,   3),
                })
            segments.append({
                "start_s": round(seg.start, 3),
                "end_s": round(seg.end,   3),
                "text": seg.text.strip(),
                "words": words,
            })
    else:
        # openai-whisper
        options: dict = {"word_timestamps": True}
        if language:
            options["language"] = language
        result = model.transcribe(filepath, **options)
        for seg in result.get("segments", []):
            words = []
            for w in seg.get("words", []):
                words.append({
                    "word": w.get("word", "").strip(),
                    "start_s": round(w.get("start", seg["start"]), 3),
                    "end_s": round(w.get("end",   seg["end"]),   3),
                })
            segments.append({
                "start_s": round(seg["start"], 3),
                "end_s": round(seg["end"],   3),
                "text": seg["text"].strip(),
                "words": words,
            })

    print(f"[Whisper] Done — {len(segments)} segments, "
          f"{sum(len(s['words']) for s in segments)} words", flush=True)
    return segments


def get_speech_segments(
    filepath: str,
    model_name: str | None = None,
    min_silence_ms: int = 500,
) -> list[dict]:
     
    segs = transcribe(filepath, model_name=model_name)
    return [{"start_s": s["start_s"], "end_s": s["end_s"]} for s in segs if s.get("text")]


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
