from __future__ import annotations
import subprocess
import os
import json
import threading
from dataclasses import dataclass
from typing import Optional


_HERE = os.path.dirname(os.path.abspath(__file__))
_FFDIR = os.path.join(_HERE, "ffmpeg")
_FFMPEG = os.path.join(_FFDIR, "ffmpeg.exe")
_FFPROBE= os.path.join(_FFDIR, "ffprobe.exe")


def _ffenv() -> dict:
    env = os.environ.copy()
    env["PATH"] = _FFDIR + ";" + env.get("PATH", "")
    return env


_ENV: dict = _ffenv()


@dataclass
class DecodedFrameFF:

    frameNumber: int
    width:  int
    height: int
    dataRGBA: bytes
    valid: bool = True


# ffprobe metadata  

def _parse_rate(s: str) -> float:
    if not s or s == "0/0":
        return 30.0
    if "/" in s:
        num, den = s.split("/", 1)
        d = int(den)
        return int(num) / d if d else 30.0
    return float(s)


def _probe(filepath: str) -> dict:
    cmd = [
        _FFPROBE, "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-select_streams", "v:0",
        filepath,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, env=_ENV)
    stdout = result.stdout.strip()
    if not stdout:
        raise RuntimeError(f"ffprobe failed for {filepath!r}\n  stderr={result.stderr[:300]}")
    data = json.loads(stdout)
    streams = data.get("streams", [])
    if not streams:
        raise RuntimeError(f"No video stream in {filepath!r}")
    s     = streams[0]
    r_str = s.get("r_frame_rate") or s.get("avg_frame_rate", "30/1")
    fps = _parse_rate(r_str)
    nb = int(s.get("nb_frames") or 0)
    dur = float(s.get("duration") or 0.0)
    return {
        "fps": fps,
        "width": int(s.get("width",  1920)),
        "height": int(s.get("height", 1080)),
        "nb_frames": nb,
        "duration":  dur,
        "codec": s.get("codec_name", "h264"),
    }


#   Hardware accelerator probe 

class _HwProbe:
     
    _lock   = threading.Lock()
    _result: Optional[str] = None

    @classmethod
    def best(cls, filepath: str, w: int, h: int, fps: float) -> str:
        with cls._lock:
            if cls._result is not None:
                return cls._result
            cls._result = cls._probe(filepath, w, h, fps)
            print(f"[HwProbe] Selected decoder: {cls._result}")
            return cls._result

    @classmethod
    def _time_cmd(cls, cmd: list, frame_bytes: int, n_frames: int = 10) -> float:
        import time
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                bufsize=frame_bytes * 4, env=_ENV,
            )
            buf   = bytearray(frame_bytes)
            mv    = memoryview(buf)
            t0    = time.monotonic()
            read  = 0
            for _ in range(n_frames):
                total = 0
                while total < frame_bytes:
                    n = proc.stdout.readinto(mv[total:])
                    if not n:
                        proc.terminate(); proc.wait()
                        return float("inf")
                    total += n
                read += 1
            elapsed = time.monotonic() - t0
            proc.stdout.close(); proc.terminate(); proc.wait()
            return elapsed / read   # seconds per frame
        except Exception:
            return float("inf")

    @classmethod
    def _probe(cls, filepath: str, w: int, h: int, fps: float) -> str:
        fb = w * h * 4   

        FAST_FLAGS = ["-probesize", "32768", "-analyzeduration", "0"]

        #   D3D11VA with GPU-side scale 
        d3d_scale_cmd = [
            _FFMPEG, "-loglevel", "error",
            "-hwaccel", "d3d11va",
            "-hwaccel_output_format", "d3d11",
        ] + FAST_FLAGS + [
            "-i", filepath,
            "-vf", f"scale_d3d11va=w={w}:h={h},hwdownload,format=nv12,format=bgra",
            "-f", "rawvideo", "-pix_fmt", "bgra", "pipe:1",
        ]

        #  D3D11VA auto-download 
        d3d_auto_cmd = [
            _FFMPEG, "-loglevel", "error",
            "-hwaccel", "d3d11va",
            "-threads", "0",
        ] + FAST_FLAGS + [
            "-i", filepath,
            "-vf", f"scale={w}:{h}:flags=fast_bilinear",
            "-f", "rawvideo", "-pix_fmt", "bgra", "pipe:1",
        ]

        #  pure software 
        sw_cmd = [
            _FFMPEG, "-loglevel", "error",
            "-threads", "0",
        ] + FAST_FLAGS + [
            "-i", filepath,
            "-vf", f"scale={w}:{h}:flags=fast_bilinear",
            "-f", "rawvideo", "-pix_fmt", "bgra", "pipe:1",
        ]

        t_d3d_scale = cls._time_cmd(d3d_scale_cmd, fb)
        t_d3d_auto  = cls._time_cmd(d3d_auto_cmd,  w * h * 4)  
        t_sw = cls._time_cmd(sw_cmd, fb)

        print(
            f"[HwProbe] d3d11va_scale={t_d3d_scale*1000:.1f}ms  "
            f"d3d11va_auto={t_d3d_auto*1000:.1f}ms  "
            f"software={t_sw*1000:.1f}ms"
        )

        best_t = min(t_d3d_scale, t_d3d_auto, t_sw)
        if best_t == t_d3d_scale and t_d3d_scale < float("inf"):
            return "d3d11va_scale"
        if best_t == t_d3d_auto and t_d3d_auto < float("inf"):
            return "d3d11va"
        return "software"

    @classmethod
    def reset(cls) -> None:
        """Force re-probe on next call (e.g. after settings change)."""
        with cls._lock:
            cls._result = None


