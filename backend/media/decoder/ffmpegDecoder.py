 
from __future__ import annotations
import subprocess
import os
import json
from dataclasses import dataclass
from typing import Optional


# Bundled executable paths  

_HERE = os.path.dirname(os.path.abspath(__file__))
_FFDIR   = os.path.join(_HERE, "ffmpeg")
_FFMPEG  = os.path.join(_FFDIR, "ffmpeg.exe")
_FFPROBE = os.path.join(_FFDIR, "ffprobe.exe")


def _ffenv() -> dict:
    """Subprocess env: prepend _FFDIR so avcodec-61.dll etc. are found."""
    env = os.environ.copy()
    env["PATH"] = _FFDIR + ";" + env.get("PATH", "")
    return env


_ENV: dict = _ffenv()


# Decoded frame container  

@dataclass
class DecodedFrameFF:
    """BGRA frame ready for skia.ImageInfo.MakeN32Premul on Windows."""
    frameNumber: int
    width: int
    height: int
    dataRGBA: bytes    
    valid: bool = True


#   Metadata probe  

def _parse_rate(s: str) -> float:
    if not s or s == "0/0":
        return 30.0
    if "/" in s:
        num, den = s.split("/", 1)
        d = int(den)
        return int(num) / d if d else 30.0
    return float(s)


def _probe(filepath: str) -> dict:
    """Run ffprobe subprocess to get video stream metadata."""
    cmd = [
        _FFPROBE, "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-select_streams", "v:0",
        filepath,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, env=_ENV)
    stdout = result.stdout.strip()
    if not stdout:
        raise RuntimeError(
            f"ffprobe failed for {filepath!r}\n"
            f"  rc={result.returncode}  stderr={result.stderr[:300]}"
        )
    data    = json.loads(stdout)
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
    }


 
class FFmpegVideoDecoder:
    

 
     
    SEEK_FWD_THRESH: int = 120    

    def __init__(self, filepath: str, fps: float = 0.0, scale_factor: float = 0.5) -> None:
        # Init all 
        self._filepath = filepath
        self._scale_factor = max(0.125, min(1.0, scale_factor))
        self._proc: Optional[subprocess.Popen] = None
        self._last_frame:  int  = -1
        self._fps = fps or 30.0
        self._width = 1920
        self._height = 1080
        self._total_frames = 0
        self._frame_bytes  = self._width * self._height * 4

        info = _probe(filepath)
        self._fps = info["fps"]
        self._width_src = info["width"]
        self._height_src = info["height"]
        # Apply scale factor 
        self._width  = max(2, round(info["width"]  * self._scale_factor) // 2 * 2)
        self._height = max(2, round(info["height"] * self._scale_factor) // 2 * 2)
        self._total_frames = info["nb_frames"] or int(round(info["duration"] * self._fps))
        self._frame_bytes  = self._width * self._height * 4

        pct = int(self._scale_factor * 100)
        print(
            f"[FFmpegDecoder] {filepath}: "
            f"{self._width_src}x{self._height_src} @ {self._fps:.3f}fps "
            f"({self._total_frames} frames) [preview {pct}%: {self._width}x{self._height}]"
        )

    # Public API  

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

    def stopSubprocess(self) -> None:
         
        pass

    def close(self) -> None:
        self._stop_process()

    def __del__(self) -> None:
        self.close()

 
    def _start_process(self, from_frame: int) -> None:
        """Start ffmpeg from just before from_frame (keyframe seek)."""
        start_sec = max(0.0, (from_frame - 2) / self._fps)

        cmd = [
            _FFMPEG,
            "-loglevel", "error",
            "-hwaccel", "none",
        ]

        # Input options (must come BEFORE -i):
        if start_sec > 0.5:
            cmd += ["-ss", f"{start_sec:.6f}"]

        cmd += ["-i", self._filepath]

        # Output options (must come AFTER -i):
        if self._scale_factor < 1.0:
            cmd += ["-vf", f"scale={self._width}:{self._height}"]

        cmd += [
            "-an",
            "-pix_fmt", "bgra",
            "-f", "rawvideo",
            "pipe:1",
        ]


        self._proc = subprocess.Popen(
            cmd,
            stdout = subprocess.PIPE,
            stderr = subprocess.DEVNULL,
            # Large pipe buffer 
            bufsize = self._frame_bytes * 8,
            env     = _ENV,
        )
        # Frame counter: 2 frames before target  
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
        """
        Read frames from the pipe until we reach target.
        Process stays alive after this returns.
        """
        if self._proc is None:
            return None

        while True:
            raw = self._proc.stdout.read(self._frame_bytes)
            if not raw or len(raw) < self._frame_bytes:
                self._stop_process()    
                return None

            self._last_frame += 1
            if self._last_frame < target:
                continue   

            return DecodedFrameFF(
                frameNumber = self._last_frame,
                width = self._width,
                height = self._height,
                dataRGBA = raw,
                valid = True,
            )
