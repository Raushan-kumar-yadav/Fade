"""
worker_bus.py — Singleton that owns the sandbox worker process and queues.

Usage:
    from backend.worker.worker_bus import bus
    bus.start()
    bus.submit_waveform("assetId", "path/to/file.mp4")
    bus.submit_index_video("assetId", "path/to/file.mp4")
    bus.get_index_status("assetId")  # → {"status": "pending"|"running"|"done"|"error", ...}
"""
from __future__ import annotations
import multiprocessing
import threading
import os
from typing import Optional

from backend.worker import sandbox_worker
from backend.worker import waveform_cache
from backend.worker import index_cache


class WorkerBus:
    def __init__(self) -> None:
        self._job_queue:    multiprocessing.Queue = multiprocessing.Queue()
        self._result_queue: multiprocessing.Queue = multiprocessing.Queue()
        self._process:  Optional[multiprocessing.Process] = None
        self._drain_thread: Optional[threading.Thread] = None
        self._running = False

    def start(self) -> None:
        if self._process and self._process.is_alive():
            return  # already running

        self._running = True
        ctx = multiprocessing.get_context("spawn")
        self._process = ctx.Process(
            target=sandbox_worker.worker_main,
            args=(self._job_queue, self._result_queue),
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
        print("[WorkerBus] stopped", flush=True)

    def is_alive(self) -> bool:
        return bool(self._process and self._process.is_alive())

    def queue_depth(self) -> int:
        try:
            return self._job_queue.qsize()
        except Exception:
            return -1

    # ── Waveform helpers ──────────────────────────────────────────────────────

    def get_cached(self, asset_id: str) -> dict | None:
        return waveform_cache.get(asset_id)

    def submit_waveform(self, asset_id: str, filepath: str, bins: int = 1000) -> None:
        """Convenience: mark pending + enqueue waveform job."""
        if waveform_cache.has(asset_id):
            entry = waveform_cache.get(asset_id)
            if entry and entry.get("status") == "done":
                return  # already cached
        waveform_cache.set_pending(asset_id)
        self.submit({
            "type":     "waveform",
            "assetId":  asset_id,
            "filepath": filepath,
            "bins":     bins,
        })

    # ── VideoSemantic indexing helpers ────────────────────────────────────────

    def submit_index_video(self, asset_id: str, filepath: str, port: int = 8000) -> None:
        """Enqueue a VideoSemantic indexing job (fire-and-forget, shows in GUI progress)."""
        existing = index_cache.get(asset_id)
        if existing and existing.get("status") in ("pending", "running", "done"):
            return  # already queued or done
        index_cache.set_pending(asset_id)
        self.submit({
            "type":     "index_video",
            "assetId":  asset_id,
            "filepath": filepath,
            "port":     port,
        })
        print(f"[WorkerBus] index_video queued for {asset_id[:8]}", flush=True)

    def get_index_status(self, asset_id: str) -> dict | None:
        return index_cache.get(asset_id)

    # ── Result drain ──────────────────────────────────────────────────────────

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

            elif rtype == "index_video_done":
                index_cache.set_done(asset_id, result.get("chunks", 0))
                print(f"[WorkerBus] index_video done: {asset_id[:8]} ({result.get('chunks')} chunks)", flush=True)
                # Notify frontend via SSE so GUI progress widget can update
                try:
                    from backend.events import notify
                    notify("library")
                except Exception:
                    pass

            elif rtype == "index_video_error":
                index_cache.set_error(asset_id, result.get("message", "unknown"))
                print(f"[WorkerBus] index_video error: {asset_id[:8]}: {result.get('message')}", flush=True)


# Global singleton — import this everywhere
bus = WorkerBus()
