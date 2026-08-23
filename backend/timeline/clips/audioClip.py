from __future__ import annotations
import uuid
from backend.timeline.clips.baseClip import BaseClip


class AudioClip(BaseClip):
    """
    A clip on an AudioTrack — references a media asset by assetId.
    The browser AudioEngine streams it directly via /assets/{assetId}/stream.
    """

    CLIP_TYPE = "audio"

    def __init__(
        self,
        clipId:      str  = "",
        startFrame:  int  = 0,
        duration:    int  = 90,
        assetId:     str  = "",
        mediaOffset: int  = 0,
        volume:      float = 1.0,
        mute:        bool  = False,
    ) -> None:
        super().__init__(clipId or str(uuid.uuid4()), startFrame, duration)
        self.assetId:     str   = assetId
        self.mediaOffset: int   = mediaOffset   # frame offset into the source media
        self.volume:      float = volume
        self.mute:        bool  = mute

    def render(self, canvas, frame: int) -> None:
        pass  # audio-only: no visual render

    def toDict(self) -> dict:
        return {
            "clipType":    self.CLIP_TYPE,
            "clipId":      self.clipId,
            "startFrame":  self.startFrame,
            "duration":    self.duration,
            "assetId":     self.assetId,
            "mediaOffset": self.mediaOffset,
            "volume":      self.volume,
            "mute":        self.mute,
        }

    @classmethod
    def fromDict(cls, data: dict) -> "AudioClip":
        return cls(
            clipId      = data.get("clipId", ""),
            startFrame  = data.get("startFrame", 0),
            duration    = data.get("duration", 90),
            assetId     = data.get("assetId", ""),
            mediaOffset = data.get("mediaOffset", 0),
            volume      = data.get("volume", 1.0),
            mute        = data.get("mute", False),
        )

    def __repr__(self) -> str:
        return f"AudioClip({self.clipId[:8]}… asset={self.assetId[:8]}… @{self.startFrame}+{self.duration})"
