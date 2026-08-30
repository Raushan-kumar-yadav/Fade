import subprocess
import os
from pathlib import Path


def extractFrame(
    videoPath: str = "",
    output_dir: str = "",
    interval: float = 2.0,
) -> list[tuple[str, float]]:
     
    os.makedirs(output_dir, exist_ok=True)

    cmd = [
        "ffmpeg", "-i", videoPath,
        "-vf", f"fps=1/{interval}",
        "-q:v", "2",
        f"{output_dir}/frame_%04d.jpg",
    ]
    result = subprocess.run(cmd, capture_output=True)

    if result.returncode != 0:
        print(f"[VideoSemantic] ffmpeg error: {result.stderr.decode()}")
        return []

     
    frames = []
    for f in sorted(Path(output_dir).glob("frame_*.jpg")):
        idx = int(f.stem.split("_")[1])          # 1-based
        timestamp = (idx - 1) * interval
        frames.append((str(f), timestamp))

    return frames