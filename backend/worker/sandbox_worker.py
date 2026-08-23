"""
sandbox_worker.py — Worker process entry point.

Runs in a completely separate process. Never imports FastAPI, Skia, or any
backend singleton. Communicates only via multiprocessing Queues.

Job schema:
  {"type": "waveform",  "assetId": str, "filepath": str, "bins": int}
  {"type": "whisper",   "assetId": str, "filepath": str, "language": str}  # future
  {"type": "_shutdown"}

Result schema:
  {"type": "waveform_done",  "assetId": str, "peaks": list[float]}
  {"type": "waveform_error", "assetId": str, "message": str}
"""
from __future__ import annotations
import multiprocessing
import struct
import subprocess
import sys


def _do_waveform(filepath: str, bins: int) -> list[float]:
    cmd = [
        "ffmpeg", "-i", filepath,
        "-vn",              # no video
        "-ac", "1",         # mono
        "-ar", "8000",      # 8 kHz — enough for a waveform
        "-f", "s16le",
        "pipe:1",
        "-loglevel", "error",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        raw = result.stdout
    except Exception as e:
        raise RuntimeError(f"ffmpeg failed: {e}") from e

    if not raw:
        return [0.0] * bins

    n = len(raw) // 2
    samples = struct.unpack(f"<{n}h", raw)

    chunk = max(1, n // bins)
    peaks: list[float] = []
    for i in range(0, n, chunk):
        sl = samples[i: i + chunk]
        if not sl:
            break
        rms = (sum(s * s for s in sl) / len(sl)) ** 0.5
        peaks.append(min(1.0, rms / 32768.0))
        if len(peaks) >= bins:
            break

    while len(peaks) < bins:
        peaks.append(0.0)
    return peaks


def worker_main(job_queue: multiprocessing.Queue,
                result_queue: multiprocessing.Queue) -> None:
    """Entry point for the sandboxed worker process."""
    print("[SandboxWorker] started", flush=True)
    while True:
        try:
            job = job_queue.get(timeout=5)
        except Exception:
            continue  # timeout — keep polling

        if job.get("type") == "_shutdown":
            print("[SandboxWorker] shutdown received", flush=True)
            break

        if job.get("type") == "waveform":
            asset_id = job["assetId"]
            filepath  = job["filepath"]
            bins      = job.get("bins", 200)
            try:
                peaks = _do_waveform(filepath, bins)
                result_queue.put({
                    "type":    "waveform_done",
                    "assetId": asset_id,
                    "peaks":   peaks,
                })
            except Exception as e:
                result_queue.put({
                    "type":    "waveform_error",
                    "assetId": asset_id,
                    "message": str(e),
                })
            continue

        # Future: whisper, loudness, scene-detect …
        print(f"[SandboxWorker] unknown job type: {job.get('type')}", flush=True)

    print("[SandboxWorker] exiting", flush=True)
