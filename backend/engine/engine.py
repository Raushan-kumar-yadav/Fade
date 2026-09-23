from __future__ import annotations
import asyncio
import struct
from backend.project.project import Project
from backend.timeline.timeline import Timeline
from backend.compositor.compositor import Compositor
from backend.compositor.renderPipeline import RenderPipeline
from backend.media.scheduler.decodeScheduler import DecodeScheduler
from backend.history.commandStack import CommandStack


class Engine:

    def __init__(self) -> None:
        self.project: Project | None = None
        self.compositor: Compositor | None = None
        self.scheduler: DecodeScheduler | None = None

        self._playing = False
        self._currentFrame = 0
        self._speed: float = 1.0           
        self._inPoint: int  | None = None   
        self._outPoint: int | None = None   

        self.commandStack: CommandStack = CommandStack()

        self._pipeline: RenderPipeline | None = None
        self._lastTimelineId: int = 0
        self._active_comp_id: str | None = None  # None = root

    # Project lifecycle  

    def newProject(
        self,
        name: str = "Untitled Project",
        width: int = 1920,
        height: int = 1080,
        fps: float  = 30.0,
    ) -> Project:
        self._stop_pipeline()
        self.project = Project(name=name, width=width, height=height, fps=fps)
        self.scheduler = DecodeScheduler()
        self.compositor = Compositor(width=width, height=height, fps=fps)
        self.compositor.setScheduler(self.scheduler)
        self.project.timelines.append(Timeline("Main Timeline"))
        return self.project

    def createComposition(
        self,
        name: str = "Composition",
        width: int = 1920,
        height: int = 1080,
        fps: float = 30.0,
        total_frames: int = 900,
    ) -> "Timeline":
        if self.project is None:
            raise RuntimeError("No active project")
        from backend.timeline.tracks.videoTrack import VideoTrack
        from backend.timeline.tracks.audioTrack import AudioTrack
        import uuid
        comp = Timeline(name)
        comp.width = width
        comp.height = height
        comp.fps = fps
        comp.totalFrames = total_frames
         
        v = VideoTrack(name="Video 1")
        v.trackId = str(uuid.uuid4())
        a = AudioTrack(name="Audio 1")
        a.trackId = str(uuid.uuid4())
        comp.tracks.append(v)
        comp.tracks.append(a)
        self.project.timelines.append(comp)
        return comp

    def getTimeline(self, timelineId: str) -> "Timeline | None":
         
        if self.project is None:
            return None
        for tl in self.project.timelines:
            if tl.timelineId == timelineId:
                return tl
        return None

    def deleteComposition(self, timelineId: str) -> bool:
         
        if self.project is None:
            return False
        root_id = self.project.timelines[0].timelineId if self.project.timelines else ""
        if timelineId == root_id:
            return False  # root
        before = len(self.project.timelines)
        self.project.timelines = [t for t in self.project.timelines if t.timelineId != timelineId]
        return len(self.project.timelines) < before


    def loadProject(self, path: str) -> Project:
        self._stop_pipeline()
        self.project = Project.load(path)
        if self.project.timelines:
            self.scheduler  = DecodeScheduler()
            self.compositor = Compositor(
                width  = self.project.width,
                height = self.project.height,
                fps = self.project.fps,
            )
            self.compositor.setScheduler(self.scheduler)
        return self.project

    def saveProject(self, path: str | None = None) -> str:
        if self.project is None:
            raise RuntimeError("No active project")
        return self.project.save(path)

    # Helpers  

    def setActiveComp(self, compId: str | None) -> None:
        """Switch the active composition. None = root.
        Also updates the render pipeline so the new timeline renders immediately."""
        self._active_comp_id = compId
        tl = self.activeTimeline  # already updated by line above
        if tl is not None and self._pipeline is not None:
            self._pipeline.set_timeline(tl)
            # seek to frame 0 so the first frame renders without needing play
            self._currentFrame = 0
            self._pipeline.notify_seek(0)

    @property
    def activeTimeline(self) -> Timeline | None:
        
        if self.project is None or not self.project.timelines:
            return None
        if self._active_comp_id:
            tl = self.getTimeline(self._active_comp_id)
            if tl is not None:
                return tl
        return self.project.timelines[0]

    @property
    def rootTimeline(self) -> Timeline | None:
        """Always return the root timeline regardless of active comp."""
        if self.project and self.project.timelines:
            return self.project.timelines[0]
        return None

    @property
    def currentFrame(self) -> int:
        return self._currentFrame

    #   Playback control  

    def play(self) -> None:
        self._playing = True
        if self._pipeline:
            self._pipeline.notify_play(self._currentFrame)

    def pause(self) -> None:
        self._playing = False
        if self._pipeline:
            self._pipeline.notify_pause()

    def seek(self, frame: int) -> None:
        if self.project:
            self._currentFrame = max(0, min(frame, self.project.totalFrame - 1))
        if self._pipeline:
            self._pipeline.notify_seek(self._currentFrame)

    def togglePlay(self) -> None:
        if self._playing:
            self.pause()
        else:
            self.play()

    def setSpeed(self, speed: float) -> None:
        """Set playback speed multiplier: 0.25, 0.5, 1.0, 2.0."""
        self._speed = max(0.1, min(4.0, speed))
        if self._pipeline:
            self._pipeline.set_speed(self._speed)

    def setInPoint(self, frame: int | None) -> None:
        self._inPoint = frame
        if self._pipeline:
            self._pipeline.set_in_out(self._inPoint, self._outPoint)

    def setOutPoint(self, frame: int | None) -> None:
        self._outPoint = frame
        if self._pipeline:
            self._pipeline.set_in_out(self._inPoint, self._outPoint)

    #    Pipeline management  

    def _stop_pipeline(self) -> None:
        if self._pipeline:
            self._pipeline.stop()
            self._pipeline = None

    def _ensure_pipeline(self) -> None:
        if self._pipeline is not None:
            return
        if self.compositor is None or self.project is None:
            return
        tl = self.activeTimeline
        self._pipeline = RenderPipeline(
            compositor = self.compositor,
            total_frames = self.project.totalFrame,
            fps = self.project.fps,
        )
        if tl:
            self._pipeline.set_timeline(tl)
            self._pipeline.notify_seek(self._currentFrame)

     

    async def startPreviewLoop(self) -> None:
         
        while True:
            await asyncio.sleep(3600)  # sleep forever

    # Single-frame API  

    def renderFramePng(self, frame: int) -> bytes:
        if self.compositor is None or self.activeTimeline is None:
            return b""
        return self.compositor.compositeFramePng(self.activeTimeline, frame)

    def renderThumbnail(self, frame: int, w: int = 320, h: int = 180) -> bytes:
        if self.compositor is None or self.activeTimeline is None:
            return b""
        return self.compositor.renderThumbnail(self.activeTimeline, frame, w, h)

    # Preview scale  

    def setPreviewScale(self, scale: float) -> None:
        if self.compositor is None or self.scheduler is None:
            return
        new_scale = max(0.125, min(1.0, scale))
        self.scheduler._previewScale = new_scale
        for clipId in list(self.scheduler._pumpToContent.keys()):
            contentId = self.scheduler._pumpToContent.get(clipId, "")
            self.scheduler._decoderPool.reopen(clipId, new_scale)
            with self.scheduler._lock:
                self.scheduler._lastDecoded[clipId]  = -1
                self.scheduler._targetFrames[clipId] = 0
            if contentId:
                self.scheduler._frameCache.evictClip(contentId)
         
        if self._pipeline:
            self._pipeline.notify_seek(self._currentFrame)
        print(f"[Engine] Preview scale -> {new_scale} ({int(new_scale*100)}%)")

    def getPreviewScale(self) -> float:
        if self.scheduler is None:
            return 1.0
        return getattr(self.scheduler, '_previewScale', 1.0)

    def setPreviewFormat(self, fmt: str) -> None:
        if self.compositor:
            self.compositor.setPreviewFormat(fmt)
        if self._pipeline:
            self._pipeline.notify_seek(self._currentFrame)

    def getPreviewFormat(self) -> str:
        if self.compositor:
            return self.compositor.getPreviewFormat()
        return 'jpeg'

    def perfStats(self) -> dict:
        if self.compositor is None:
            return {}
        return self.compositor.perfStats()

    def __repr__(self) -> str:
        proj = self.project.name if self.project else "None"
        return f"Engine(project={proj!r}, frame={self._currentFrame}, playing={self._playing})"
