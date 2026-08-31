
from __future__ import annotations
import multiprocessing
import threading
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from backend.worker import sandbox_worker
from backend.worker import waveform_cache
from backend.worker import index_cache


class WorkerBus:
    def __init__(self) -> None:
        self._job_queue: multiprocessing.Queue = multiprocessing.Queue()
        self._result_queue: multiprocessing.Queue = multiprocessing.Queue()
        self._cancel_queue: multiprocessing.Queue = multiprocessing.Queue()  # carries asset_ids to cancel
        self._process:  Optional[multiprocessing.Process] = None
        self._drain_thread: Optional[threading.Thread] = None
        self._running = False
         
        self._waveform_pool = ThreadPoolExecutor(
            max_workers=3, thread_name_prefix="FadeWaveform"
        )
        self._watchdog_thread: Optional[threading.Thread] = None

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
        print("[WorkerBus] sandbox worker started", flush=True)

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
                    f"[WorkerBus] sandbox process died (exit={exit_code}) — restarting",
                    flush=True,
                )
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
            _candidates = [
                os.path.join(_root, "tools", "ffmpeg", "ffmpeg.exe"),
                r"D:\ffmpeg\FFmpeg\ffmpeg.exe",
                r"C:\ffmpeg\bin\ffmpeg.exe",
            ]
            for c in _candidates:
                if os.path.isfile(c):
                    ffmpeg_exe = c
                    break

        from backend.config.global_config import cfg as _cfg
        vision_model   = _cfg.get("ai.vision_model",   "moondream:latest")
        frame_interval = _cfg.get("ai.frame_interval", 4.0)

        print(f"[WorkerBus] index_video queued for {asset_id[:8]} model={vision_model} interval={frame_interval}s", flush=True)
        self.submit({
            "type": "index_video",
            "assetId": asset_id,
            "filepath": filepath,
            "port": port,
            "ffmpeg_exe": ffmpeg_exe,
            "vision_model":   vision_model,
            "frame_interval": frame_interval,
            "db_path": db_path,   # empty = use default
        })

    def submit_index_image(self, asset_id: str, filepath: str, db_path: str = "") -> None:
        """Queue a single-image description + ChromaDB save job."""
        from backend.config.global_config import cfg as _cfg
        vision_model = _cfg.get("ai.vision_model", "moondream:latest")
        index_cache.set_pending(asset_id)
        print(f"[WorkerBus] index_image queued for {asset_id[:8]} model={vision_model}", flush=True)
        self.submit({
            "type": "index_image",
            "assetId": asset_id,
            "filepath": filepath,
            "vision_model": vision_model,
            "db_path": db_path,   # empty = use default
        })

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

            elif rtype == "index_video_error":
                index_cache.set_error(asset_id, result.get("message", "unknown"))
                print(f"[WorkerBus] index_video error: {asset_id[:8]}: {result.get('message')}", flush=True)
                try:
                    from backend.routers.jobs import complete_asset_job
                    complete_asset_job(asset_id, "video_index",
                                       error=result.get("message", "indexing failed"))
                except Exception:
                    pass

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

            elif rtype == "index_image_error":
                index_cache.set_error(asset_id, result.get("message", "unknown"))
                print(f"[WorkerBus] index_image error: {asset_id[:8]}: {result.get('message')}", flush=True)
                try:
                    from backend.routers.jobs import complete_asset_job
                    complete_asset_job(asset_id, "image_index",
                                       error=result.get("message", "indexing failed"))
                except Exception:
                    pass

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
