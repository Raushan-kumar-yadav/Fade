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
        clipId: str  = "",
        startFrame: int  = 0,
        duration: int  = 90,
        assetId: str  = "",
        mediaOffset: int  = 0,
        volume: float = 1.0,
        mute: bool  = False,
    ) -> None:
        super().__init__(clipId or str(uuid.uuid4()), startFrame, duration)
        self.assetId:     str   = assetId
        self.mediaOffset: int   = mediaOffset   # frame offset  
        self.volume:      float = volume
        self.mute:        bool  = mute

    def render(self, canvas, frame: int) -> None:
        pass  # audio-only: no visual render

    def getThumbnail(self, frame: int, width: int = 160, height: int = 90) -> bytes:
         
        try:
            import skia
            surface = skia.Surface(width, height)
            with surface as canvas:
                # Dark background
                canvas.clear(skia.Color4f(0.05, 0.10, 0.12, 1.0))
                # Teal waveform bar in the vertical center
                bar_h = max(4, height // 4)
                y = (height - bar_h) // 2
                paint = skia.Paint(Color=skia.Color(0x00, 0xE5, 0xCC, 0xFF))  # #00E5CC
                canvas.drawRect(skia.Rect.MakeXYWH(0, y, width, bar_h), paint)
            image = surface.makeImageSnapshot()
            data = image.encodeToData(skia.EncodedImageFormat.kJPEG, 85)
            return bytes(data)
        except Exception:
            # Fallback: return a tiny valid 1x1 JPEG
            return (
                b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
                b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t'
                b'\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a'
                b'\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\x1e\xc0'
                b'\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f'
                b'\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00'
                b'\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4'
                b'\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04'
                b'\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa'
                b'\x07"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br'
                b'\x82\t\n\x16\x17\x18\x19\x1a%&\'()*456789:CDEFGHIJ'
                b'STUVWXYZ\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xf5(\xa2\x8a'
                b'\xff\xd9'
            )

    def toDict(self) -> dict:
        filepath = ""
        try:
            from backend.state import _library
            filepath = _library[self.assetId].filepath if self.assetId in _library else ""
        except Exception:
            pass
        return {
            "clipType": self.CLIP_TYPE,
            "clipId": self.clipId,
            "startFrame":  self.startFrame,
            "duration": self.duration,
            "assetId": self.assetId,
            "filepath": filepath,
            "mediaOffset": self.mediaOffset,
            "volume": self.volume,
            "mute": self.mute,
        }

    @classmethod
    def fromDict(cls, data: dict) -> "AudioClip":
        c = cls(
            clipId = data.get("clipId", ""),
            startFrame  = data.get("startFrame", 0),
            duration = data.get("duration", 90),
            assetId = data.get("assetId", ""),
            mediaOffset = data.get("mediaOffset", 0),
            volume = data.get("volume", 1.0),
            mute = data.get("mute", False),
        )
        # Store filepath so asset library 
        c.filepath = data.get("filepath", "")
        return c

    def __repr__(self) -> str:
        return f"AudioClip({self.clipId[:8]}… asset={self.assetId[:8]}… @{self.startFrame}+{self.duration})"
