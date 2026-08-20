from __future__ import annotations
import asyncio
from backend.project.project import Project
from backend.timeline.timeline import Timeline
from backend.compositor.compositor import Compositor
from backend.media.scheduler.decodeScheduler import DecodeScheduler


class Engine:
    
    def __init__(self) -> None:
        self.project: Project | None    = None
        self.compositor: Compositor | None = None
        self.scheduler: DecodeScheduler | None = None

        self._playing = False
        self._currentFrame = 0

        self.frameQueue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=3)
        self._loopTask: asyncio.Task | None   = None

    # Project lifecycle  

    def newProject(
        self,
        name: str = "Untitled Project",
        width: int  = 1920,
        height: int = 1080,
        fps: float  = 30.0,
    ) -> Project:
        self.project = Project(name=name, width=width, height=height, fps=fps)
        self.scheduler = DecodeScheduler()
        self.compositor = Compositor(width=width, height=height, fps=fps)
        self.compositor.setScheduler(self.scheduler)
        self.project.timelines.append(Timeline("Main Timeline"))
        return self.project

    def loadProject(self, path: str) -> Project:
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

    # Active timeline shortcut  

    @property
    def activeTimeline(self) -> Timeline | None:
        if self.project and self.project.timelines:
            return self.project.timelines[0]
        return None

    # Playback control  

    @property
    def currentFrame(self) -> int:
        return self._currentFrame

    def play(self) -> None:
        self._playing = True

    def pause(self) -> None:
        self._playing = False

    def seek(self, frame: int) -> None:
        if self.project:
            self._currentFrame = max(
                0, min(frame, self.project.totalFrame - 1)
            )

    def togglePlay(self) -> None:
        if self._playing:
            self.pause()
        else:
            self.play()

    #   Preview loop    

    async def startPreviewLoop(self) -> None:
        if self.project is None or self.compositor is None:
            return

        interval    = 1.0 / self.project.fps
        _skip_count = 0

        while True:
            t0 = asyncio.get_event_loop().time()

            if self.activeTimeline:
                try:
                    jpeg = await asyncio.to_thread(
                        self.compositor.compositeFrameJpeg,
                        self.activeTimeline,
                        self._currentFrame,
                    )
                    _skip_count = 0
                    try:
                        self.frameQueue.put_nowait(jpeg)
                    except asyncio.QueueFull:
                        pass  # drop frame — consumer is slow

                    # Advance frame only when playing
                    if self._playing:
                        self._currentFrame += 1
                        if self._currentFrame >= self.project.totalFrame:
                            self._currentFrame = 0
                            self._playing = False

                except Exception as exc:
                    _skip_count += 1
                    if _skip_count <= 3:
                        print(f"[Engine] render error frame {self._currentFrame}: {exc}")
                    await asyncio.sleep(interval)
                    continue

            elapsed = asyncio.get_event_loop().time() - t0
            # When paused: run at 10 fps to save CPU; when playing: full fps
            target_interval = interval if self._playing else 0.1
            await asyncio.sleep(max(0.0, target_interval - elapsed))


    #   Single frame  

    def renderFrameJpeg(self, frame: int) -> bytes:
        if self.compositor is None or self.activeTimeline is None:
            return b""
        return self.compositor.compositeFrameJpeg(self.activeTimeline, frame)

    def renderThumbnail(self, frame: int, w: int = 320, h: int = 180) -> bytes:
        if self.compositor is None or self.activeTimeline is None:
            return b""
        return self.compositor.renderThumbnail(self.activeTimeline, frame, w, h)

    def perfStats(self) -> dict:
        if self.compositor is None:
            return {}
        return self.compositor.perfStats()

    def __repr__(self) -> str:
        proj = self.project.name if self.project else "None"
        return f"Engine(project={proj!r}, frame={self._currentFrame}, playing={self._playing})"
