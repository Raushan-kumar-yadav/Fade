 
from __future__ import annotations
import json
import threading
import pathlib

_lock = threading.Lock()
_status_file: pathlib.Path | None = None


def set_db_path(db_path: str) -> None:
    """Point at the active ChromaDB directory (call whenever switch_db is called)."""
    global _status_file
    with _lock:
        _status_file = pathlib.Path(db_path) / "transcript_status.json"


def _load() -> dict:
    if _status_file and _status_file.exists():
        try:
            return json.loads(_status_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save(data: dict) -> None:
    if _status_file:
        _status_file.parent.mkdir(parents=True, exist_ok=True)
        _status_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def mark_done(asset_id: str) -> None:
    with _lock:
        d = _load()
        d[asset_id] = "done"
        _save(d)


def mark_failed(asset_id: str) -> None:
    with _lock:
        d = _load()
        d[asset_id] = "failed"
        _save(d)


def is_done(asset_id: str) -> bool:
    with _lock:
        return _load().get(asset_id) == "done"


def remove(asset_id: str) -> None:
    with _lock:
        d = _load()
        d.pop(asset_id, None)
        _save(d)


def all_statuses() -> dict:
    with _lock:
        return dict(_load())
