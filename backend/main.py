from __future__ import annotations
import os
import faulthandler
from pathlib import Path

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

 
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_FFMPEG_DIRS = [
    str(_PROJECT_ROOT / "tools" / "ffmpeg"),   # bundled  
    r"D:\ffmpeg\FFmpeg",                         
    r"C:\Users\raush\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0-full_build\bin",  # fallback B
]
for _d in _FFMPEG_DIRS:
    if os.path.isdir(_d) and _d not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _d + os.pathsep + os.environ.get("PATH", "")
        print(f"[main] Added ffmpeg to PATH: {_d}", flush=True)
        break   

faulthandler.enable()

import sys
import io

if sys.stdout and hasattr(sys.stdout, 'buffer') and getattr(sys.stdout, 'encoding', 'utf-8').lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
if sys.stderr and hasattr(sys.stderr, 'buffer') and getattr(sys.stderr, 'encoding', 'utf-8').lower() != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

sys.setswitchinterval(0.001)

import asyncio
import concurrent.futures
import socket
import struct
import json as _json
import threading
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.state import engine
from backend.timeline.tracks.videoTrack import VideoTrack
from backend.timeline.tracks.audioTrack import AudioTrack
from backend.worker.worker_bus import bus as _worker_bus
from backend.routers.render import _get_frame_data

from backend.routers import (
    project,
    render,
    library,
    timeline,
    playback,
    clips,
    comps,
    effects,
    transitions,
    audio,
    export_,
    search,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine.newProject()
    tl = engine.activeTimeline
    if tl:
        for name in ["Video 1", "Video 2", "Video 3"]:
            tl.addTrack(VideoTrack(name))
        tl.addTrack(AudioTrack("Audio 1"))

    try:
        _worker_bus.start()
    except Exception as _e:
        print(f"[main] sandbox worker failed to start: {_e}", flush=True)

    asyncio.create_task(engine.startPreviewLoop())

    _HTTP_PORT = int(os.environ.get("BACKEND_PORT", 8000))
    _TCP_PORT  = _HTTP_PORT + 1

    def _free_port(port: int) -> None:
        """Best-effort: kill whatever process holds *port* on Windows/Linux."""
        try:
            import psutil
            for conn in psutil.net_connections(kind="tcp"):
                if conn.laddr and conn.laddr.port == port and conn.pid:
                    try:
                        psutil.Process(conn.pid).terminate()
                        print(f"[TCP] Killed PID {conn.pid} which held port {port}", flush=True)
                    except Exception:
                        pass
        except ImportError:
            # psutil not available  
            try:
                import subprocess, re
                out = subprocess.check_output(
                    f"netstat -ano | findstr :{port}", shell=True, text=True
                )
                for line in out.splitlines():
                    m = re.search(r"\s+(\d+)\s*$", line)
                    if m:
                        pid = int(m.group(1))
                        subprocess.run(f"taskkill /PID {pid} /F", shell=True,
                                       capture_output=True)
                        print(f"[TCP] taskkill PID {pid} on port {port}", flush=True)
            except Exception:
                pass

 
    _frame_executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=2,
        thread_name_prefix="tcp-frame",
    )

    def _run_tcp_server():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _prefetch: dict[int, bytes] = {}   # frame_num  
        _in_flight: set[int] = set()       # frames currently being computed

        async def _compute_frame(fn: int) -> bytes:
            """Compute _get_frame_data off the event loop (thread pool)."""
            try:
                data = await loop.run_in_executor(_frame_executor, _get_frame_data, fn)
                return _json.dumps(data).encode("utf-8")
            except Exception:
                import traceback; traceback.print_exc()
                fallback = {"frame": fn, "fps": 30, "width": 1920, "height": 1080, "clips": []}
                return _json.dumps(fallback).encode("utf-8")

        async def _prefetch_next(after_frame: int) -> None:
             
            fn = after_frame + 1
            if fn in _prefetch or fn in _in_flight:
                return
            _in_flight.add(fn)
            try:
                payload = await _compute_frame(fn)
                _prefetch[fn] = payload
            finally:
                _in_flight.discard(fn)

        async def _handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
            import backend.media.scheduler.decodeScheduler as _ds_mod
            _ds_mod.cpp_renderer_active = True
            print("[TCP] C++ frame client connected", flush=True)
            try:
                while True:
                    header    = await reader.readexactly(4)
                    frame_num = struct.unpack("<I", header)[0]

                    # Cache hit?
                    payload = _prefetch.pop(frame_num, None)
                    _in_flight.discard(frame_num)

                    if payload is None:
                        # Miss: compute now  
                        payload = await _compute_frame(frame_num)

                    writer.write(struct.pack("<I", len(payload)) + payload)
                    await writer.drain()

                    # Evict stale entries
                    for old in [k for k in list(_prefetch) if k <= frame_num]:
                        _prefetch.pop(old, None)
                        _in_flight.discard(old)

                    # Kick off sequential prefetch of N+1  
                    asyncio.create_task(_prefetch_next(frame_num))

            except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
                pass
            finally:
                import backend.media.scheduler.decodeScheduler as _ds_mod
                _ds_mod.cpp_renderer_active = False
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass
                print("[TCP] C++ frame client disconnected", flush=True)

        async def _serve():
            # Pass reuse_address=True  
            for attempt in range(3):
                try:
                    server = await asyncio.start_server(
                        _handle_client, "127.0.0.1", _TCP_PORT,
                        reuse_address=True,
                    )
                    print(f"[TCP] Frame server listening on 127.0.0.1:{_TCP_PORT}", flush=True)
                    async with server:
                        await server.serve_forever()
                    return
                except OSError as exc:
                    if attempt == 0:
                        print(f"[TCP] Port {_TCP_PORT} busy (attempt {attempt+1}): {exc} — freeing…",
                              flush=True)
                        _free_port(_TCP_PORT)
                        await asyncio.sleep(0.8)
                    else:
                        print(f"[TCP] Could not bind port {_TCP_PORT} after {attempt+1} attempts: {exc}",
                              flush=True)
                        raise

        try:
            loop.run_until_complete(_serve())
        except Exception as exc:
            print(f"[TCP] Frame server FATAL: {exc} — C++ renderer will not receive frame data.",
                  flush=True)

    threading.Thread(target=_run_tcp_server, daemon=True, name="tcp-frame-server").start()


    yield

    try:
        _worker_bus.stop()
    except Exception:
        pass


