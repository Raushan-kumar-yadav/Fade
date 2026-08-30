import subprocess
import os
import sys
from pathlib import Path


# Candidate ffmpeg directories — checked in order if not on PATH
_FFMPEG_CANDIDATES = [
    str(Path(__file__).resolve().parents[4] / "tools" / "ffmpeg"),  # bundled
    r"D:\ffmpeg\FFmpeg",
    r"C:\ffmpeg\bin",
]


def _find_ffmpeg() -> str:
    """Return the best ffmpeg executable path, checking PATH then known locations."""
    import shutil
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    for d in _FFMPEG_CANDIDATES:
        candidate = os.path.join(d, "ffmpeg.exe") if os.name == "nt" else os.path.join(d, "ffmpeg")
        if os.path.isfile(candidate):
            return candidate
    return "ffmpeg"  # last resort — will fail with a clear error


def extractFrame(
    videoPath: str = "",
    output_dir: str = "",
    interval: float = 2.0,
    ffmpeg_exe: str | None = None,
) -> list[tuple[str, float]]:

    os.makedirs(output_dir, exist_ok=True)

    exe = ffmpeg_exe or _find_ffmpeg()
    print(f"[VideoSemantic] Using ffmpeg: {exe}", flush=True)

    cmd = [
        exe, "-i", videoPath,
        "-vf", f"fps=1/{interval}",
        "-q:v", "2",
        f"{output_dir}/frame_%04d.jpg",
    ]
    result = subprocess.run(cmd, capture_output=True)

    if result.returncode != 0:
        err = result.stderr.decode(errors="replace")[-500:]  # last 500 chars
        print(f"[VideoSemantic] ffmpeg error (rc={result.returncode}): {err}", flush=True)
        return []

    frames = []
    for f in sorted(Path(output_dir).glob("frame_*.jpg")):
        idx = int(f.stem.split("_")[1])          # 1-based
        timestamp = (idx - 1) * interval
        frames.append((str(f), timestamp))

    print(f"[VideoSemantic] Extracted {len(frames)} frames from {os.path.basename(videoPath)}", flush=True)
    return frames