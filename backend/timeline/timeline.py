from __future__ import annotations
import uuid
from backend.timeline.tracks.baseTrack import BaseTrack


class Timeline:
    

    def __init__(self, name: str = "Sequence 01") -> None:
        self.timelineId = str(uuid.uuid4())
        self.name = name
        self.tracks: list[BaseTrack] = []
        self.playheadFrame: int = 0

    # Track management  

    def addTrack(self, track: BaseTrack) -> None:
        self.tracks.append(track)

    def removeTrack(self, trackId: str) -> None:
        self.tracks = [t for t in self.tracks if t.trackId != trackId]

    def getTrack(self, trackId: str) -> BaseTrack | None:
        return next((t for t in self.tracks if t.trackId == trackId), None)

    def moveTrack(self, trackId: str, newIndex: int) -> None:
        """Reorder a track — e.g. drag-and-drop in the UI."""
        track = self.getTrack(trackId)
        if track is None:
            return
        self.tracks.remove(track)
        self.tracks.insert(newIndex, track)

    #   Rendering  

    def render(self, canvas, frame: int) -> None:
        
        for track in reversed(self.tracks):
            if not track.muted:
                track.render(canvas, frame)

    #   Serialization  

    def toDict(self) -> dict:
        return {
            "timelineId": self.timelineId,
            "name": self.name,
            "playheadFrame": self.playheadFrame,
            "tracks": [t.toDict() for t in self.tracks],
        }

    @classmethod
    def fromDict(cls, data: dict) -> "Timeline":
        t = cls(name=data["name"])
        t.timelineId = data["timelineId"]
        t.playheadFrame = data.get("playheadFrame", 0)
      
        return t

    def __repr__(self) -> str:
        return (
            f"Timeline({self.name!r}, "
            f"{len(self.tracks)} tracks, "
            f"frame={self.playheadFrame})"
        )
