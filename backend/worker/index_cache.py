 
from __future__ import annotations
import threading

_lock: threading.Lock = threading.Lock()
_cache: dict[str, dict] = {}   # assetId → {status, chunks, message}


def set_pending(asset_id: str) -> None:
    with _lock:
        _cache[asset_id] = {"status": "pending", "chunks": 0, "message": ""}


def set_running(asset_id: str) -> None:
    with _lock:
        if asset_id in _cache:
            _cache[asset_id]["status"] = "running"


def set_done(asset_id: str, chunks: int) -> None:
    with _lock:
        _cache[asset_id] = {"status": "done", "chunks": chunks, "message": ""}


def set_progress(asset_id: str, chunks: int, stage: str = "running") -> None:
    """Partial progress — vision saved, transcript still running."""
    with _lock:
        _cache[asset_id] = {"status": "running", "chunks": chunks, "stage": stage, "message": ""}


def set_error(asset_id: str, message: str) -> None:
    with _lock:
        _cache[asset_id] = {"status": "error", "chunks": 0, "message": message}


def set_cancelled(asset_id: str) -> None:
    """Mark an indexing job as user-cancelled."""
    with _lock:
        _cache[asset_id] = {"status": "cancelled", "chunks": 0, "message": "Cancelled by user"}


def is_cancelled(asset_id: str) -> bool:
    """Return True if the user requested cancellation of this asset's indexing."""
    with _lock:
        entry = _cache.get(asset_id)
        return bool(entry and entry.get("status") == "cancelled")


def get(asset_id: str) -> dict | None:
    with _lock:
        return _cache.get(asset_id)


def remove(asset_id: str) -> None:
    with _lock:
        _cache.pop(asset_id, None)
