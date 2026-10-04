"""
bg_remove/service.py — Local background removal using rembg + OpenCV + FFmpeg.

Supports:
  - Single image (sync, fast)
  - Video (async, frame-by-frame with progress updates)

Models (via rembg):
  u2net        — best quality,  ~180MB download on first use
  u2netp       — fast+small,    ~4MB,  good for video
  isnet-general-use — newest, best detail
  silueta      — balanced speed/quality
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

# ── Constants ─────────────────────────────────────────────────────────────────

MODELS = {
    "u2net":              "u2net",
    "u2netp":             "u2netp",
    "isnet":              "isnet-general-use",
    "silueta":            "silueta",
}

DEFAULT_IMAGE_MODEL = "u2net"
DEFAULT_VIDEO_MODEL = "u2netp"   # faster for frame-by-frame

# Output goes into a sibling "bg_removed" folder next to source
OUTPUT_DIR = Path(__file__).parent.parent.parent / "bg_removed"
OUTPUT_DIR.mkdir(exist_ok=True)


# ── Image removal (sync) ──────────────────────────────────────────────────────

def remove_background_image(
    input_path: str,
    model_key: str = DEFAULT_IMAGE_MODEL,
    output_path: str | None = None,
) -> str:
    """
    Remove background from a single image.
    Returns the path to the output PNG (with alpha).
    """
    from rembg import remove, new_session

    in_path = Path(input_path)
    if not in_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")

    model_name = MODELS.get(model_key, model_key)

    if output_path is None:
        stem = in_path.stem
        out = OUTPUT_DIR / f"{stem}_nobg_{model_key}.png"
    else:
        out = Path(output_path)

    out.parent.mkdir(parents=True, exist_ok=True)

    session = new_session(model_name)
    with open(in_path, "rb") as f:
        data = f.read()

    result = remove(data, session=session)
    out.write_bytes(result)
    print(f"[BgRemove] Image done: {out}", flush=True)
    return str(out)


# ── Video removal (async with progress) ───────────────────────────────────────

def remove_background_video(
    input_path: str,
    model_key: str = DEFAULT_VIDEO_MODEL,
    output_format: str = "webm",    # webm (alpha) or mp4 (green-screen)
    workers: int = 4,
    progress_cb: Callable[[float, str], None] | None = None,
    cancelled_fn: Callable[[], bool] | None = None,
) -> str:
    """
    Remove background from every frame of a video.
    Returns path to output file.

    progress_cb(pct: float, message: str) — called during processing
    cancelled_fn() → bool                 — return True to abort
    """
    from rembg import remove, new_session

    in_path = Path(input_path)
    if not in_path.exists():
        raise FileNotFoundError(f"Video not found: {input_path}")

    model_name = MODELS.get(model_key, model_key)
    job_id     = str(uuid.uuid4())[:8]
    tmp_dir    = Path(tempfile.mkdtemp(prefix=f"bg_remove_{job_id}_"))
    out_stem   = OUTPUT_DIR / f"{in_path.stem}_nobg_{model_key}_{job_id}"

    def _prog(pct, msg):
        if progress_cb:
            progress_cb(pct, msg)
        print(f"[BgRemove] {pct:.0f}% — {msg}", flush=True)

    try:
        # ── 1. Open video ───────────────────────────────────────────────────
        cap = cv2.VideoCapture(str(in_path))
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video: {input_path}")

        fps    = cap.get(cv2.CAP_PROP_FPS) or 24.0
        total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        _prog(2, f"Opened video: {width}x{height} @ {fps}fps, {total} frames")

        # ── 2. Extract frames ───────────────────────────────────────────────
        frames_dir = tmp_dir / "frames_in"
        frames_dir.mkdir()
        out_dir    = tmp_dir / "frames_out"
        out_dir.mkdir()

        frame_paths = []
        idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            p = frames_dir / f"frame_{idx:05d}.png"
            cv2.imwrite(str(p), frame)
            frame_paths.append(p)
            idx += 1
        cap.release()

        total_frames = len(frame_paths)
        _prog(10, f"Extracted {total_frames} frames")

        # ── 3. Remove background per frame ─────────────────────────────────
        session = new_session(model_name)
        done_count = 0

        def _process_frame(fp: Path) -> Path:
            out_fp = out_dir / fp.name
            with open(fp, "rb") as f:
                result = remove(f.read(), session=session)
            out_fp.write_bytes(result)
            return out_fp

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_process_frame, fp): fp for fp in frame_paths}
            for fut in as_completed(futures):
                if cancelled_fn and cancelled_fn():
                    pool.shutdown(wait=False, cancel_futures=True)
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                    raise RuntimeError("Cancelled by user")
                fut.result()  # re-raise any exception
                done_count += 1
                pct = 10 + (done_count / total_frames) * 75
                _prog(pct, f"Processed frame {done_count}/{total_frames}")

        _prog(85, "Reassembling video…")

        # ── 4. Reassemble with FFmpeg ───────────────────────────────────────
        if output_format == "webm":
            out_file = str(out_stem) + ".webm"
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-framerate", str(fps),
                "-i", str(out_dir / "frame_%05d.png"),
                "-c:v", "libvpx-vp9",
                "-pix_fmt", "yuva420p",
                "-b:v", "0", "-crf", "30",
                out_file,
            ]
        else:
            # mp4 with green-screen compositing
            out_file = str(out_stem) + ".mp4"
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-framerate", str(fps),
                "-i", str(out_dir / "frame_%05d.png"),
                "-vf", "colorchannelmixer=aa=1,format=yuv420p",
                "-c:v", "libx264", "-crf", "18",
                out_file,
            ]

        proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg failed:\n{proc.stderr[-500:]}")

        # ── 5. Try to merge original audio ─────────────────────────────────
        final_file = str(out_stem) + f"_final.{output_format}"
        merge_cmd = [
            "ffmpeg", "-y",
            "-i", out_file,
            "-i", str(in_path),
            "-c:v", "copy",
            "-c:a", "aac",
            "-map", "0:v:0",
            "-map", "1:a:0?",     # ? = optional (no audio track = ok)
            "-shortest",
            final_file,
        ]
        merge_proc = subprocess.run(merge_cmd, capture_output=True, text=True)
        if merge_proc.returncode == 0:
            os.unlink(out_file)
            result_path = final_file
        else:
            result_path = out_file   # no audio, still valid

        _prog(100, f"Done! Output: {result_path}")
        return result_path

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Job registry (in-memory) ───────────────────────────────────────────────────

_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def _new_job(job_type: str, input_path: str) -> str:
    job_id = str(uuid.uuid4())[:12]
    with _lock:
        _jobs[job_id] = {
            "job_id":     job_id,
            "type":       job_type,
            "input_path": input_path,
            "status":     "pending",
            "progress":   0.0,
            "message":    "Queued",
            "output_path": None,
            "error":      None,
            "created_at": time.time(),
        }
    return job_id


def _update_job(job_id: str, **kw):
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(kw)


def get_job(job_id: str) -> dict | None:
    with _lock:
        return dict(_jobs[job_id]) if job_id in _jobs else None


def list_jobs() -> list[dict]:
    with _lock:
        return [dict(j) for j in _jobs.values()]


_cancelled: set[str] = set()


def cancel_job(job_id: str):
    _cancelled.add(job_id)
    _update_job(job_id, status="cancelling", message="Cancellation requested…")


def _is_cancelled(job_id: str) -> bool:
    return job_id in _cancelled


# ── Start async video job ─────────────────────────────────────────────────────

def start_video_job(
    input_path: str,
    model_key: str = DEFAULT_VIDEO_MODEL,
    output_format: str = "webm",
    workers: int = 4,
) -> str:
    """Submit a video background removal job. Returns job_id immediately."""
    job_id = _new_job("video_bg_remove", input_path)

    def _run():
        _update_job(job_id, status="running", progress=2, message="Starting…")
        try:
            result = remove_background_video(
                input_path=input_path,
                model_key=model_key,
                output_format=output_format,
                workers=workers,
                progress_cb=lambda pct, msg: _update_job(
                    job_id, progress=pct, message=msg),
                cancelled_fn=lambda: _is_cancelled(job_id),
            )
            _update_job(job_id, status="done", progress=100,
                        message="Complete", output_path=result)
        except RuntimeError as e:
            if "Cancelled" in str(e):
                _update_job(job_id, status="cancelled", message="Cancelled")
                _cancelled.discard(job_id)
            else:
                _update_job(job_id, status="failed", error=str(e),
                            message=f"Error: {str(e)[:120]}")
        except Exception as e:
            _update_job(job_id, status="failed", error=str(e),
                        message=f"Error: {str(e)[:120]}")
            print(f"[BgRemove] Job {job_id} failed: {e}", flush=True)

    threading.Thread(target=_run, daemon=True, name=f"bg_remove_{job_id}").start()
    return job_id
