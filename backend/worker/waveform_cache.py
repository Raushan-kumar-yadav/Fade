"""
waveform_cache.py — Thread-safe in-memory store for waveform results.

Keys are assetId strings. Values are:
  {"status": "pending"}
  {"status": "done",  "peaks": [...], "bins": N}
  {"status": "error", "message": "..."}
"""
from __future__ import annotations
import threading

_lock  = threading.Lock()
_cache: dict[str, dict] = {}


def set_pending(asset_id: str) -> None:
    with _lock:
        _cache[asset_id] = {"status": "pending"}


def set_result(asset_id: str, peaks: list[float]) -> None:
    with _lock:
        _cache[asset_id] = {"status": "done", "peaks": peaks, "bins": len(peaks)}


def set_error(asset_id: str, message: str) -> None:
    with _lock:
        _cache[asset_id] = {"status": "error", "message": message}


def get(asset_id: str) -> dict | None:
    with _lock:
        return _cache.get(asset_id)


def has(asset_id: str) -> bool:
    with _lock:
        return asset_id in _cache
