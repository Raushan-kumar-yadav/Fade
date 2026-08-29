 
from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncIterator

# All active SSE subscriber queues
_subscribers: list[asyncio.Queue] = []


def notify(scope: str, data: dict | None = None) -> None:
     
    payload = json.dumps({"scope": scope, "ts": time.time(), **(data or {})})
    dead: list[asyncio.Queue] = []
    for q in list(_subscribers):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        try:
            _subscribers.remove(q)
        except ValueError:
            pass


async def event_stream() -> AsyncIterator[str]:
    """Async generator that yields SSE-formatted messages."""
    q: asyncio.Queue = asyncio.Queue(maxsize=64)
    _subscribers.append(q)
     
    yield f"event: connected\ndata: {json.dumps({'ok': True})}\n\n"
    try:
        while True:
            try:
                # Heartbeat every 
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
