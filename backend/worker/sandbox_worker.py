 
from __future__ import annotations
import multiprocessing
import sys

 
_AI_FRAME_INTERVAL: float = 4.0    


class _IndexCancelled(Exception):
    """Raised inside the sandbox when the user cancels an indexing job."""


#   Waveform  

def _do_waveform(filepath: str, bins: int) -> list[float]:
     
    try:
        import av
        import math
    except ImportError:
        raise RuntimeError("PyAV not installed")

    container = av.open(filepath)
    audio_stream = next((s for s in container.streams if s.type == "audio"), None)
    if audio_stream is None:
        container.close()
        return [0.0] * bins

 
    duration_sec: float = 0.0
    if audio_stream.duration and audio_stream.time_base:
        duration_sec = float(audio_stream.duration) * float(audio_stream.time_base)
    elif container.duration:
        duration_sec = container.duration / 1_000_000.0  

    sample_rate = audio_stream.sample_rate or 44100
    total_samples_est = max(1, int(duration_sec * sample_rate))
    samples_per_bin = max(1, total_samples_est // bins)

    #   Single-pass streaming accumulator  
    bin_sum_sq = 0.0    
    bin_count  = 0     # samples in current bin
    peaks: list[float] = []
    total_seen = 0

    for packet in container.demux(audio_stream):
        if len(peaks) >= bins:
            break
        for frame in packet.decode():
            arr = frame.to_ndarray()
            # Collapse to mono float
            if arr.ndim > 1:
                mono = arr.mean(axis=0)
            else:
                mono = arr
            fmt = frame.format.name
            if fmt in ("s16", "s16p"):
                mono = mono.astype(float) / 32768.0
            elif fmt in ("s32", "s32p"):
                mono = mono.astype(float) / 2_147_483_648.0
            else:
                mono = mono.astype(float)

            # Feed samples into the bin accumulator
            for sample in mono:
                bin_sum_sq += float(sample) * float(sample)
                bin_count  += 1
                total_seen += 1

                if bin_count >= samples_per_bin:
                    rms = math.sqrt(bin_sum_sq / bin_count)
                    peaks.append(min(1.0, rms))
                    bin_sum_sq = 0.0
                    bin_count  = 0
                    if len(peaks) >= bins:
                        break

    container.close()

    # Flush the last partial bin
    if bin_count > 0 and len(peaks) < bins:
        rms = math.sqrt(bin_sum_sq / bin_count)
        peaks.append(min(1.0, rms))

    # Pad to exactly `bins` values
    while len(peaks) < bins:
        peaks.append(0.0)

    return peaks[:bins]




#   VideoSemantic indexing  

def _do_index_video(asset_id: str, filepath: str, port: int,
                    ffmpeg_exe: str = "",
                    vision_model: str = "",
                    frame_interval: float = 4.0,
                    result_queue=None,
                    cancel_queue=None) -> int:
     
    import tempfile
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

        # ── Cancel check: before heavy vision work ──────────────────────────────
        def _is_cancelled() -> bool:
            """Drain cancel_queue and check if our asset_id was cancelled."""
            if cancel_queue is None:
                return False
            cancelled_ids: set[str] = set()
            while True:
                try:
                    cancelled_ids.add(cancel_queue.get_nowait())
                except Exception:
                    break
            # Put others back (only ours matters right now)
            for cid in cancelled_ids:
                if cid != asset_id:
                    try:
                        cancel_queue.put_nowait(cid)
                    except Exception:
                        pass
            return asset_id in cancelled_ids

        if _is_cancelled():
            raise _IndexCancelled(f"Indexing cancelled before vision phase: {asset_id[:8]}")

      
        print(f"[SandboxWorker] Starting vision + transcription in parallel…", flush=True)

        def _run_vision() -> list[dict]:
            """Describe frames one-by-one, checking for cancellation between each."""
            import os as _os
            from backend.ai.VideoSemantic.descriptions import describe_frame, _get_model
            model = vision_model or _get_model()
            results: list[dict] = []
            frame_files = sorted(
                f for f in _os.listdir(tmp_dir)
                if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
            )
            for i, fname in enumerate(frame_files):
                # Cancel check between every frame
                if _is_cancelled():
                    print(f"[SandboxWorker] Vision cancelled at frame {i}/{len(frame_files)} for {asset_id[:8]}", flush=True)
                    raise _IndexCancelled("Vision cancelled mid-frame")
                fpath = _os.path.join(tmp_dir, fname)
                # Compute approximate timestamp from filename or index
                try:
                    ts = float(fname.replace(".jpg","").replace(".jpeg","").replace(".png","").replace(".webp","").split("_")[-1])
                except Exception:
                    ts = i * frame_interval
                desc = describe_frame(fpath, model)
                if desc:
                    results.append({"text": desc, "start": ts, "end": ts + frame_interval})
            return results

        def _run_transcribe() -> list[dict]:
            import traceback
            import backend.ai.whisper_tool as _wt
            from backend.config.global_config import cfg
            model_name = cfg.get("ai.whisper_model", "small")
            try:
                device, compute_type = _wt._detect_device()
                print(f"[Whisper][Worker] Device selected: {device}/{compute_type}", flush=True)
                print(f"[Whisper][Worker] Loading model '{model_name}' on {device}…", flush=True)
                _wt.get_model(model_name)  # warm-up / log
                print(f"[Whisper][Worker] Model ready — transcribing {filepath}", flush=True)
                try:
                    raw = _wt.transcribe(filepath, model_name=model_name, language=None)
                except RuntimeError as cuda_err:
                    _cuda_kw = ("cublas", "cufft", "cudnn", "cusolver", ".dll", "cuda")
                    if any(kw in str(cuda_err).lower() for kw in _cuda_kw):
                        print(f"[Whisper][Worker] CUDA runtime error — falling back to CPU and retrying", flush=True)
                        _wt.force_cpu()   # clears cache 
                        raw = _wt.transcribe(filepath, model_name=model_name, language=None)
                    else:
                        raise
                segs = [
                    {"text": s["text"], "start": s["start_s"], "end": s["end_s"]}
                    for s in raw if s.get("text", "").strip()
                ]
                print(f"[Whisper][Worker] Transcription done: {len(segs)} segments", flush=True)
                return segs
            except Exception as e:
                print(f"[Whisper][Worker] FAILED — {type(e).__name__}: {e}", flush=True)
                traceback.print_exc()
                return []

        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="VideoIdx") as pool:
            vision_future:     Future = pool.submit(_run_vision)
            transcribe_future: Future = pool.submit(_run_transcribe)

            # vision done  
            scenes = vision_future.result()
            vision_chunks = merge_and_chunk(scenes, [], window_sec=4.0)
            count = index_video(asset_id, vision_chunks)
            print(f"[SandboxWorker] Phase 1 done — {count} vision chunks saved (searchable, transcript pending…)", flush=True)
            if result_queue is not None:
                result_queue.put({"type": "index_video_phase1", "assetId": asset_id, "chunks": count})

            #  whisper done 
            print(f"[SandboxWorker] Waiting for Whisper transcript…", flush=True)
            transcript = transcribe_future.result()
            from backend.worker import transcript_status as _ts
            if transcript:
                enriched_chunks = merge_and_chunk(scenes, transcript, window_sec=4.0)
                count = index_video(asset_id, enriched_chunks)
                _ts.mark_done(asset_id)
                print(
                    f"[SandboxWorker] Phase 2 done — {count} enriched chunks (vision+speech) saved",
                    flush=True,
                )
            else:
                _ts.mark_failed(asset_id)
                print(f"[SandboxWorker] Phase 2: transcript failed — vision-only kept, marked for retry", flush=True)

    print(f"[SandboxWorker] index_video done: {asset_id[:8]} → {count} chunks indexed", flush=True)
    return count


