from __future__ import annotations
from backend.timeline.tracks.baseTrack import BaseTrack


class AudioTrack(BaseTrack):
    

    TRACK_TYPE = "audio"

    def __init__(self, name: str = "Audio Track") -> None:
        super().__init__(name)
        self.volume: float = 1.0  
        self.pan: float = 0.0    

    def render(self, canvas, frame: int) -> None:
        pass  

    def toDict(self) -> dict:
        d = self._baseDict()
        d["type"]   = self.TRACK_TYPE
        d["volume"] = self.volume
        d["pan"] = self.pan
        return d

    @classmethod
    def fromDict(cls, data: dict) -> "AudioTrack":
        t = cls(name=data["name"])
        t._applyBaseDict(data)
        t.volume = data.get("volume", 1.0)
        t.pan = data.get("pan", 0.0)
        return t
