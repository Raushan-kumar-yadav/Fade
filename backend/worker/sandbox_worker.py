"""
sandbox_worker.py — Worker process entry point.

Runs in a completely separate process. Never imports FastAPI, Skia, or any
backend singleton. Communicates only via multiprocessing Queues.

Job schema:
  {"type": "waveform",     "assetId": str, "filepath": str, "bins": int}
  {"type": "index_video",  "assetId": str, "filepath": str, "port": int}
  {"type": "_shutdown"}

Result schema:
  {"type": "waveform_done",     "assetId": str, "peaks": list[float]}
  {"type": "waveform_error",    "assetId": str, "message": str}
  {"type": "index_video_done",  "assetId": str, "chunks": int}
  {"type": "index_video_error", "assetId": str, "message": str}
"""
from __future__ import annotations
import multiprocessing
import sys


# ── Waveform ─────────────────────────────────────────────────────────────────

def _do_waveform(filepath: str, bins: int) -> list[float]:
    """Extract audio waveform peaks using PyAV (no external ffmpeg needed)."""
    try:
        import av
        import numpy as np
    except ImportError:
        raise RuntimeError("PyAV / numpy not installed")

    container = av.open(filepath)
    audio_stream = next((s for s in container.streams if s.type == 'audio'), None)
    if audio_stream is None:
        container.close()
        return [0.0] * bins

    samples_list: list[float] = []
    for packet in container.demux(audio_stream):
        for frame in packet.decode():
            arr = frame.to_ndarray()
            mono = arr.mean(axis=0) if arr.ndim > 1 else arr
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


#   VideoSemantic indexing  

def _do_index_video(asset_id: str, filepath: str, port: int) -> int:
    """
    Full VideoSemantic pipeline — runs inside the sandboxed worker process.
    Returns number of chunks indexed.
    """
    import tempfile
    import json as _json
    import urllib.request

    from backend.ai.VideoSemantic.frameExtractor import extractFrame
    from backend.ai.VideoSemantic.descriptions import describe_all_frames
    from backend.ai.VideoSemantic.merger import merge_and_chunk
    from backend.ai.VideoSemantic.indexer import index_video

    INTERVAL = 2.0

    with tempfile.TemporaryDirectory() as tmp_dir:
        #   Extract frames
        frames = extractFrame(filepath, tmp_dir, INTERVAL)
        if not frames:
            raise RuntimeError("ffmpeg extracted 0 frames")

        # Vision descriptions  
        scenes = describe_all_frames(tmp_dir, INTERVAL)

        #   Transcript via existing /ai/transcribe HTTP endpoint
        transcript: list[dict] = []
        try:
            body = _json.dumps({
                "assetId": asset_id,
                "model": "small",
                "create_text_clips": False,
            }).encode()
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/ai/transcribe",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = _json.loads(resp.read())
                transcript = [
                    {"text": s["text"], "start": s["start"], "end": s["end"]}
                    for s in data.get("segments", [])
                ]
        except Exception as _e:
            print(f"[SandboxWorker] transcribe skipped (non-fatal): {_e}", flush=True)

        # Merge scenes 
        chunks = merge_and_chunk(scenes, transcript, window_sec=4.0)

        #   Embed and store in ChromaDB
        count = index_video(asset_id, chunks)

    return count


#   Main loop  

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
            filepath = job["filepath"]
            bins = job.get("bins", 200)
            try:
                peaks = _do_waveform(filepath, bins)
                result_queue.put({"type": "waveform_done", "assetId": asset_id, "peaks": peaks})
            except Exception as e:
                result_queue.put({"type": "waveform_error", "assetId": asset_id, "message": str(e)})
            continue

        if job.get("type") == "index_video":
            asset_id = job["assetId"]
            filepath = job["filepath"]
            port = job.get("port", 8000)
            try:
                chunks = _do_index_video(asset_id, filepath, port)
                result_queue.put({"type": "index_video_done", "assetId": asset_id, "chunks": chunks})
            except Exception as e:
                result_queue.put({"type": "index_video_error", "assetId": asset_id, "message": str(e)})
            continue

        print(f"[SandboxWorker] unknown job type: {job.get('type')}", flush=True)

    print("[SandboxWorker] exiting", flush=True)
