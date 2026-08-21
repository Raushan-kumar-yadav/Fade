from __future__ import annotations
import subprocess
import struct


def extract_waveform(file_path: str, bins: int = 200) -> list[float]:
    cmd = [
        "ffmpeg", "-i", file_path,
        "-ac", "1", "-ar", "8000",
        "-f", "s16le", "pipe:1",
        "-loglevel", "error",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        raw = result.stdout
    except Exception:
        return [0.0] * bins

    if not raw:
        return [0.0] * bins

    n_samples = len(raw) // 2
    samples   = struct.unpack(f"<{n_samples}h", raw)

    chunk_size = max(1, n_samples // bins)
    peaks: list[float] = []
    for i in range(0, n_samples, chunk_size):
        chunk = samples[i : i + chunk_size]
        if not chunk:
            break
        rms = (sum(s * s for s in chunk) / len(chunk)) ** 0.5
        peaks.append(min(1.0, rms / 32768.0))
        if len(peaks) >= bins:
            break

    while len(peaks) < bins:
        peaks.append(0.0)

    return peaks
