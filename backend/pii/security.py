"""
backend/pii/security.py
Lightweight in-memory PII security registry.
Thread-safe. No disk I/O. Does not modify MediaAsset or _library.

Public API
----------
mark(asset_id, state)       -> set state for an asset ("NONE"|"RESTRICTED"|"SANITIZED")
get_state(asset_id)         -> current state string
link(original_id, san_id)   -> record original<->sanitized relationship
get_sanitized(original_id)  -> sanitized assetId or None
get_original(sanitized_id)  -> original assetId or None
clear(asset_id)             -> remove all records for an asset
get_all_states()            -> snapshot dict for debugging
"""
from __future__ import annotations
import threading

_VALID_STATES = frozenset({"NONE", "RESTRICTED", "SANITIZED"})
_lock = threading.Lock()

# assetId -> "RESTRICTED" | "SANITIZED"   (absent == "NONE")
_asset_security: dict[str, str] = {}
_sanitized_of:   dict[str, str] = {}  # original_id -> sanitized_id
_original_of:    dict[str, str] = {}  # sanitized_id -> original_id


def mark(asset_id: str, state: str) -> None:
    if state not in _VALID_STATES:
        raise ValueError(f"Invalid security state: {state!r}. "
                         f"Must be one of {sorted(_VALID_STATES)}")
    with _lock:
        if state == "NONE":
            _asset_security.pop(asset_id, None)
        else:
            _asset_security[asset_id] = state


def get_state(asset_id: str) -> str:
    with _lock:
        return _asset_security.get(asset_id, "NONE")


def link(original_id: str, sanitized_id: str) -> None:
    with _lock:
        _sanitized_of[original_id] = sanitized_id
        _original_of[sanitized_id] = original_id


def get_sanitized(original_id: str) -> str | None:
    with _lock:
        return _sanitized_of.get(original_id)


def get_original(sanitized_id: str) -> str | None:
    with _lock:
        return _original_of.get(sanitized_id)


def clear(asset_id: str) -> None:
    with _lock:
        _asset_security.pop(asset_id, None)
        partner = _sanitized_of.pop(asset_id, None)
        if partner:
            _original_of.pop(partner, None)
        partner2 = _original_of.pop(asset_id, None)
        if partner2:
            _sanitized_of.pop(partner2, None)


def get_all_states() -> dict[str, str]:
    with _lock:
        return dict(_asset_security)
