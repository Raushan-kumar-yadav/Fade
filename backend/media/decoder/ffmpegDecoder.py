 
from __future__ import annotations
import subprocess
import os
import json
from dataclasses import dataclass
from typing import Optional


#   Bundled executable paths  

_HERE = os.path.dirname(os.path.abspath(__file__))
_FFDIR = os.path.join(_HERE, "ffmpeg")
_FFMPEG  = os.path.join(_FFDIR, "ffmpeg.exe")
_FFPROBE = os.path.join(_FFDIR, "ffprobe.exe")

# Subprocess environment: prepend _FFDIR so avcodec-61.dll etc. are found
def _ffenv() -> dict:
    env = os.environ.copy()
    env["PATH"] = _FFDIR + ";" + env.get("PATH", "")
    return env

_ENV: dict = _ffenv()


#   Decoded frame container  

@dataclass
class DecodedFrameFF:
    """Immutable decoded video frame (BGRA packed, ready for skia.MakeN32Premul)."""
    frameNumber: int
    width: int
    height: int
    dataRGBA: bytes   # BGRA 
    valid: bool = True


# Metadata probe 
 
def _parse_rate(s: str) -> float:
    """Parse '60000/1001' or '60' into a float fps."""
    if not s or s == "0/0":
        return 30.0
    if "/" in s:
        num, den = s.split("/", 1)
        d = int(den)
        return int(num) / d if d else 30.0
    return float(s)


def _probe(filepath: str) -> dict:
    """
    Run bundled ffprobe.exe to get video stream metadata.
    Pure subprocess — no Python FFmpeg bindings, no Skia DLL conflict.
    """
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


# Decoder  

class FFmpegVideoDecoder:
    """
    Frame-accurate video decoder using ffmpeg.exe subprocess.

    Keeps a single persistent ffmpeg process for sequential forward reads.
    Restarts the process on seeks.  ALWAYS drains / terminates the subprocess
    before returning data to the caller so no pipe activity runs alongside Skia.
    """

    SEEK_FWD_THRESH = 30   # restart on jumps > this many frames

    def __init__(self, filepath: str, fps: float = 0.0) -> None:
        # Init ALL attributes first so __del__ never hits AttributeError
        self._filepath = filepath
        self._proc: Optional[subprocess.Popen] = None
        self._last_frame: int  = -1
        self._fps = fps or 30.0
        self._width = 1920
        self._height = 1080
        self._total_frames = 0
        self._frame_bytes  = self._width * self._height * 4

        # Probe  
        info = _probe(filepath)
        self._fps = info["fps"]
        self._width = info["width"]
        self._height = info["height"]
        self._total_frames  = info["nb_frames"] or int(round(info["duration"] * self._fps))
        self._frame_bytes   = self._width * self._height * 4

        print(
            f"[FFmpegDecoder] {filepath}: "
            f"{self._width}x{self._height} @ {self._fps:.3f}fps "
            f"({self._total_frames} frames)"
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
         
        need_restart = (
            self._proc is None or
            frame_number < self._last_frame or
            frame_number > self._last_frame + self.SEEK_FWD_THRESH
        )

        if need_restart:
            self._stop_process()
            self._start_process(frame_number)

        return self._read_until(frame_number)

    def close(self) -> None:
        self._stop_process()

    def __del__(self) -> None:
        self.close()

    # Internal  

    def _start_process(self, from_frame: int) -> None:
        """Start a new ffmpeg process from approximately from_frame."""
        start_sec = max(0.0, (from_frame - 2) / self._fps)  # 2-frame buffer before target

        cmd = [_FFMPEG, "-loglevel", "error"]

        if start_sec > 0.5:
            cmd += ["-ss", f"{start_sec:.6f}"]

        cmd += [
            "-i", self._filepath,
            "-an", # drop audio
            "-vf", f"fps={self._fps}",
            "-pix_fmt",  "bgra",          # BGRA = skia MakeN32Premul on Windows
            "-f", "rawvideo",
            "pipe:1",
        ]

        self._proc = subprocess.Popen(
            cmd, 
            stdout = subprocess.PIPE,
            stderr = subprocess.DEVNULL,
            bufsize = self._frame_bytes * 4,
            env = _ENV,
        )
        # The sequential  
        self._last_frame = max(-1, from_frame - 3)

    def _stop_process(self) -> None:
        """Terminate the running ffmpeg process and wait for it to exit."""
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
        Read frames from the pipe until we reach target frame number.
        Drops frames before target (they're already decoded, just discarded).
        Terminates the process cleanly before returning.
        """
        if self._proc is None:
            return None

        result: Optional[DecodedFrameFF] = None

        while True:
            raw = self._proc.stdout.read(self._frame_bytes)
            if not raw or len(raw) < self._frame_bytes:
                 
                break

            self._last_frame += 1
            cur = self._last_frame

            if cur < target:
                continue   # drop this frame

            # Found our target frame
            result = DecodedFrameFF(
                frameNumber = cur,
                width = self._width,
                height = self._height,
                dataRGBA = raw,
                valid = True,
            )
            break

      
        self._stop_process()
        return result