# FFmpeg subprocess decoder  

class FFmpegVideoDecoder:

    SEEK_FWD_THRESH: int = 120

    def __init__(self, filepath: str, fps: float = 0.0, scale_factor: float = 0.5) -> None:
        self._filepath = filepath
        self._scale_factor = max(0.125, min(1.0, scale_factor))
        self._proc: Optional[subprocess.Popen] = None
        self._last_frame = -1
        self._fps = fps or 30.0
        self._hwmode: Optional[str] = None    

        info = _probe(filepath)
        self._fps = info["fps"]
        self._width_src = info["width"]
        self._height_src = info["height"]
        self._codec = info.get("codec", "h264")
        self._width  = max(2, round(info["width"]  * self._scale_factor) // 2 * 2)
        self._height = max(2, round(info["height"] * self._scale_factor) // 2 * 2)
        self._total_frames = info["nb_frames"] or int(round(info["duration"] * self._fps))
        self._frame_bytes  = self._width * self._height * 4
        self._read_buf     = bytearray(self._frame_bytes)

        pct = int(self._scale_factor * 100)
        print(
            f"[FFmpegDecoder] {os.path.basename(filepath)}: "
            f"{self._width_src}x{self._height_src} @ {self._fps:.3f}fps "
            f"({self._total_frames} frames) [preview {pct}%: {self._width}x{self._height}]"
        )

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    def getDurationFrames(self) -> int:
        return self._total_frames

    def decodeFrame(self, frame_number: int) -> Optional[DecodedFrameFF]:
        # Lazy hw probe
        if self._hwmode is None:
            self._hwmode = _HwProbe.best(
                self._filepath, self._width, self._height, self._fps
            )

        proc_dead = self._proc is not None and self._proc.poll() is not None
        need_restart = (
            self._proc is None
            or proc_dead
            or frame_number < self._last_frame
            or frame_number > self._last_frame + self.SEEK_FWD_THRESH
        )

        if need_restart:
            self._stop_process()
            self._start_process(frame_number)

        return self._read_until(frame_number)

    def close(self) -> None:
        self._stop_process()

    def __del__(self) -> None:
        self.close()

    # Process management  

    def _start_process(self, from_frame: int) -> None:
        start_sec = max(0.0, (from_frame - 2) / self._fps)
        mode = self._hwmode or "software"

        FAST = ["-probesize", "32768", "-analyzeduration", "0"]

        if mode == "d3d11va_scale":
            cmd = [_FFMPEG, "-loglevel", "error",
                   "-hwaccel", "d3d11va",
                   "-hwaccel_output_format", "d3d11",
                   ] + FAST
            if start_sec > 0.5:
                cmd += ["-ss", f"{start_sec:.6f}"]
            cmd += ["-i", self._filepath,
                    "-vf", f"scale_d3d11va=w={self._width}:h={self._height},hwdownload,format=nv12,format=bgra",
                    "-an", "-pix_fmt", "bgra", "-f", "rawvideo", "pipe:1"]


        elif mode == "d3d11va":
            cmd = [_FFMPEG, "-loglevel", "error",
                   "-hwaccel", "d3d11va",
                   "-threads", "0",
                   ] + FAST
            if start_sec > 0.5:
                cmd += ["-ss", f"{start_sec:.6f}"]
            vf = f"scale={self._width}:{self._height}:flags=fast_bilinear"
            cmd += ["-i", self._filepath,
                    "-vf", vf,
                    "-an", "-pix_fmt", "bgra", "-f", "rawvideo", "pipe:1"]

        else:  # software
            cmd = [_FFMPEG, "-loglevel", "error", "-threads", "0"] + FAST
            if start_sec > 0.5:
                cmd += ["-ss", f"{start_sec:.6f}"]
            cmd += ["-i", self._filepath]
            if self._scale_factor < 1.0:
                cmd += ["-vf", f"scale={self._width}:{self._height}:flags=fast_bilinear"]
            cmd += ["-an", "-pix_fmt", "bgra", "-f", "rawvideo", "pipe:1"]


        self._proc = subprocess.Popen(
            cmd,
            stdout = subprocess.PIPE,
            stderr = subprocess.DEVNULL,
            bufsize = self._frame_bytes * 8,
            env = _ENV,
        )
        self._last_frame = max(-1, from_frame - 3)

    def _stop_process(self) -> None:
        if self._proc is None:
            return
        try:
            self._proc.stdout.close()
        except Exception:
            pass
        try:
            self._proc.terminate()
            self._proc.wait(timeout=3)
        except Exception:
            try:
                self._proc.kill()
                self._proc.wait(timeout=1)
            except Exception:
                pass
        self._proc = None

    def _read_until(self, target: int) -> Optional[DecodedFrameFF]:
        if self._proc is None:
            return None

        while True:
            buf = self._read_buf
            mv  = memoryview(buf)
            total = 0
            while total < len(buf):
                n = self._proc.stdout.readinto(mv[total:])
                if not n:
                    self._stop_process()
                    return None
                total += n

            self._last_frame += 1
            if self._last_frame < target:
                continue

            return DecodedFrameFF(
                frameNumber = self._last_frame,
                width = self._width,
                height = self._height,
                dataRGBA = bytes(buf),
                valid = True,
            )