def _do_transcribe_only(asset_id: str, filepath: str) -> int:
     
    import traceback
    from backend.ai.VideoSemantic.indexer import index_video, get_db_path, _col
    from backend.ai.VideoSemantic.merger import merge_and_chunk
    from backend.worker import transcript_status as _ts

    print(f"[SandboxWorker] transcribe_only start: {asset_id[:8]}", flush=True)

    #   Rebuild scenes list    
    try:
        col = _col
        existing = col.get(where={"assetId": asset_id}, include=["documents", "metadatas"])
        scenes = []
        for doc, meta in zip(existing["documents"], existing["metadatas"]):
            # Strip "Visual: " prefix to get raw vision text
            vis_text = doc.replace("Visual: ", "").split(" | Speech:")[0].strip()
            scenes.append({
                "text": vis_text,
                "start": float(meta.get("start_sec", 0)),
                "end": float(meta.get("end_sec", 4)),
            })
        scenes.sort(key=lambda s: s["start"])
        print(f"[SandboxWorker] transcribe_only: loaded {len(scenes)} existing vision chunks", flush=True)
    except Exception as e:
        print(f"[SandboxWorker] transcribe_only: failed to load scenes ({e})", flush=True)
        return 0

    #   Run Whisper  
    import backend.ai.whisper_tool as _wt
    from backend.config.global_config import cfg
    model_name = cfg.get("ai.whisper_model", "small")
    try:
        device, compute_type = _wt._detect_device()
        print(f"[Whisper][Worker] Device: {device}/{compute_type}  model: {model_name}", flush=True)
        _wt.get_model(model_name)
        print(f"[Whisper][Worker] Transcribing {filepath}", flush=True)
        try:
            raw = _wt.transcribe(filepath, model_name=model_name, language=None)
        except RuntimeError as cuda_err:
            if any(kw in str(cuda_err).lower() for kw in ("cublas", "cufft", "cudnn", ".dll", "cuda")):
                print(f"[Whisper][Worker] CUDA error — CPU fallback", flush=True)
                _wt.force_cpu()
                raw = _wt.transcribe(filepath, model_name=model_name, language=None)
            else:
                raise
        transcript = [
            {"text": s["text"], "start": s["start_s"], "end": s["end_s"]}
            for s in raw if s.get("text", "").strip()
        ]
        print(f"[Whisper][Worker] Done: {len(transcript)} segments", flush=True)
    except Exception as e:
        print(f"[Whisper][Worker] FAILED — {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        _ts.mark_failed(asset_id)
        return 0

    if not transcript:
        _ts.mark_failed(asset_id)
        return 0

    enriched = merge_and_chunk(scenes, transcript, window_sec=4.0)
    count = index_video(asset_id, enriched)
    _ts.mark_done(asset_id)
    print(f"[SandboxWorker] transcribe_only done: {asset_id[:8]} → {count} enriched chunks", flush=True)
    return count


#   Audio-only transcription  

def _do_transcribe_audio(asset_id: str, filepath: str) -> int:
     
    import traceback
    from backend.ai.VideoSemantic.indexer import _col, _embedder
    from backend.worker import transcript_status as _ts

    print(f"[SandboxWorker] transcribe_audio start: {asset_id[:8]} | {filepath}", flush=True)

    import backend.ai.whisper_tool as _wt
    from backend.config.global_config import cfg
    model_name = cfg.get("ai.whisper_model", "small")
    try:
        device, compute_type = _wt._detect_device()
        print(f"[Whisper][Audio] Device: {device}/{compute_type}  model: {model_name}", flush=True)
        _wt.get_model(model_name)
        try:
            raw = _wt.transcribe(filepath, model_name=model_name, language=None)
        except RuntimeError as cuda_err:
            if any(kw in str(cuda_err).lower() for kw in ("cublas", "cufft", "cudnn", ".dll", "cuda")):
                print("[Whisper][Audio] CUDA error — CPU fallback", flush=True)
                _wt.force_cpu()
                raw = _wt.transcribe(filepath, model_name=model_name, language=None)
            else:
                raise
        segments = [
            {"text": s["text"], "start": s["start_s"], "end": s["end_s"]}
            for s in raw if s.get("text", "").strip()
        ]
        print(f"[Whisper][Audio] Done: {len(segments)} segments for {asset_id[:8]}", flush=True)
    except Exception as e:
        print(f"[Whisper][Audio] FAILED — {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        _ts.mark_failed(asset_id)
        return 0

    if not segments:
        _ts.mark_failed(asset_id)
        print(f"[SandboxWorker] transcribe_audio: 0 segments (silence?) for {asset_id[:8]}", flush=True)
        return 0

    # Save to ChromaDB video_segments  
    texts = [f"Speech: {s['text']}" for s in segments]
    embeddings = _embedder.encode(texts).tolist()
    ids = [f"{asset_id}__audio__{i}" for i in range(len(segments))]
    metadatas = [
        {
            "assetId": asset_id,
            "start_sec": float(s["start"]),
            "end_sec": float(s["end"]),
            "asset_type": "audio",
        }
        for s in segments
    ]
    _col.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
    _ts.mark_done(asset_id)
    print(f"[SandboxWorker] transcribe_audio done: {asset_id[:8]} → {len(segments)} segments in ChromaDB", flush=True)
    return len(segments)


#   Image indexing  

def _do_index_image(asset_id: str, filepath: str, vision_model: str = "") -> bool:
     
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
                cancel_queue: multiprocessing.Queue,
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
            asset_id = job["assetId"]
            filepath = job["filepath"]
            port = job.get("port", 8000)
            ffmpeg_exe   = job.get("ffmpeg_exe", "")
            vision_model = job.get("vision_model", "")
            frame_interval = float(job.get("frame_interval", 4.0))
            db_path = job.get("db_path", "")
            if db_path:
                from backend.ai.VideoSemantic.indexer import switch_db as _sw
                _sw(db_path)
                from backend.worker import transcript_status as _ts
                _ts.set_db_path(db_path)
            # Skip jobs that were cancelled before they got to run
            from backend.worker import index_cache as _ic
            if _ic.is_cancelled(asset_id):
                print(f"[SandboxWorker] Skipping cancelled index_video job: {asset_id[:8]}", flush=True)
                result_queue.put({"type": "index_video_cancelled", "assetId": asset_id})
                continue
            try:
                chunks = _do_index_video(asset_id, filepath, port,
                                         ffmpeg_exe=ffmpeg_exe,
                                         vision_model=vision_model,
                                         frame_interval=frame_interval,
                                         result_queue=result_queue,
                                         cancel_queue=cancel_queue)
                result_queue.put({"type": "index_video_done", "assetId": asset_id, "chunks": chunks})
            except _IndexCancelled as ce:
                print(f"[SandboxWorker] index_video cancelled: {asset_id[:8]} — {ce}", flush=True)
                result_queue.put({"type": "index_video_cancelled", "assetId": asset_id})
            except Exception as e:
                result_queue.put({"type": "index_video_error", "assetId": asset_id, "message": str(e)})
            continue

        if job.get("type") == "transcribe_only":
            asset_id = job["assetId"]
            filepath = job["filepath"]
            db_path = job.get("db_path", "")
            if db_path:
                from backend.ai.VideoSemantic.indexer import switch_db as _sw
                _sw(db_path)
                from backend.worker import transcript_status as _ts
                _ts.set_db_path(db_path)
            try:
                chunks = _do_transcribe_only(asset_id, filepath)
                result_queue.put({"type": "index_video_done", "assetId": asset_id, "chunks": chunks})
            except Exception as e:
                result_queue.put({"type": "index_video_error", "assetId": asset_id, "message": str(e)})
            continue

        if job.get("type") == "index_image":
            asset_id = job["assetId"]
            filepath = job["filepath"]
            vision_model = job.get("vision_model", "")
            db_path = job.get("db_path", "")
            if db_path:
                from backend.ai.VideoSemantic.indexer import switch_db as _sw
                _sw(db_path)
            try:
                ok = _do_index_image(asset_id, filepath, vision_model=vision_model)
                result_queue.put({"type": "index_image_done", "assetId": asset_id, "saved": ok})
            except Exception as e:
                result_queue.put({"type": "index_image_error", "assetId": asset_id, "message": str(e)})
            continue

        if job.get("type") == "transcribe_audio":
            asset_id = job["assetId"]
            filepath = job["filepath"]
            db_path = job.get("db_path", "")
            if db_path:
                from backend.ai.VideoSemantic.indexer import switch_db as _sw
                _sw(db_path)
                from backend.worker import transcript_status as _ts
                _ts.set_db_path(db_path)
            try:
                count = _do_transcribe_audio(asset_id, filepath)
                result_queue.put({"type": "transcribe_audio_done", "assetId": asset_id, "segments": count})
            except Exception as e:
                result_queue.put({"type": "transcribe_audio_error", "assetId": asset_id, "message": str(e)})
            continue

        print(f"[SandboxWorker] unknown job type: {job.get('type')}", flush=True)

    print("[SandboxWorker] exiting", flush=True)
