
from __future__ import annotations
import multiprocessing
import threading
import os
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from backend.worker import sandbox_worker
from backend.worker import waveform_cache
from backend.worker import index_cache


class WorkerBus:
    def __init__(self) -> None:
        self._job_queue: multiprocessing.Queue = multiprocessing.Queue()
        self._result_queue: multiprocessing.Queue = multiprocessing.Queue()
        self._cancel_queue: multiprocessing.Queue = multiprocessing.Queue()   
        self._process:  Optional[multiprocessing.Process] = None
        self._drain_thread: Optional[threading.Thread] = None
        self._running = False
         
        self._waveform_pool = ThreadPoolExecutor(
            max_workers=3, thread_name_prefix="FadeWaveform"
        )
        self._watchdog_thread: Optional[threading.Thread] = None

        #   Concurrent indexing limiter  
        self._index_lock = threading.Lock()
        self._active_index_ids: set[str] = set()      # asset IDs currently being indexed
        self._index_waiting: deque[dict] = deque()     # jobs waiting for a slot
        self._max_concurrent_index: int = 2            # default; overridden by config

    def is_indexing_active(self) -> bool:
        """True while any vision or transcript indexing job is running in the sandbox.

        Used by project.py to skip ChromaDB reads/heals during indexing to prevent
        concurrent multi-process Rust HNSW access (which causes a code-1 segfault).
        """
        with self._index_lock:
            return len(self._active_index_ids) > 0

    def start(self) -> None:
        if self._process and self._process.is_alive():
            return  # already running

        import sys, os
        parent_syspath = sys.path[:]    

       
        if sys.platform == "win32" and getattr(sys, "executable", "").lower().endswith(".exe"):
            python_exe = os.path.join(sys.exec_prefix, "python.exe")
            if os.path.exists(python_exe) and sys.executable.lower() != python_exe.lower():
                multiprocessing.set_executable(python_exe)

        self._running = True
        ctx = multiprocessing.get_context("spawn")
        self._process = ctx.Process(
            target=sandbox_worker.worker_main,
            args=(self._job_queue, self._result_queue, self._cancel_queue, parent_syspath),
            daemon=True,
            name="FadeSandboxWorker",
        )
        self._process.start()

        self._drain_thread = threading.Thread(
            target=self._drain_results,
            daemon=True,
            name="FadeWorkerDrain",
        )
        self._drain_thread.start()

        # Watchdog 
        self._watchdog_thread = threading.Thread(
            target=self._watchdog,
            daemon=True,
            name="FadeWorkerWatchdog",
        )
        self._watchdog_thread.start()

        # Load concurrency limit from config
        try:
            from backend.config.global_config import cfg as _cfg
            saved = _cfg.get("ai.max_concurrent_index", 2)
            self._max_concurrent_index = max(1, min(10, int(saved)))
        except Exception:
            pass

        print(f"[WorkerBus] sandbox worker started (max_concurrent_index={self._max_concurrent_index})", flush=True)

    def submit(self, job: dict) -> None:
        """Non-blocking: enqueue a job for the worker."""
        if not self._process or not self._process.is_alive():
            print("[WorkerBus] worker not running — restarting", flush=True)
            self.start()
        self._job_queue.put_nowait(job)

    def stop(self) -> None:
        self._running = False
        try:
            self._job_queue.put_nowait({"type": "_shutdown"})
        except Exception:
            pass
        if self._process:
            self._process.join(timeout=5)
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(timeout=2)
        # Free any active index slots that were held when the worker died
        # so the bus doesn't get stuck when restarted
        with self._index_lock:
            leaked = list(self._active_index_ids)
            self._active_index_ids.clear()
        for aid in leaked:
            print(f"[WorkerBus] stop: freeing leaked index slot {aid[:8]}", flush=True)
        self._waveform_pool.shutdown(wait=False)
        print("[WorkerBus] stopped", flush=True)

    def _watchdog(self) -> None:
        """Restart the sandbox process if it dies unexpectedly."""
        import time
        while self._running:
            time.sleep(10)
            if not self._running:
                break
            if self._process and not self._process.is_alive():
                exit_code = self._process.exitcode
                print(
                    f"[WorkerBus] sandbox process died (exit={exit_code}) — freeing slots & restarting",
                    flush=True,
                )
                # Free any index slots held at crash time
                with self._index_lock:
                    leaked = list(self._active_index_ids)
                    self._active_index_ids.clear()
                for aid in leaked:
                    try:
                        from backend.worker import index_cache as _ic
                        _ic.set_error(aid, "worker process died unexpectedly")
                        from backend.routers.jobs import complete_asset_job
                        complete_asset_job(aid, "video_index", error="worker died")
                    except Exception:
                        pass
                    print(f"[WorkerBus] watchdog: freed slot for {aid[:8]}", flush=True)
                self.start()

    def is_alive(self) -> bool:
        return bool(self._process and self._process.is_alive())

    def queue_depth(self) -> int:
        try:
            return self._job_queue.qsize()
        except Exception:
            return -1

    #   Waveform helpers  

    def get_cached(self, asset_id: str) -> dict | None:
        return waveform_cache.get(asset_id)

    def submit_waveform(self, asset_id: str, filepath: str, bins: int = 1000) -> None:
         
        if waveform_cache.has(asset_id):
            entry = waveform_cache.get(asset_id)
            if entry and entry.get("status") == "done":
                return  # already cached
        waveform_cache.set_pending(asset_id)
        self._waveform_pool.submit(self._run_waveform_thread, asset_id, filepath, bins)

    def _run_waveform_thread(self, asset_id: str, filepath: str, bins: int) -> None:
        """Runs inside the waveform thread pool — calls _do_waveform directly."""
        try:
            peaks = sandbox_worker._do_waveform(filepath, bins)
            waveform_cache.set_result(asset_id, peaks)
            print(f"[WorkerBus] waveform done: {asset_id[:8]}", flush=True)
        except Exception as exc:
            import traceback
            msg = f"{type(exc).__name__}: {exc}"
            waveform_cache.set_error(asset_id, msg)
            print(f"[WorkerBus] waveform error: {asset_id[:8]}: {msg}", flush=True)
            traceback.print_exc()

    #   Concurrent indexing gate  

    def set_max_concurrent_index(self, n: int) -> None:
        """Update the concurrent indexing limit (called from settings API)."""
        with self._index_lock:
            self._max_concurrent_index = max(1, min(10, n))
            print(f"[WorkerBus] max_concurrent_index -> {self._max_concurrent_index}", flush=True)
        # Try to promote waiting jobs with the new limit
        self._promote_waiting()

    def get_max_concurrent_index(self) -> int:
        return self._max_concurrent_index

    def _try_submit_index(self, job: dict) -> None:
        """Submit an indexing job if under the concurrency limit, else queue it."""
        asset_id = job["assetId"]
        with self._index_lock:
            if len(self._active_index_ids) < self._max_concurrent_index:
                self._active_index_ids.add(asset_id)
                print(f"[WorkerBus] index START {asset_id[:8]} (active={len(self._active_index_ids)}/{self._max_concurrent_index})", flush=True)
                self.submit(job)
            else:
                self._index_waiting.append(job)
                index_cache.set_pending(asset_id)  # keep UI showing "queued"
                print(f"[WorkerBus] index QUEUED {asset_id[:8]} (waiting={len(self._index_waiting)}, active={len(self._active_index_ids)}/{self._max_concurrent_index})", flush=True)

    def _on_index_complete(self, asset_id: str) -> None:
        """Called when an indexing job finishes (done/error/cancelled). Promotes next waiting job."""
        with self._index_lock:
            self._active_index_ids.discard(asset_id)
        self._promote_waiting()

    def _promote_waiting(self) -> None:
        """Move waiting jobs into the active set if slots are available."""
        while True:
            with self._index_lock:
                if not self._index_waiting:
                    break
                if len(self._active_index_ids) >= self._max_concurrent_index:
                    break
                job = self._index_waiting.popleft()
                aid = job["assetId"]
                # Skip if cancelled while waiting
                if index_cache.is_cancelled(aid):
                    print(f"[WorkerBus] skipping cancelled waiting job {aid[:8]}", flush=True)
                    continue
                self._active_index_ids.add(aid)
                print(f"[WorkerBus] index PROMOTED {aid[:8]} (active={len(self._active_index_ids)}/{self._max_concurrent_index}, waiting={len(self._index_waiting)})", flush=True)
            self.submit(job)

    def get_index_queue_info(self) -> dict:
        """Return queue status for the frontend."""
        with self._index_lock:
            return {
                "maxConcurrent": self._max_concurrent_index,
                "active": len(self._active_index_ids),
                "waiting": len(self._index_waiting),
                "activeIds": list(self._active_index_ids),
                "waitingIds": [j["assetId"] for j in self._index_waiting],
            }

    # VideoSemantic indexing helpers  

    def submit_index_video(self, asset_id: str, filepath: str, port: int = 8000,
                           db_path: str = "") -> None:
        """Enqueue a VideoSemantic indexing job (fire-and-forget, shows in GUI progress)."""
        existing = index_cache.get(asset_id)
        if existing and existing.get("status") in ("pending", "running", "done"):
            return  # already queued or done
        index_cache.set_pending(asset_id)

        import shutil
        ffmpeg_exe = shutil.which("ffmpeg") or ""
        if not ffmpeg_exe:
            _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            for c in [
                os.path.join(_root, "tools", "ffmpeg", "ffmpeg.exe"),
                os.path.join(_root, "renderer", "build", "Release", "ffmpeg.exe"),
            ]:
                if os.path.isfile(c):
                    ffmpeg_exe = c
                    break

        from backend.config.global_config import cfg as _cfg
        vision_model   = _cfg.get("ai.vision_model",   "moondream:latest")
        frame_interval = _cfg.get("ai.frame_interval", 4.0)

        job = {
            "type": "index_video",
            "assetId": asset_id,
            "filepath": filepath,
            "port": port,
            "ffmpeg_exe": ffmpeg_exe,
            "vision_model":   vision_model,
            "frame_interval": frame_interval,
            "db_path": db_path,   # empty = use default
        }
        print(f"[WorkerBus] index_video queued for {asset_id[:8]} model={vision_model} interval={frame_interval}s", flush=True)
        self._try_submit_index(job)

    def submit_index_image(self, asset_id: str, filepath: str, db_path: str = "") -> None:
        """Queue a single-image description + ChromaDB save job."""
        from backend.config.global_config import cfg as _cfg
        vision_model = _cfg.get("ai.vision_model", "moondream:latest")
        index_cache.set_pending(asset_id)
        job = {
            "type": "index_image",
            "assetId": asset_id,
            "filepath": filepath,
            "vision_model": vision_model,
            "db_path": db_path,   # empty = use default
        }
        print(f"[WorkerBus] index_image queued for {asset_id[:8]} model={vision_model}", flush=True)
        self._try_submit_index(job)

    def submit_transcribe_audio(self, asset_id: str, filepath: str, db_path: str = "") -> None:
        """Queue a Whisper-only transcript job for a pure audio file (no vision)."""
        from backend.worker.transcript_status import is_done as _ts_done
        if _ts_done(asset_id):
            return  # already transcribed
        print(f"[WorkerBus] transcribe_audio queued for {asset_id[:8]}", flush=True)
        self.submit({
            "type": "transcribe_audio",
            "assetId": asset_id,
            "filepath": filepath,
            "db_path": db_path,
        })

    def cancel_index(self, asset_id: str) -> None:
        """Signal the sandbox worker to stop indexing a specific asset.

        Works for both queued (not started yet) and actively running jobs:
        - Marks index_cache as 'cancelled' so the pending-check at job start fires.
        - Sends asset_id through the cancel queue so the running frame loop exits early.
        """
        from backend.worker import index_cache
        index_cache.set_cancelled(asset_id)
        try:
            self._cancel_queue.put_nowait(asset_id)
        except Exception:
            pass
        # Complete any SSE job card for this asset so the UI updates
        try:
            from backend.routers.jobs import complete_asset_job
            complete_asset_job(asset_id, "video_index", error=None)
            complete_asset_job(asset_id, "image_index", error=None)
        except Exception:
            pass
        try:
            from backend.events import notify
            notify("library")
        except Exception:
            pass
        print(f"[WorkerBus] cancel_index: {asset_id[:8]}", flush=True)

    def get_index_status(self, asset_id: str) -> dict | None:
        return index_cache.get(asset_id)

    #   Result drain  

    def _drain_results(self) -> None:
        """Runs in a daemon thread in the main process. Never blocks FastAPI."""
        while self._running:
            try:
                result = self._result_queue.get(timeout=2)
            except Exception:
                continue

            rtype    = result.get("type", "")
            asset_id = result.get("assetId", "")

            if rtype == "waveform_done":
                waveform_cache.set_result(asset_id, result["peaks"])
                print(f"[WorkerBus] waveform done: {asset_id[:8]}", flush=True)

            elif rtype == "waveform_error":
                waveform_cache.set_error(asset_id, result.get("message", "unknown"))
                print(f"[WorkerBus] waveform error: {asset_id[:8]}: {result.get('message')}", flush=True)

            elif rtype == "index_video_phase1":
                # Vision indexed, transcript still running  
                chunks = result.get("chunks", 0)
                print(f"[WorkerBus] index_video phase1: {asset_id[:8]} ({chunks} vision chunks, transcribing…)", flush=True)
                index_cache.set_progress(asset_id, chunks, stage="transcribing")
                try:
                    from backend.events import notify
                    notify("library")
                except Exception:
                    pass

            elif rtype == "index_video_done":
                index_cache.set_done(asset_id, result.get("chunks", 0))
                print(f"[WorkerBus] index_video done: {asset_id[:8]} ({result.get('chunks')} chunks)", flush=True)
                try:
                    from backend.routers.jobs import complete_asset_job
                    complete_asset_job(asset_id, "video_index")
                except Exception:
                    pass
                # Notify agent of completion
                try:
                    from backend.ai.agent_jobs import on_job_done as _aj_done
                    _aj_done(asset_id, {"assetId": asset_id, "type": "index_video", "chunks": result.get("chunks", 0)})
                except Exception:
                    pass
                try:
                    from backend.events import notify
                    notify("library")
                except Exception:
                    pass
                self._on_index_complete(asset_id)

            elif rtype == "index_video_error":
                index_cache.set_error(asset_id, result.get("message", "unknown"))
                print(f"[WorkerBus] index_video error: {asset_id[:8]}: {result.get('message')}", flush=True)
                try:
                    from backend.routers.jobs import complete_asset_job
                    complete_asset_job(asset_id, "video_index",
                                       error=result.get("message", "indexing failed"))
                except Exception:
                    pass
                self._on_index_complete(asset_id)

            elif rtype == "index_video_frame_progress":
                # Per-frame progress: 10% → 80% during vision phase
                frame = result.get("frame", 0)
                total = result.get("total", 1)
                pct = 0.10 + 0.70 * (frame / max(total, 1))
                try:
                    from backend.routers.jobs import update_asset_job_progress
                    update_asset_job_progress(
                        asset_id, "video_index", pct,
                        f"Analyzing frame {frame}/{total}…"
                    )
                except Exception:
                    pass

            elif rtype == "index_video_cancelled":
                self._on_index_complete(asset_id)

            elif rtype == "index_image_done":
                index_cache.set_done(asset_id, 1)
                print(f"[WorkerBus] index_image done: {asset_id[:8]}", flush=True)
                try:
                    from backend.routers.jobs import complete_asset_job
                    complete_asset_job(asset_id, "image_index")
                except Exception:
                    pass
                # Notify agent of completion
                try:
                    from backend.ai.agent_jobs import on_job_done as _aj_done
                    _aj_done(asset_id, {"assetId": asset_id, "type": "index_image"})
                except Exception:
                    pass
                try:
                    from backend.events import notify
                    notify("library")
                except Exception:
                    pass
                self._on_index_complete(asset_id)

            elif rtype == "index_image_error":
                index_cache.set_error(asset_id, result.get("message", "unknown"))
                print(f"[WorkerBus] index_image error: {asset_id[:8]}: {result.get('message')}", flush=True)
                try:
                    from backend.routers.jobs import complete_asset_job
                    complete_asset_job(asset_id, "image_index",
                                       error=result.get("message", "indexing failed"))
                except Exception:
                    pass
                self._on_index_complete(asset_id)

            elif rtype == "transcribe_audio_done":
                segs = result.get("segments", 0)
                print(f"[WorkerBus] transcribe_audio done: {asset_id[:8]} ({segs} segments)", flush=True)
                try:
                    from backend.routers.jobs import complete_asset_job
                    complete_asset_job(asset_id, "audio_transcript")
                except Exception:
                    pass
                try:
                    from backend.events import notify
                    notify("library")
                except Exception:
                    pass

            elif rtype == "transcribe_audio_error":
                print(f"[WorkerBus] transcribe_audio error: {asset_id[:8]}: {result.get('message')}", flush=True)
                try:
                    from backend.routers.jobs import complete_asset_job
                    complete_asset_job(asset_id, "audio_transcript",
                                       error=result.get("message", "transcription failed"))
                except Exception:
                    pass


    def check_and_resume(self, db_path: str = "", port: int = 8000) -> None:
         
        import threading
        threading.Thread(
            target=self._check_and_resume_bg,
            args=(db_path, port),
            daemon=True,
            name="FadeResumeCheck",
        ).start()

    def _check_and_resume_bg(self, db_path: str, port: int) -> None:
        try:
            import time, requests
            time.sleep(2)  # let FastAPI fully start
            base = f"http://127.0.0.1:{port}"
            resp = requests.get(f"{base}/library/assets", timeout=5)
            assets = resp.json()
        except Exception as e:
            print(f"[WorkerBus] check_and_resume: library fetch failed ({e})", flush=True)
            return

        from backend.ai.VideoSemantic.indexer import is_asset_indexed
        from backend.worker.transcript_status import is_done as _ts_done

        video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
        audio_exts = {".wav", ".mp3", ".aac", ".flac", ".ogg", ".m4a"}
        queued_vision = 0
        queued_transcript = 0
        queued_audio = 0

        for asset in assets:
            aid   = asset.get("assetId", "")
            fpath = asset.get("filepath", "")
            if not aid or not fpath:
                continue
            import pathlib
            ext = pathlib.Path(fpath).suffix.lower()

            if ext in video_exts:
                vision_done = is_asset_indexed(aid)
                transcript_done = _ts_done(aid)

                if not vision_done:
                    existing = index_cache.get(aid)
                    if not existing or existing.get("status") not in ("pending", "running", "done"):
                        print(f"[WorkerBus] resume: queuing full index for {aid[:8]}", flush=True)
                        self.submit_index_video(aid, fpath, port=port, db_path=db_path)
                        queued_vision += 1
                elif not transcript_done:
                    existing = index_cache.get(aid)
                    if not existing or existing.get("status") not in ("pending", "running"):
                        print(f"[WorkerBus] resume: queuing transcript retry for {aid[:8]}", flush=True)
                        self.submit({
                            "type": "transcribe_only",
                            "assetId": aid,
                            "filepath": fpath,
                            "db_path": db_path,
                        })
                        index_cache.set_pending(aid)
                        queued_transcript += 1

            elif ext in audio_exts:
                if not _ts_done(aid):
                    print(f"[WorkerBus] resume: queuing audio transcript for {aid[:8]}", flush=True)
                    self.submit_transcribe_audio(aid, fpath, db_path=db_path)
                    queued_audio += 1

        print(f"[WorkerBus] check_and_resume: {queued_vision} vision + {queued_transcript} transcript + {queued_audio} audio jobs queued", flush=True)


# Global singleton
bus = WorkerBus()
