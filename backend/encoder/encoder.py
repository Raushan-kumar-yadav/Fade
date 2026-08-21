from __future__ import annotations
import os
import subprocess
import threading
import uuid
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.compositor.compositor import Compositor
    from backend.timeline.timeline import Timeline


def detect_encoder() -> str:
    candidates = ["h264_nvenc", "h264_qsv", "libx264"]
    for enc in candidates:
        try:
            r = subprocess.run(
                ["ffmpeg", "-f", "lavfi", "-i", "nullsrc=s=16x16:d=0.1",
                 "-c:v", enc, "-f", "null", "-"],
                capture_output=True, timeout=5,
            )
            if r.returncode == 0:
                return enc
        except Exception:
            pass
    return "libx264"


_ENCODER_CACHE: str | None = None


def _cached_encoder() -> str:
    global _ENCODER_CACHE
    if _ENCODER_CACHE is None:
        _ENCODER_CACHE = detect_encoder()
    return _ENCODER_CACHE


class ExportJob:
    def __init__(self, settings: dict) -> None:
        self.jobId    = str(uuid.uuid4())
        self.settings = settings
        self.frame    = 0
        self.total    = 0
        self.done     = False
        self.error: str | None = None
        self.path: str | None  = None
        self._cancel  = threading.Event()
        self._proc: subprocess.Popen | None = None

    def cancel(self) -> None:
        self._cancel.set()
        if self._proc:
            try:
                self._proc.kill()
            except Exception:
                pass

    def toDict(self) -> dict:
        pct = round(self.frame / self.total * 100) if self.total > 0 else 0
        return {
            "jobId":   self.jobId,
            "frame":   self.frame,
            "total":   self.total,
            "percent": pct,
            "done":    self.done,
            "error":   self.error,
            "path":    self.path,
        }


def run_export(job: ExportJob, compositor: "Compositor", timeline: "Timeline") -> None:
    s       = job.settings
    width   = s.get("width",  1920)
    height  = s.get("height", 1080)
    fps     = s.get("fps",    30.0)
    codec   = s.get("codec",  "auto")
    vbr     = s.get("videoBitrate", "8M")
    abr     = s.get("audioBitrate", "192k")
    out     = s.get("outputPath", "output.mp4")

    if codec == "auto":
        codec = _cached_encoder()

    total_frames = 0
    if timeline:
        for track in timeline.tracks:
            for clip in track.clips:
                total_frames = max(total_frames, clip.endFrame)
    job.total = total_frames

    if total_frames == 0:
        job.error = "Timeline is empty"
        job.done  = True
        return

    tmp_video = out + ".tmp_video.mp4"

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f",      "rawvideo",
        "-vcodec", "rawvideo",
        "-pix_fmt","rgba",
        "-s",      f"{width}x{height}",
        "-r",      str(fps),
        "-i",      "pipe:0",
        "-c:v",    codec,
        "-pix_fmt","yuv420p",
        "-b:v",    vbr,
        "-movflags","+faststart",
        tmp_video,
    ]

    try:
        proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        job._proc = proc

        for f in range(total_frames):
            if job._cancel.is_set():
                proc.kill()
                job.error = "Cancelled"
                job.done  = True
                return

            img  = compositor._renderFrameAtSize(timeline, f, width, height)
            rgba = img.toarray()
            proc.stdin.write(rgba.tobytes())
            job.frame = f + 1

        proc.stdin.close()
        proc.wait()
        job._proc = None

        if proc.returncode != 0:
            job.error = f"FFmpeg exited with code {proc.returncode}"
            job.done  = True
            return

        _mux_audio(tmp_video, out, timeline, fps, abr)
        job.path = out
        job.done = True

    except Exception as exc:
        job.error = str(exc)
        job.done  = True
    finally:
        try:
            os.remove(tmp_video)
        except Exception:
            pass


def _mux_audio(video_path: str, out_path: str, timeline: "Timeline", fps: float, abr: str) -> None:
    from backend.media.asset.mediaAsset import MediaAsset

    audio_inputs: list[str] = []
    for track in timeline.tracks:
        for clip in track.clips:
            asset_path = getattr(getattr(clip, "_asset", None), "filePath", None)
            if asset_path and os.path.exists(asset_path):
                audio_inputs.append(asset_path)
                break

    if not audio_inputs:
        os.rename(video_path, out_path)
        return

    cmd = ["ffmpeg", "-y", "-i", video_path]
    for a in audio_inputs:
        cmd += ["-i", a]
    cmd += ["-c:v", "copy", "-c:a", "aac", "-b:a", abr,
            "-shortest", out_path]
    subprocess.run(cmd, capture_output=True)
