 
from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncIterator

 
_subscribers: list[asyncio.Queue] = []
 
_loop: asyncio.AbstractEventLoop | None = None


def notify(scope: str, data: dict | None = None) -> None:
    """Push an SSE event to all subscribers.

    Safe to call from ANY thread — uses call_soon_threadsafe when called from
    outside the event loop (e.g. worker download threads, worker_bus drain thread).
    """
    payload = json.dumps({"scope": scope, "ts": time.time(), **(data or {})})

     
    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        running_loop = None

    dead: list[asyncio.Queue] = []
    for q in list(_subscribers):
        try:
            if running_loop is not None:
                # Called from within the event loop  
                q.put_nowait(payload)
            elif _loop is not None and _loop.is_running():
                # Called from a worker thread  
                _loop.call_soon_threadsafe(q.put_nowait, payload)
            else:
                # Fallback: best-effort direct put  
                q.put_nowait(payload)
        except (asyncio.QueueFull, RuntimeError):
            dead.append(q)
    for q in dead:
        try:
            _subscribers.remove(q)
        except ValueError:
            pass


async def event_stream() -> AsyncIterator[str]:
    """Async generator that yields SSE-formatted messages."""
    global _loop
    q: asyncio.Queue = asyncio.Queue(maxsize=128)
    _loop = asyncio.get_running_loop()   
    _subscribers.append(q)
     
    yield f"event: connected\ndata: {json.dumps({'ok': True})}\n\n"
    try:
        while True:
            try:
                # Heartbeat every 15 s if no events
                payload = await asyncio.wait_for(q.get(), timeout=15.0)
                 
                try:
                    obj = json.loads(payload)
                    scope = obj.get("scope", "update")
                except Exception:
                    scope = "update"
                yield f"event: {scope}\ndata: {payload}\n\n"
            except asyncio.TimeoutError:
                # Heartbeat comment  
                yield ": heartbeat\n\n"
    finally:
        try:
            _subscribers.remove(q)
        except ValueError:
            pass
