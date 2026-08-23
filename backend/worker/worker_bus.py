"""
worker_bus.py — Singleton that owns the sandbox worker process and queues.

Usage:
    from backend.worker.worker_bus import bus
    bus.start()
    bus.submit({"type": "waveform", "assetId": "...", "filepath": "...", "bins": 200})
    result = bus.get_cached("assetId")   # returns None | dict

The result-drain thread runs in the main process and copies completed results
from the result_queue into waveform_cache — no FastAPI thread is blocked.
"""
from __future__ import annotations
import multiprocessing
import threading
from typing import Optional

from backend.worker import sandbox_worker
from backend.worker import waveform_cache


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

    # Result helpers
    def get_cached(self, asset_id: str) -> dict | None:
        return waveform_cache.get(asset_id)

    def submit_waveform(self, asset_id: str, filepath: str, bins: int = 200) -> None:
        """Convenience: mark pending + enqueue waveform job."""
        if waveform_cache.has(asset_id):
            entry = waveform_cache.get(asset_id)
            if entry and entry.get("status") == "done":
                return  # already cached
        waveform_cache.set_pending(asset_id)
        self.submit({
            "type":    "waveform",
            "assetId": asset_id,
            "filepath": filepath,
            "bins":    bins,
        })

    def _drain_results(self) -> None:
        """Runs in a daemon thread in the main process. Never blocks FastAPI."""
        while self._running:
            try:
                result = self._result_queue.get(timeout=2)
            except Exception:
                continue

            rtype = result.get("type", "")
            asset_id = result.get("assetId", "")

            if rtype == "waveform_done":
                waveform_cache.set_result(asset_id, result["peaks"])
                print(f"[WorkerBus] waveform done: {asset_id}", flush=True)
            elif rtype == "waveform_error":
                waveform_cache.set_error(asset_id, result.get("message", "unknown"))
                print(f"[WorkerBus] waveform error: {asset_id}: {result.get('message')}", flush=True)
            # Future: handle whisper_done, scene_done, etc.


# Global singleton — import this everywhere
bus = WorkerBus()