app = FastAPI(title="Fade Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# AI router
try:
    from backend.ai.router import ai_router
    app.include_router(ai_router, prefix="/ai")
    print("[main] AI router mounted at /ai", flush=True)
except ImportError as _ai_err:
    print(f"[main] AI router not available: {_ai_err}", flush=True)

# Domain routers
app.include_router(project.router)
app.include_router(render.router)
app.include_router(library.router)
app.include_router(timeline.router)
app.include_router(playback.router)
app.include_router(clips.router)
app.include_router(comps.router)
app.include_router(effects.router)
app.include_router(transitions.router)
app.include_router(audio.router)
app.include_router(export_.router)
app.include_router(search.router)

 
from fastapi.responses import FileResponse as _FileResponse
import pathlib as _pathlib

_RUNTIME_JS = (
    _pathlib.Path(__file__).parent.parent / "templates" / "webcomps" / "_runtime" / "fade-react.js"
)

@app.get("/runtime/fade-react.js", include_in_schema=False)
async def serve_runtime_js():
    if not _RUNTIME_JS.exists():
        from fastapi import HTTPException
        raise HTTPException(404, "fade-react.js not found")
    return _FileResponse(str(_RUNTIME_JS), media_type="application/javascript")


# Server-Sent Events endpoint  
 
@app.get("/events")
async def sse_events(request: Request):
    from starlette.responses import StreamingResponse
    from backend.events import event_stream

    async def _guarded():
        async for chunk in event_stream():
            if await request.is_disconnected():
                break
            yield chunk

    return StreamingResponse(
        _guarded(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering
            "Connection": "keep-alive",
        },
    )


def _findFreePort(start: int = 8000, end: int = 8010) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found between {start} and {end}")


if __name__ == "__main__":
    port = _findFreePort()
    os.environ["BACKEND_PORT"] = str(port)
    print(f"[Fade] Backend starting on port {port}", flush=True)
    print(f"[Fade] Python {sys.version.split()[0]} | skia + subprocess-ffmpeg ready", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
