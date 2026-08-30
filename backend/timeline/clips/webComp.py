from __future__ import annotations
import uuid
from backend.timeline.clips.baseClip import BaseClip


class WebCompClip(BaseClip):
     

    CLIP_TYPE = "webcomp"

    def __init__(
        self,
        clipId: str = "",
        startFrame: int = 0,
        duration: int = 150,
        webcompId: str = "",
        mediaOffset: int = 0,
    ) -> None:
        super().__init__(
            clipId or str(uuid.uuid4()),
            startFrame,
            duration,
        )
        self.webcompId = webcompId    
        self.mediaOffset = mediaOffset
        self._runtimeParams: dict = {}  

    # Timeline helpers

    def sourceFrame(self, timelineFrame: int) -> int:
         
        return max(0, (timelineFrame - self.startFrame) + self.mediaOffset)

    # BaseClip abstract implementations
    def render(self, canvas, frame: int) -> None:
        
        pass

    def getThumbnail(self, frame: int, width: int = 160, height: int = 90) -> bytes:
         
        return b""

    # Serialization
    def toDict(self) -> dict:
        return {
            "type": self.CLIP_TYPE,
            "clipId": self.clipId,
            "startFrame": self.startFrame,
            "duration": self.duration,
            "webcompId": self.webcompId,
            "mediaOffset": self.mediaOffset,
            "runtimeParams": self._runtimeParams,
            "transform": self.transform.toDict(),
            "effects": [e.toDict() for e in self.effects],
        }

    @classmethod
    def fromDict(cls, data: dict) -> "WebCompClip":
        from backend.animation.transform import Transform
        from backend.timeline.effects.skslEffect import SkslEffect
        c = cls(
            clipId=data["clipId"],
            startFrame=data["startFrame"],
            duration=data["duration"],
            webcompId=data.get("webcompId", ""),
            mediaOffset=data.get("mediaOffset", 0),
        )
        c._runtimeParams = data.get("runtimeParams", {})
        if "transform" in data:
            c.transform = Transform.fromDict(data["transform"])
        # Restore effects
        for ed in data.get("effects", []):
            t = ed.get("type", "")
            if t.startswith("sksl:") or "typeId" in ed:
                try:
                    c.effects.append(SkslEffect.fromDict(ed))
                except Exception as ex:
                    print(f"[WebCompClip] effect restore failed: {ex}")
        return c
