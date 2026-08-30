import ollama
import base64
import re
from pathlib import Path

# Fallback priority when the configured model isn't installed
_MODEL_PRIORITY = ["moondream:latest", "moondream", "moondream2", "gemma3:4b", "llava", "llava-phi3"]

VISION_PROMPT = (
    "Directly describe this video frame in 2 sentences. "
    "Do NOT write introductions, headers, bold text, or bullet points. "
    "Just output plain text. Cover: "
    "(1) what subjects are doing, "
    "(2) the scene/environment, "
    "(3) camera angle and mood."
)


def _get_model(override: str | None = None) -> str:
    """
    Return the vision model to use.
    Priority: override arg → global_config → fallback priority list → first available.
    Both main process and worker read from the same config file on disk.
    """
    from backend.config.global_config import cfg
    chosen = override or cfg.get("ai.vision_model", "moondream:latest")

    try:
        models = [m.model for m in ollama.list().models]
        print(f"[VideoSemantic] Ollama models available: {models}", flush=True)

        if chosen in models:
            print(f"[VideoSemantic] Using model: {chosen}", flush=True)
            return chosen

        # Chosen model not installed — warn and fall back
        print(f"[VideoSemantic] Configured model {chosen!r} not found, trying fallbacks…", flush=True)
        for preferred in _MODEL_PRIORITY:
            if preferred in models:
                print(f"[VideoSemantic] Falling back to: {preferred}", flush=True)
                return preferred

        if models:
            print(f"[VideoSemantic] Using first available: {models[0]}", flush=True)
            return models[0]

    except Exception as e:
        print(f"[VideoSemantic] Could not list Ollama models: {e}", flush=True)

    return chosen



def describe_frame(frame_path: str, model: str) -> str:
    """Send a single frame to the vision model via Ollama and return its description."""
    with open(frame_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    response = ollama.chat(
        model=model,
        messages=[{
            "role": "user",
            "content": VISION_PROMPT,
            "images": [img_b64],
        }],
    )
    msg = response.message if hasattr(response, "message") else response["message"]
    content = msg.content if hasattr(msg, "content") else msg["content"]
    return content.strip()


def describe_all_frames(
    frames_dir: str,
    interval: float = 2.0,
    vision_model: str | None = None,
) -> list[dict]:
    frames_dir = Path(frames_dir)
    frame_files = sorted(frames_dir.glob("frame_*.jpg"))
    total = len(frame_files)

    model = _get_model(override=vision_model)
    print(f"[VideoSemantic] Describing {total} frames with model={model}", flush=True)

    results: list[dict] = []
    for i, frame_file in enumerate(frame_files, 1):
        match = re.search(r"frame_(\d+)\.jpg$", frame_file.name)
        if not match:
            continue

        idx = int(match.group(1))   # 1-based
        start_sec = (idx - 1) * interval
        end_sec = idx * interval

        try:
            description = describe_frame(str(frame_file), model)
            print(f"[VideoSemantic] [{i}/{total}] t={start_sec:.0f}s → {description[:80]}...", flush=True)
        except Exception as e:
            description = ""
            print(f"[VideoSemantic] [{i}/{total}] vision FAILED for {frame_file.name}: {e}", flush=True)

        if description:
            results.append({
                "text":  description,
                "start": start_sec,
                "end":   end_sec,
            })

    print(f"[VideoSemantic] Described {len(results)}/{total} frames successfully", flush=True)
    return results
