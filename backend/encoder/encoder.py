from __future__ import annotations
import os
import subprocess
import threading
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.compositor.compositor import Compositor
    from backend.timeline.timeline import Timeline


# ──────────────────────────────────────────────────────────────────────────────
# Encoder auto-detection
# ──────────────────────────────────────────────────────────────────────────────

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


# ──────────────────────────────────────────────────────────────────────────────
# ExportJob — tracks state of one export run
# ──────────────────────────────────────────────────────────────────────────────

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


# ──────────────────────────────────────────────────────────────────────────────
# Main export runner — called from background thread
# ──────────────────────────────────────────────────────────────────────────────

def run_export(job: ExportJob, compositor: "Compositor", timeline: "Timeline") -> None:
    s               = job.settings
    width           = s.get("width",           1920)
    height          = s.get("height",          1080)
    fps             = s.get("fps",             30.0)
    codec           = s.get("codec",           "auto")
    vbr             = s.get("videoBitrate",    "8M")
    crf             = s.get("crf",             -1)
    preset          = s.get("preset",          "medium")
    abr             = s.get("audioBitrate",    "192k")
    audio_sr        = s.get("audioSampleRate", 48000)
    audio_ch        = s.get("audioChannels",   2)
    out             = s.get("outputPath",      "output.mp4")

    if codec == "auto":
        codec = _cached_encoder()

    # Compute total frames
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

    # Ensure the output directory exists — FFmpeg cannot create parent directories
    out_dir = os.path.dirname(os.path.abspath(out))
    os.makedirs(out_dir, exist_ok=True)

    tmp_video = os.path.join(out_dir, f".fade_tmp_{uuid.uuid4().hex[:8]}.mp4")

    # Build FFmpeg video encode command
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-vcodec",  "rawvideo",
        "-pix_fmt", "rgba",
        "-s", f"{width}x{height}",
        "-r", str(fps),
        "-i", "pipe:0",
        "-c:v", codec,
        "-pix_fmt", "yuv420p",
    ]

    # Quality mode: CRF preferred over bitrate for CPU encoders
    cpu_encoders = ("libx264", "libx265")
    if crf >= 0 and codec in cpu_encoders:
        ffmpeg_cmd += ["-crf", str(crf), "-preset", preset]
    else:
        ffmpeg_cmd += ["-b:v", vbr]
        if codec in cpu_encoders:
            ffmpeg_cmd += ["-preset", preset]

    ffmpeg_cmd += ["-movflags", "+faststart", tmp_video]

    try:
        proc = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
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

        _mux_audio_v2(tmp_video, out, timeline, fps, abr, audio_sr, audio_ch)
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


 
def _mux_audio_v2(
    video_path: str,
    out_path: str,
    timeline: "Timeline",
    fps: float,
    abr: str,
    sample_rate: int = 48000,
    channels: int = 2,
) -> None:
     
    from backend.state import _library
    from backend.timeline.clips.audioClip import AudioClip

    audio_clips: list[dict] = []

    for track in timeline.tracks:
        # Skip muted tracks
        if getattr(track, "muted", False):
            continue
        for clip in track.clips:
            from backend.timeline.clips.audioClip import AudioClip
            from backend.timeline.clips.videoClip import VideoClip
            if not isinstance(clip, (AudioClip, VideoClip)):
                continue
            if getattr(clip, "mute", False):
                continue

            # Resolve asset file path  
            asset = _library.get(getattr(clip, "assetId", ""))
            
            if isinstance(clip, VideoClip):
                if not asset or not getattr(asset, "hasAudio", False):
                    continue

            filepath: str | None = None
            if asset:
                filepath = getattr(asset, "filepath", None) or getattr(asset, "filePath", None)
            if not filepath:
                # fromDict() stores  
                filepath = getattr(clip, "filepath", None)
            if not filepath or not os.path.exists(filepath):
                continue

            start_sec  = clip.startFrame / fps
            offset_sec = getattr(clip, "mediaOffset", 0) / fps
            dur_sec = clip.duration / fps
            volume = float(getattr(clip, "volume", 1.0))

            audio_clips.append({
                "path": filepath,
                "start_sec":  start_sec,
                "offset_sec": offset_sec,
                "dur_sec": dur_sec,
                "volume": volume,
            })

    # No audio  
    if not audio_clips:
        os.rename(video_path, out_path)
        return

    # Build FFmpeg command with complex filter graph
    inputs = ["-i", video_path]
    for c in audio_clips:
        inputs += ["-i", c["path"]]

    filter_parts: list[str] = []
    mix_labels:   list[str] = []

    for i, c in enumerate(audio_clips):
        src = f"[{i + 1}:a]"
        label = f"[ac{i}]"
        delay_ms = int(c["start_sec"] * 1000)
        offset_sec = c["offset_sec"]
        dur_sec = c["dur_sec"]
        vol = c["volume"]

        chain = (
            f"{src}"
             
            f"atrim=start={offset_sec:.6f}:duration={dur_sec:.6f},"
             
            f"asetpts=PTS-STARTPTS,"
             
            f"adelay={delay_ms}|{delay_ms},"
            # Apply per-clip volume
            f"volume={vol:.6f}"
            f"{label}"
        )
        filter_parts.append(chain)
        mix_labels.append(label)

    # Mix all streams; normalize=0 keeps absolute volumes
    n = len(audio_clips)
    mix_inputs = "".join(mix_labels)
    filter_parts.append(
        f"{mix_inputs}amix=inputs={n}:duration=longest:normalize=0[aout]"
    )
    filter_graph = ";".join(filter_parts)

    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex", filter_graph,
        "-map",  "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a",  "aac",
        "-b:a", abr,
        "-ar", str(sample_rate),
        "-ac",   str(channels),
        out_path,
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        # Fallback 
        print(f"[encoder] _mux_audio_v2 failed: {result.stderr.decode(errors='replace')[-400:]}")
        try:
            os.rename(video_path, out_path)
        except Exception:
            pass



