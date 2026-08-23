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
    """Extract audio waveform peaks using PyAV (no external ffmpeg needed)."""
    try:
        import av
        import numpy as np
        has_numpy = True
    except ImportError:
        has_numpy = False

    try:
        import av
        container = av.open(filepath)
        audio_stream = next((s for s in container.streams if s.type == 'audio'), None)
        if audio_stream is None:
            container.close()
            return [0.0] * bins

        samples_list: list[float] = []

        for packet in container.demux(audio_stream):
            for frame in packet.decode():
                # Convert to mono float32
                arr = frame.to_ndarray()  # shape: (channels, samples)
                mono = arr.mean(axis=0) if arr.ndim > 1 else arr
                # Normalize to -1..1 based on format
                if frame.format.name in ('s16', 's16p'):
                    mono = mono.astype(float) / 32768.0
                elif frame.format.name in ('s32', 's32p'):
                    mono = mono.astype(float) / 2147483648.0
                elif frame.format.name in ('fltp', 'flt'):
                    mono = mono.astype(float)
                else:
                    mono = mono.astype(float) / 32768.0
                samples_list.extend(mono.tolist())

        container.close()

        if not samples_list:
            return [0.0] * bins

        # Chunk into bins and compute RMS peak per bin
        n = len(samples_list)
        chunk = max(1, n // bins)
        peaks: list[float] = []
        for i in range(0, n, chunk):
            sl = samples_list[i: i + chunk]
            if not sl:
                break
            rms = (sum(s * s for s in sl) / len(sl)) ** 0.5
            peaks.append(min(1.0, rms))
            if len(peaks) >= bins:
                break

        while len(peaks) < bins:
            peaks.append(0.0)
        return peaks

    except Exception as e:
        raise RuntimeError(f"PyAV waveform failed: {e}") from e


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
