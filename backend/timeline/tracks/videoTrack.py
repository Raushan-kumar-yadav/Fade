from __future__ import annotations
from backend.timeline.tracks.baseTrack import BaseTrack
from backend.timeline.clips.baseClip import BaseClip


class VideoTrack(BaseTrack):
     

    TRACK_TYPE = "video"

    def __init__(self, name: str = "Video Track") -> None:
        super().__init__(name)
        self.opacity: float = 1.0   

    def render(self, canvas, frame: int) -> None:
        if self.muted:
            return
        clip = self.clipAt(frame)
        if clip is None:
            return

        # Render the clip pixels
        clip.render(canvas, frame)

   
        for effect in clip.effects:
            if effect.enabled:
                effect.apply(canvas, frame)

    def toDict(self) -> dict:
        d = self._baseDict()
        d["type"] = self.TRACK_TYPE
        d["opacity"] = self.opacity
        return d

    @classmethod
    def fromDict(cls, data: dict) -> "VideoTrack":
        from backend.timeline.clips.videoClip import VideoClip
        t = cls(name=data["name"])
        t._applyBaseDict(data)
        t.opacity = data.get("opacity", 1.0)
        for clipData in data.get("clips", []):
            t.clips.append(VideoClip.fromDict(clipData))
        return t
