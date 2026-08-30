import ollama
import base64
import re
from pathlib import Path


VISION_MODEL  = "gemma3:4b"
VISION_PROMPT = (
    "You are analyzing a video frame for a video editing search engine. "
    "Describe the following in 2-3 concise sentences:\n"
    "1. Main subjects and their actions (e.g. 'person running left to right')\n"
    "2. Scene/environment (e.g. 'urban street at night, neon signs')\n"
    "3. Camera angle and mood (e.g. 'low-angle shot, tense atmosphere')\n"
    "Be specific and factual. Do not say 'this image shows' — just describe directly."
)


def describe_frame(frame_path: str) -> str:
    """Send a single frame to Gemma 3 4B via Ollama and return its visual description."""
    with open(frame_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    response = ollama.chat(
        model=VISION_MODEL,
        messages=[{
            "role": "user",
            "content": VISION_PROMPT,
            "images": [img_b64],
        }],
    )
    return response["message"]["content"].strip()


def describe_all_frames(
    frames_dir: str,
    interval: float = 2.0,
) -> list[dict]:
     
    frames_dir = Path(frames_dir)
    frame_files = sorted(frames_dir.glob("frame_*.jpg"))

    results: list[dict] = []
    for frame_file in frame_files:
        # frame_%04d.jpg  
        match = re.search(r"frame_(\d+)\.jpg$", frame_file.name)
        if not match:
            continue

        idx = int(match.group(1))   # 1-based  
        start_sec = (idx - 1) * interval
        end_sec = idx * interval

        try:
            description = describe_frame(str(frame_file))
        except Exception as e:
            description = ""
            print(f"[VideoSemantic] vision failed for {frame_file.name}: {e}")

        if description:
            results.append({
                "text": description,
                "start": start_sec,
                "end": end_sec,
            })

    return results
