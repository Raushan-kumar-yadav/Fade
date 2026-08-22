 
from __future__ import annotations
import threading
import queue
import time
import struct
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.compositor.compositor import Compositor
    from backend.timeline.timeline import Timeline


# Number of pre-composited frames 
LOOKAHEAD = 4


class _ReadyFrame:
    __slots__ = ("frame_num", "data")

    def __init__(self, frame_num: int, data: bytes) -> None:
        self.frame_num = frame_num
        self.data      = data


_SENTINEL = object()


class RenderPipeline:
     

    def __init__(
        self,
        compositor: "Compositor",
        total_frames: int,
        fps: float,
    ) -> None:
        self._compositor = compositor
        self._total_frames = total_frames
        self._fps = fps

        # Ring buffer 
        self._ready: queue.Queue[_ReadyFrame | object] = queue.Queue(maxsize=LOOKAHEAD + 1)

        # Shared state with the engine  
        self._lock = threading.Lock()
        self._target_frame = 0     
        self._playing = False
        self._seek_version = 0
        self._speed: float = 1.0          # playback rate multiplier
        self._in_point: int | None = None  # loop region start (None = disabled)
        self._out_point: int | None = None # loop region end
        self._frame_accum: float = 0.0    # fractional frame accumulator for sub-1x speed

         
        self._timeline: Optional["Timeline"] = None

        self._stopped = False
        self._thread  = threading.Thread(
            target=self._worker,
            name="RenderPipeline",
            daemon=True,
        )
        self._thread.start()

    #   Engine API  

    def set_timeline(self, tl: "Timeline") -> None:
        changed = False
        with self._lock:
            if self._timeline is not tl:
                self._timeline = tl
                changed = True
        if changed:
            self._flush()


    def notify_play(self, frame: int) -> None:
        with self._lock:
            self._target_frame = frame
            self._playing      = True
            self._seek_version += 1
            self._frame_accum  = 0.0
        self._flush()

    def notify_pause(self) -> None:
        with self._lock:
            self._playing = False
            self._seek_version += 1
        self._flush()

    def notify_seek(self, frame: int) -> None:
        with self._lock:
            self._target_frame = frame
            self._seek_version += 1
            self._frame_accum  = 0.0
        self._flush()

    def set_speed(self, speed: float) -> None:
        """Set playback speed (0.25–4.0). Thread-safe."""
        with self._lock:
            self._speed = max(0.1, min(4.0, speed))
            self._frame_accum = 0.0

    def set_in_out(self, in_point: int | None, out_point: int | None) -> None:
        """Set loop in/out points. Pass None to disable looping."""
        with self._lock:
            self._in_point  = in_point
            self._out_point = out_point

    def advance_playhead(self) -> None:
        """Called by engine after consuming a frame. Advances by speed frames,
        loops at out-point if set, or wraps at total_frames."""
        with self._lock:
            if not self._playing:
                return
            # Accumulate fractional frames for sub-1x speeds
            self._frame_accum += self._speed
            steps = int(self._frame_accum)
            self._frame_accum -= steps
            if steps < 1:
                return  # not yet time to advance

            next_frame = self._target_frame + steps
            # Loop region: bounce back to in_point when out_point reached
            if self._out_point is not None and next_frame > self._out_point:
                next_frame = self._in_point if self._in_point is not None else 0
            elif next_frame >= self._total_frames:
                next_frame = 0
                self._playing = False
            self._target_frame = next_frame

    def get_frame(self, timeout: float = 0.0) -> Optional[_ReadyFrame]:
        """Non-blocking fetch of the next ready frame. Returns None if empty."""
        try:
            item = self._ready.get_nowait()
            if item is _SENTINEL:
                return None
            return item   
        except queue.Empty:
            return None

    def get_frame_blocking(self, timeout: float = 0.05) -> Optional[_ReadyFrame]:
         
        try:
            item = self._ready.get(timeout=timeout)
            if item is _SENTINEL:
                return None
            return item   
        except queue.Empty:
            return None

    def stop(self) -> None:
        self._stopped = True
        self._flush()
        self._thread.join(timeout=2.0)

    #   Internal  

    def _flush(self) -> None:
         
        try:
            while True:
                self._ready.get_nowait()
        except queue.Empty:
            pass

    def _worker(self) -> None:
        while not self._stopped:
            with self._lock:
                tl = self._timeline
                playing = self._playing
                target  = self._target_frame
                version = self._seek_version

            if tl is None:
                time.sleep(0.02)
                continue

            # if paused 
            frames_to_render = LOOKAHEAD if playing else 1

            rendered = 0
            while rendered < frames_to_render and not self._stopped:
                # skip current frame if seeked 
                with self._lock:
                    if self._seek_version != version:
                        break
                    frame = self._target_frame + rendered

                if frame >= self._total_frames:
                    break

                # dont over fill the buffer 
                if self._ready.full():
                    # seek 
                    time.sleep(0.002)
                    with self._lock:
                        if self._seek_version != version:
                            break
                    continue

                try:
                    data = self._compositor.compositeFramePng(tl, frame)
                    fmt_byte = 1 if self._compositor.getPreviewFormat() == 'png' else 0
                    header = struct.pack('>IB', frame, fmt_byte)
                    ready = _ReadyFrame(frame, header + data)

                    # skip this if race condition 
                    try:
                        self._ready.put_nowait(ready)
                        rendered += 1
                    except queue.Full:
                        pass

                except Exception as e:
                    print(f"[RenderPipeline] frame {frame} error: {e}")
                    rendered += 1  # skip damaged frame

            if not playing:
                # Paused 
                time.sleep(0.03)
