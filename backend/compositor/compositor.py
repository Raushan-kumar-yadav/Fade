from __future__ import annotations
import threading
import time
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING
import skia

from backend.rendering.graph.graphBuilder import GraphBuilder
from backend.rendering.renderContext import RenderContext

if TYPE_CHECKING:
    from backend.timeline.timeline import Timeline
    from backend.timeline.clips.videoClip import VideoClip
    from backend.media.scheduler.decodeScheduler import DecodeScheduler
    from backend.media.decoder.decodedFrame import DecodedFrame


# Frames within this window of the playhead are decoded proactively
WAKE_RADIUS = 120

# Prefetch look-ahead when playing — 60 = 2s at 30fps, 1s at 60fps
PREFETCH_RADIUS = 60




@dataclass
class _PerfStats:
    tickMs: float = 0.0
    uploadMs: float = 0.0
    renderMs: float = 0.0
    decodeWaitMs: float = 0.0
    fps: float = 0.0
    activeClips:  int   = 0
    cacheEntries: int   = 0


class Compositor:
    

    def __init__(self, width: int, height: int, fps: float = 30.0) -> None:
        self.width  = width
        self.height = height
        self.fps    = fps

       
        self._surface: "skia.Surface | None" = None



         
        self._activeClipIds: set[str] = set()

        # DecodeScheduler  
        self._scheduler: Optional[DecodeScheduler] = None

        # Pending timeline swap  
        self._pendingTimeline: Optional[Timeline] = None
        self._pendingLock = threading.Lock()

        # Render lock 
        self._renderLock = threading.Lock()

        # Perf stats
        self._stats = _PerfStats()
        self._fpsCount = 0
        self._fpsT0 = time.monotonic()
        # JPEG quality for preview stream (adjustable via /settings)
        self._jpegQuality: int = 85

    # API  

    def setScheduler(self, scheduler: "DecodeScheduler") -> None:
        self._scheduler = scheduler

    def compositeFramePng(
        self,
        timeline: "Timeline",
        frame: int,
        quality: int   = 85,   # JPEG quality 1-100 (PNG fallback uses this too)
        panX: float = 0.0,
        panY: float = 0.0,
        zoom: float = 1.0,
    ) -> bytes:
        """Main preview composite method.

        Uses JPEG encoding for the WebSocket preview stream — 7ms vs 46ms for
        PNG at 960x540.  The compositor output is always opaque (clips with
        alpha are composited internally by Skia onto the black background), so
        JPEG transparency loss is irrelevant for preview.
        """
        t0 = time.monotonic()

        self._applyPendingTimeline()

        if timeline is None:
            return b""

        # Determine preview scale — drives both surface size and clip scaling
        scale = getattr(self._scheduler, '_previewScale', 1.0) if self._scheduler else 1.0
        if scale < 1.0:
            pw = max(2, round(self.width  * scale) // 2 * 2)
            ph = max(2, round(self.height * scale) // 2 * 2)
        else:
            pw, ph = self.width, self.height

        with self._renderLock:
            self._syncClipRegistrations(timeline, frame)
            t_upload = time.monotonic()

            img = self._renderFrameAtSize(timeline, frame, pw, ph, panX, panY, zoom)
            t_render = time.monotonic()

            # JPEG: 7ms at 960x540 vs PNG 46ms — 6x faster, fine for opaque preview
            q      = quality if quality != 85 else self._jpegQuality
            data   = img.encodeToData(skia.kJPEG, q)
            result = bytes(data)

        self._updateStats(t0, t_upload, t_render)
        return result


    def renderThumbnail(
        self,
        timeline: "Timeline",
        frame: int,
        width: int = 320,
        height: int = 180,
        quality: int = 3,
    ) -> bytes:
        with self._renderLock:
            img  = self._renderFrame(timeline, frame)
        info  = skia.ImageInfo.MakeN32Premul(width, height)
        thumb = img.resize(info.width(), info.height())
        if thumb is None:
            thumb = img
        data = thumb.encodeToData(skia.kPNG, quality)
        return bytes(data)

    def resize(self, width: int, height: int) -> None:
        if width != self.width or height != self.height:
            self.width    = width
            self.height   = height
            self._surface = None  # recreated lazily on next _renderFrame call


    @staticmethod
    def _makeSurface(width: int, height: int) -> skia.Surface:
        """Create a CPU raster surface with explicit ImageInfo (never nullptr)."""
        info = skia.ImageInfo.MakeN32Premul(max(1, width), max(1, height))
        surf = skia.Surface.MakeRaster(info)
        if surf is None:
            raise RuntimeError(f"skia.Surface.MakeRaster({width}x{height}) failed")
        return surf

    def setTimeline(self, timeline: "Timeline") -> None:
       
        with self._pendingLock:
            self._pendingTimeline = timeline

    def perfStats(self) -> dict:
        return {
            "tickMs": round(self._stats.tickMs, 2),
            "uploadMs": round(self._stats.uploadMs, 2),
            "renderMs": round(self._stats.renderMs, 2),
            "decodeWaitMs": round(self._stats.decodeWaitMs, 2),
            "fps": round(self._stats.fps, 1),
            "activeClips":  self._stats.activeClips,
            "cacheEntries": self._scheduler._frameCache.entryCount if self._scheduler else 0,
            "cacheUsedMB": round(self._scheduler._frameCache.usedMB, 2) if self._scheduler else 0.0,
        }

    def recordDecodeWait(self, milliseconds: float) -> None:
        self._stats.decodeWaitMs = max(0.0, milliseconds)

    def isFrameReady(self, timeline: "Timeline", frame: int) -> bool:
        """Return whether every visible video clip has its requested frame cached."""
        if self._scheduler is None:
            return True

        for track in timeline.tracks:
            if getattr(track, "muted", False):
                continue
            if getattr(track, "isAudio", lambda: False)():
                continue
            for clip in track.clips:
                if not clip.overlaps(frame) or not getattr(clip, "assetId", None):
                    continue
                localFrame = clip.sourceFrame(frame)
                decoded = self._scheduler.tryGetFrame(clip.assetId, localFrame)
                if not (decoded and decoded.valid):
                    return False
        return True

    #   Internal  

    def _syncClipRegistrations(self, timeline: "Timeline", frame: int) -> None:
        
        if self._scheduler is None:
            return

        currentIds: set[str] = set()

        for track in timeline.tracks:
            if getattr(track, 'muted', False):
                continue
            if getattr(track, 'isAudio', lambda: False)():
                continue

            for clip in track.clips:
                isNear = (
                    frame >= clip.startFrame - WAKE_RADIUS and
                    frame <= clip.endFrame   + WAKE_RADIUS
                )

                if isNear:
                    currentIds.add(clip.clipId)
                    if clip.clipId not in self._activeClipIds:
                        self._registerClip(clip)

        # Unregister clips that left the window
        leaving = self._activeClipIds - currentIds
        for clipId in leaving:
            self._scheduler.unregisterClip(clipId)
        self._activeClipIds = currentIds
        self._stats.activeClips  = len(self._activeClipIds)

    def _registerClip(self, clip) -> None:
        from backend.timeline.clips.videoClip import VideoClip
        if not isinstance(clip, VideoClip):
            return
        if not clip.assetId:
            return
         
        if hasattr(clip, '_scheduler') and clip._scheduler is not None:
            self._activeClipIds.add(clip.clipId)
        elif self._scheduler is not None:
            self._activeClipIds.add(clip.clipId)

    # Internal 

    def _prefetchActiveClips(self, timeline: "Timeline", frame: int) -> None:
         
        from backend.timeline.clips.videoClip import VideoClip

        for track in timeline.tracks:
            if getattr(track, 'muted', False):
                continue
            for clip in track.clips:
                if not isinstance(clip, VideoClip) or not clip.assetId:
                    continue
                if not clip.overlaps(frame):
                    continue
                localFrame = clip.sourceFrame(frame)
                self._scheduler.prefetchAround(clip.clipId, localFrame, PREFETCH_RADIUS)

    def prefetchForFrame(self, timeline: "Timeline", frame: int) -> None:
       
        if self._scheduler is None or timeline is None:
            return
        self._syncClipRegistrations(timeline, frame)
        self._prefetchActiveClips(timeline, frame)

    # Internal  

    def _renderFrame(
        self,
        timeline: "Timeline",
        frame: int,
        panX: float = 0.0,
        panY: float = 0.0,
        zoom: float = 1.0,
    ) -> skia.Image:
        return self._renderFrameAtSize(timeline, frame, self.width, self.height, panX, panY, zoom)

    def _renderFrameAtSize(
        self,
        timeline: "Timeline",
        frame: int,
        pw: int,
        ph: int,
        panX: float = 0.0,
        panY: float = 0.0,
        zoom: float = 1.0,
    ) -> skia.Image:
        """Render directly into a pw×ph surface.

        All clip coordinates are in full project space (self.width × self.height).
        canvas.scale(sx, sy) maps them to pw×ph automatically — one Skia pass,
        no intermediate surface or blit needed.
        """
        info = skia.ImageInfo.MakeN32Premul(max(2, pw), max(2, ph))
        surf = skia.Surface.MakeRaster(info)
        if surf is None:
            # Fallback to cached surface
            if self._surface is None:
                self._surface = self._makeSurface(self.width, self.height)
            surf = self._surface

        canvas = surf.getCanvas()
        canvas.clear(skia.Color4f(0, 0, 0, 1))

        if not timeline.tracks:
            return surf.makeImageSnapshot()

        if self._scheduler:
            self._injectScheduler(timeline)

        # Scale canvas so full-project coordinates map to preview size
        sx = pw / self.width
        sy = ph / self.height
        if sx != 1.0 or sy != 1.0:
            canvas.scale(sx, sy)

        # Apply pan/zoom on top of scale
        if zoom != 1.0 or panX != 0.0 or panY != 0.0:
            canvas.translate(panX, panY)
            canvas.scale(zoom, zoom)

        # DAG build + execute
        graph = GraphBuilder.build(timeline, frame)
        graph.compile()

        ctx = RenderContext(
            canvas = canvas,
            frame = frame,
            width = self.width,
            height = self.height,
            fps = self.fps,
            panX = panX,
            panY = panY,
            zoom = zoom,
            scheduler = self._scheduler,
        )
        graph.execute(ctx)

        return surf.makeImageSnapshot()


    def _injectScheduler(self, timeline: "Timeline") -> None:
        
        from backend.timeline.clips.videoClip import VideoClip
        for track in timeline.tracks:
            for clip in track.clips:
                if isinstance(clip, VideoClip) and clip._scheduler is None:
                    clip.setScheduler(self._scheduler, self.fps)
                    if clip.assetId and clip.clipId not in self._activeClipIds:
                         self._activeClipIds.add(clip.clipId)

    #   Internal 

    @staticmethod
    def buildSkiaImage(decoded: "DecodedFrame") -> Optional[skia.Image]:
        
        if decoded is None or not decoded.valid:
            return None
        info  = skia.ImageInfo.MakeN32Premul(decoded.width, decoded.height)
        data  = skia.Data.MakeWithCopy(decoded.dataRGBA)
        return skia.Image.MakeRasterData(info, data, decoded.width * 4)

    #   Internal 

    def _applyPendingTimeline(self) -> None:
        
        with self._pendingLock:
            pending = self._pendingTimeline
            self._pendingTimeline = None

        if pending is None:
            return

        # Clear all clip-level state for the old timeline
        if self._scheduler:
            for clipId in self._activeClipIds:
                self._scheduler.unregisterClip(clipId)

        self._activeClipIds.clear()
        self._imageCache.clear()
        self._surface = skia.Surface(self.width, self.height)

    #   Perf  

    def _updateStats(self, t0: float, t_upload: float, t_render: float) -> None:
        now = time.monotonic()
        self._stats.tickMs   = (now - t0) * 1000.0
        self._stats.uploadMs = (t_upload  - t0) * 1000.0
        self._stats.renderMs = (t_render  - t_upload)  * 1000.0

        self._fpsCount += 1
        elapsed = now - self._fpsT0
        if elapsed >= 1.0:
            self._stats.fps  = self._fpsCount / elapsed
            self._fpsCount = 0
            self._fpsT0 = now
