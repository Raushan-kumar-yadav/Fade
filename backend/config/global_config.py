 
from __future__ import annotations
import json
import threading
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent / "app_config.json"

_DEFAULTS: dict = {
    "ai": {
        "vision_model":    "moondream:latest",
        "frame_interval":  4.0,
        "whisper_backend": "faster",   # "faster" | "openai"
        "whisper_model":   "small",    # tiny | base | small | medium | large
    },
    "generators": {
        # image  — "google" | "comfyui" | "local" | "stability"
        "image_provider":        "google",
        "image_local_model":     "gemma3:4b",       # ollama model tag
        "comfyui_url":           "http://127.0.0.1:8188",
        "comfyui_path":          "",                # path to ComfyUI folder (contains main.py)
        "comfyui_model":         "v1-5-pruned-emaonly.safetensors",
        "comfyui_width":         512,
        "comfyui_height":        512,
        "comfyui_steps":         20,
        "comfyui_cfg":           7.0,
        # Stability AI
        "stability_model":       "core",            # "core" | "ultra" | "sd3"
        "stability_style":       "",               # "" | "photographic" | "anime" | etc.
        "stability_width":       1024,
        "stability_height":      1024,
        # tts  — "google" | "local"
        "tts_provider":          "google",
        "tts_google_voice":      "Kore",
        "tts_local_model":       "kokoro",
        # video  — "google" | "local"
        "video_provider":        "google",
        "video_local_model":     "wan2.1",
    }
}


class _Config:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        """Load config from disk, merging with defaults."""
        try:
            if _CONFIG_PATH.exists():
                raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            else:
                raw = {}
        except Exception as e:
            print(f"[Config] Failed to read {_CONFIG_PATH}: {e}", flush=True)
            raw = {}

        # Deep-merge defaults → raw (raw wins)
        self._data = _deep_merge(_DEFAULTS, raw)

    def save(self) -> None:
        """Persist current config to disk."""
        try:
            _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                _CONFIG_PATH.write_text(
                    json.dumps(self._data, indent=2), encoding="utf-8"
                )
        except Exception as e:
            print(f"[Config] Failed to save {_CONFIG_PATH}: {e}", flush=True)

    def get(self, dotpath: str, default=None):
        """Get a value by dot-separated path, e.g. 'ai.vision_model'."""
        with self._lock:
            node = self._data
            for key in dotpath.split("."):
                if not isinstance(node, dict) or key not in node:
                    return default
                node = node[key]
            return node

    def set(self, dotpath: str, value) -> None:
        """Set a value by dot-separated path and auto-save."""
        keys = dotpath.split(".")
        with self._lock:
            node = self._data
            for key in keys[:-1]:
                node = node.setdefault(key, {})
            node[keys[-1]] = value
        self.save()
        print(f"[Config] {dotpath} = {value!r}", flush=True)

    def as_dict(self) -> dict:
        with self._lock:
            return json.loads(json.dumps(self._data))  # deep copy


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


# Singleton
cfg = _Config()
