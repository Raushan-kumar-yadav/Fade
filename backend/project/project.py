from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json
import uuid


@dataclass
class ProjectSettings:
    outputPath: str = ""
    codec: str = "libx264"
    crf: int = 18
    preset: str = "fast"
    audioCodec: str = "aac"
    audioBitrate: str = "192k"


class Project:
    VERSION = "1.0"

    def __init__(
        self,
        name: str = "Untitled Project",
        width: int = 1920,
        height: int = 1080,
        fps: float = 30.0,
        totalFrame: int   = 1800,
    ) -> None: 
        self.projectId  = str(uuid.uuid4())
        self.name = name
        self.width = width
        self.height = height
        self.fps = fps
        self.totalFrame = totalFrame    
        self.filePath:  str | None = None
        self.isDirty    = False
        self.timelines: list = []       
        self.settings   = ProjectSettings()

    # Derived properties  

    @property
    def durationSeconds(self) -> float:
        return self.totalFrame / self.fps

    @property
    def aspectRatio(self) -> float:
        return self.width / self.height

    #   Serialization  

    def toDict(self) -> dict:
        return {
            "version": self.VERSION,
            "projectId": self.projectId,
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "totalFrame":  self.totalFrame,
            "settings": {
                "outputPath": self.settings.outputPath,
                "codec": self.settings.codec,
                "crf": self.settings.crf,
                "preset": self.settings.preset,
                "audioCodec": self.settings.audioCodec,
                "audioBitrate": self.settings.audioBitrate,
            },
        }

    @classmethod
    def fromDict(cls, data: dict) -> "Project":
        p = cls(
            name = data["name"],
            width = data["width"],
            height = data["height"],
            fps = data["fps"],
            totalFrame = data.get("totalFrame", data.get("totalFrames", 1800)),
        )
        p.projectId = data["projectId"]
        s = data.get("settings", {})
        p.settings = ProjectSettings(**s) if s else ProjectSettings()
        return p

    def save(self, path: str | None = None) -> str:
        savePath = path or self.filePath
        if not savePath:
            raise ValueError("No file path set")
        Path(savePath).parent.mkdir(parents=True, exist_ok=True)
        Path(savePath).write_text(json.dumps(self.toDict(), indent=2), encoding="utf-8")
        self.filePath = savePath
        self.isDirty  = False
        return savePath

    @classmethod
    def load(cls, path: str) -> "Project":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        p = cls.fromDict(data)
        p.filePath = path
        return p

    def __repr__(self) -> str:
        return (
            f"Project({self.name!r}, "
            f"{self.width}x{self.height} @ {self.fps}fps, "
            f"{self.durationSeconds:.1f}s)"
        )