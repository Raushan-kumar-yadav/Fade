from __future__ import annotations
import os
import faulthandler
from pathlib import Path

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

# ── Load saved .env at startup ─────────────────────────────────────────────────
# FADE_RESOURCES_PATH is set by Electron before spawning the backend process.
# Without this, saved settings (AI provider, API keys) are lost on every restart
# because os.environ only has the default system environment.
def _load_saved_env() -> None:
    try:
        from dotenv import load_dotenv
        resources = os.environ.get("FADE_RESOURCES_PATH", "")
        if resources:
            _env_path = Path(resources) / ".env"
        else:
            # Dev mode: repo root is two levels up from backend/main.py
            _env_path = Path(__file__).resolve().parent.parent / ".env"
        if _env_path.exists():
            load_dotenv(str(_env_path), override=True)
            print(f"[Startup] Loaded .env from: {_env_path}", flush=True)
        else:
            print(f"[Startup] No .env found at: {_env_path}", flush=True)
    except Exception as e:
        print(f"[Startup] Could not load .env: {e}", flush=True)

_load_saved_env()


import sys as _sys_early

# ── Resolve project/resource root (works in dev AND PyInstaller frozen bundle) ──
if getattr(_sys_early, 'frozen', False):
    # PyInstaller: _MEIPASS is the extracted bundle temp dir
    _RESOURCE_ROOT = Path(_sys_early._MEIPASS)  # type: ignore[attr-defined]
else:
    _RESOURCE_ROOT = Path(__file__).resolve().parent.parent

# ── FFmpeg discovery (NO hardcoded user paths) ────────────────────────────────
_FFMPEG_CANDIDATES = [
    str(_RESOURCE_ROOT / "tools" / "ffmpeg"),           # bundled alongside app
    str(_RESOURCE_ROOT / "renderer" / "build" / "Release"),  # C++ build output
]
for _d in _FFMPEG_CANDIDATES:
    if os.path.isdir(_d) and _d not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _d + os.pathsep + os.environ.get("PATH", "")
        print(f"[main] Added ffmpeg to PATH: {_d}", flush=True)
        break
# If neither bundled location exists, ffmpeg must be on system PATH already

faulthandler.enable()

import sys
import io

if sys.stdout and hasattr(sys.stdout, 'buffer') and getattr(sys.stdout, 'encoding', 'utf-8').lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
if sys.stderr and hasattr(sys.stderr, 'buffer') and getattr(sys.stderr, 'encoding', 'utf-8').lower() != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

sys.setswitchinterval(0.001)

if __name__ == "__main__":
    # REQUIRED for PyInstaller + multiprocessing.spawn on Windows
    import multiprocessing as _mp
    _mp.freeze_support()

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
    context,
    scene_tools,
    audio_tools,
    animation,
    jobs,
    debug,
    virality,
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
        # Resume any unfinished indexing from previous sessions
        _HTTP_PORT_EARLY = int(os.environ.get("BACKEND_PORT", 8000))
        _worker_bus.check_and_resume(port=_HTTP_PORT_EARLY)
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

    # ── Python-fallback play loop ─────────────────────────────────────────────
    # When the C++ native renderer is NOT connected, engine._currentFrame is
    # never advanced (the C++ addon drives that via the TCP frame loop).
    # This thread advances the playhead at the correct fps and broadcasts SSE
    # 'playback' events so the timeline playhead moves in Python fallback mode.
    def _run_fallback_play_loop():
        import time as _time
        from backend.events import notify as _notify_sse
        import backend.media.scheduler.decodeScheduler as _ds_mod

        last_frame = -1
        last_time  = _time.monotonic()

        while True:
            _time.sleep(0.033)  # ~30fps tick

            # Only drive playback when C++ renderer is NOT connected
            if _ds_mod.cpp_renderer_active:
                last_time = _time.monotonic()
                continue

            if not engine._playing:
                last_time = _time.monotonic()
                continue

            prj = engine.project
            if prj is None:
                last_time = _time.monotonic()
                continue

            # Advance frame by elapsed time
            now     = _time.monotonic()
            elapsed = now - last_time
            last_time = now

            fps   = prj.fps or 30.0
            speed = getattr(engine, "_speed", 1.0)
            steps = int(elapsed * fps * speed)
            if steps < 1:
                continue

            total = prj.totalFrame or 1800
            in_p  = getattr(engine, "_inPoint",  None)
            out_p = getattr(engine, "_outPoint", None)

            new_frame = engine._currentFrame + steps
            if out_p is not None and new_frame > out_p:
                new_frame = in_p if in_p is not None else 0
            elif new_frame >= total:
                new_frame = 0
                engine._playing = False

            engine._currentFrame = new_frame

            # Broadcast current frame via SSE so frontend playhead updates
            if new_frame != last_frame:
                last_frame = new_frame
                try:
                    _notify_sse("playback", {
                        "frame":       new_frame,
                        "playing":     engine._playing,
                        "fps":         fps,
                        "totalFrames": total,
                        "speed":       speed,
                        "inPoint":     in_p,
                        "outPoint":    out_p,
                    })
                except Exception:
                    pass

    threading.Thread(
        target=_run_fallback_play_loop,
        daemon=True,
        name="fallback-play-loop",
    ).start()
    # ─────────────────────────────────────────────────────────────────────────


    # Pre-warm Kokoro TTS model in background (first load downloads ~170MB + ONNX init).
    # This prevents the agent's 30-second HTTP timeout from firing on the first TTS call.
    def _prewarm_kokoro():
        try:
            from backend.config.global_config import cfg as _cfg
            if _cfg.get("generators.tts_provider", "google") == "kokoro":
                from backend.tools.generators.tts_generator import KokoroTTSGenerator
                KokoroTTSGenerator()._get_kokoro()
                print("[main] Kokoro TTS model pre-warmed.", flush=True)
        except Exception as _e:
            print(f"[main] Kokoro pre-warm skipped: {_e}", flush=True)
    threading.Thread(target=_prewarm_kokoro, daemon=True, name="kokoro-prewarm").start()

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

# MCP Remote Control router
try:
    from backend.routers.mcp_remote_router import mcp_remote_router
    app.include_router(mcp_remote_router)
    print("[main] MCP remote router mounted at /mcp-remote", flush=True)
except ImportError as _mcp_err:
    print(f"[main] MCP remote router not available: {_mcp_err}", flush=True)

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
app.include_router(audio_tools.router)
app.include_router(animation.router)
app.include_router(jobs.router)
app.include_router(export_.router)
app.include_router(search.router)
app.include_router(context.router)
app.include_router(debug.router)    # animation diagnostics: /debug/anim-*
app.include_router(scene_tools.router)  # scene search / clip description tools
app.include_router(virality.router)  # virality predictor + social connections

 
from fastapi.responses import FileResponse as _FileResponse
import pathlib as _pathlib

_RUNTIME_JS = _RESOURCE_ROOT / "templates" / "webcomps" / "_runtime" / "fade-react.js"

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
