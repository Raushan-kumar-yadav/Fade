 
from __future__ import annotations
import multiprocessing
import sys

 
_AI_FRAME_INTERVAL: float = 4.0   # seconds between sampled frames


#   Waveform  

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

def _do_index_video(asset_id: str, filepath: str, port: int,
                    ffmpeg_exe: str = "",
                    vision_model: str = "",
                    frame_interval: float = 4.0) -> int:
    """
    Full VideoSemantic pipeline — runs inside the sandboxed worker process.
    Vision (Ollama) and Transcription (Whisper) run in parallel.
    Returns number of chunks indexed.
    """
    import tempfile
    import json as _json
    import urllib.request
    from concurrent.futures import ThreadPoolExecutor, Future

    from backend.ai.VideoSemantic.frameExtractor import extractFrame
    from backend.ai.VideoSemantic.descriptions import describe_all_frames
    from backend.ai.VideoSemantic.merger import merge_and_chunk
    from backend.ai.VideoSemantic.indexer import index_video

    print(f"[SandboxWorker] index_video start: {asset_id[:8]} model={vision_model or 'default'} interval={frame_interval}s", flush=True)

    with tempfile.TemporaryDirectory() as tmp_dir:

        #  Extract frames  
        frames = extractFrame(filepath, tmp_dir, frame_interval, ffmpeg_exe=ffmpeg_exe or None)
        if not frames:
            raise RuntimeError("ffmpeg extracted 0 frames")

        #     + Transcription in PARALLEL  
        # Both are independent: vision needs tmp_dir frames, whisper needs filepath.
        print(f"[SandboxWorker] Starting vision + transcription in parallel…", flush=True)

        def _run_vision() -> list[dict]:
            return describe_all_frames(tmp_dir, frame_interval, vision_model=vision_model or None)

        def _run_transcribe() -> list[dict]:
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
                with urllib.request.urlopen(req, timeout=600) as resp:
                    data = _json.loads(resp.read())
                    segs = [
                        {"text": s["text"], "start": s["start"], "end": s["end"]}
                        for s in data.get("segments", [])
                    ]
                    print(f"[SandboxWorker] Transcription done: {len(segs)} segments", flush=True)
                    return segs
            except Exception as e:
                print(f"[SandboxWorker] Transcription skipped (non-fatal): {e}", flush=True)
                return []

        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="VideoIdx") as pool:
            vision_future: Future = pool.submit(_run_vision)
            transcribe_future: Future = pool.submit(_run_transcribe)

            # Block until both complete
            scenes     = vision_future.result()
            transcript = transcribe_future.result()

        print(f"[SandboxWorker] Both done — {len(scenes)} scenes, {len(transcript)} transcript segs", flush=True)

        #   Merge + embed  
        chunks = merge_and_chunk(scenes, transcript, window_sec=4.0)
        count  = index_video(asset_id, chunks)

    print(f"[SandboxWorker] index_video done: {asset_id[:8]} → {count} chunks indexed", flush=True)
    return count


#   Image indexing (vision only, no ffmpeg/whisper)  

def _do_index_image(asset_id: str, filepath: str, vision_model: str = "") -> bool:
    """
    Describe a single image with Ollama and save to ChromaDB.
    No frame extraction or transcription needed.
    """
    from backend.config.global_config import cfg
    from backend.ai.VideoSemantic.descriptions import describe_frame, _get_model
    from backend.ai.VideoSemantic.indexer import index_image

    model = vision_model or _get_model()
    print(f"[SandboxWorker] index_image start: {asset_id[:8]} model={model}", flush=True)

    description = describe_frame(filepath, model)
    if not description:
        print(f"[SandboxWorker] index_image: empty description for {asset_id[:8]}", flush=True)
        return False

    ok = index_image(asset_id, description)
    print(f"[SandboxWorker] index_image done: {asset_id[:8]} → {'saved' if ok else 'skipped'}", flush=True)
    return ok


def worker_main(job_queue: multiprocessing.Queue,
                result_queue: multiprocessing.Queue,
                parent_syspath: list | None = None) -> None:
    """Entry point for the sandboxed worker process."""
     
    if parent_syspath:
        for p in reversed(parent_syspath):
            if p not in sys.path:
                sys.path.insert(0, p)
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
            asset_id     = job["assetId"]
            filepath     = job["filepath"]
            port         = job.get("port", 8000)
            ffmpeg_exe   = job.get("ffmpeg_exe", "")
            vision_model = job.get("vision_model", "")
            frame_interval = float(job.get("frame_interval", 4.0))
            try:
                chunks = _do_index_video(asset_id, filepath, port,
                                         ffmpeg_exe=ffmpeg_exe,
                                         vision_model=vision_model,
                                         frame_interval=frame_interval)
                result_queue.put({"type": "index_video_done", "assetId": asset_id, "chunks": chunks})
            except Exception as e:
                result_queue.put({"type": "index_video_error", "assetId": asset_id, "message": str(e)})
            continue

        if job.get("type") == "index_image":
            asset_id     = job["assetId"]
            filepath     = job["filepath"]
            vision_model = job.get("vision_model", "")
            try:
                ok = _do_index_image(asset_id, filepath, vision_model=vision_model)
                result_queue.put({"type": "index_image_done", "assetId": asset_id, "saved": ok})
            except Exception as e:
                result_queue.put({"type": "index_image_error", "assetId": asset_id, "message": str(e)})
            continue

        print(f"[SandboxWorker] unknown job type: {job.get('type')}", flush=True)

    print("[SandboxWorker] exiting", flush=True)
