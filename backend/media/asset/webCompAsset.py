from __future__ import annotations
import os
import json
import uuid
from pathlib import Path
from backend.media.asset.baseAsset import BaseAsset, MediaType


class WebCompAsset(BaseAsset):
    """
    A WebComp asset is a folder on disk containing index.html, style.css,
    script.js, and webcomp.json. It gets rendered to RGBA pixels by
    Electron's offscreen BrowserWindow.
    """

    def __init__(
        self,
        assetId: str = "",
        name: str = "Untitled WebComp",
        folderPath: str = "",
        width: int = 1920,
        height: int = 1080,
        fps: float = 30.0,
        durationFrames: int = 150,
    ) -> None:
        super().__init__(assetId or str(uuid.uuid4()), folderPath, name)
        self.name = name
        self.folderPath = folderPath
        self.width = width
        self.height = height
        self.fps = fps
        self.durationFrames = durationFrames
        self._params: list[dict] = []

    @property
    def mediaType(self) -> MediaType:
        return MediaType.webcomp

    @property
    def entryHtmlPath(self) -> str:
        """Full path to index.html."""
        return os.path.join(self.folderPath, "index.html")

    @property
    def hasValidFolder(self) -> bool:
        return os.path.isdir(self.folderPath) and os.path.isfile(self.entryHtmlPath)

    @property
    def params(self) -> list[dict]:
        """Load params from webcomp.json."""
        if not self._params:
            self._loadMeta()
        return self._params

    def _loadMeta(self) -> None:
        meta_path = os.path.join(self.folderPath, "webcomp.json")
        if os.path.isfile(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.width = data.get("width", self.width)
            self.height = data.get("height", self.height)
            self.fps = data.get("fps", self.fps)
            self.durationFrames = data.get("durationFrames", self.durationFrames)
            self._params = data.get("params", [])

    def saveMeta(self) -> None:
        """Write webcomp.json metadata to disk."""
        os.makedirs(self.folderPath, exist_ok=True)
        meta_path = os.path.join(self.folderPath, "webcomp.json")
        data = {
            "name": self.name,
            "version": "1.0",
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "durationFrames": self.durationFrames,
            "entry": "index.html",
            "params": self._params,
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def buildHtmlUrl(self) -> str:
        """Return a file:// URL for the entry HTML."""
        return Path(self.entryHtmlPath).resolve().as_uri()

    # Serialization

    def toDict(self) -> dict:
        return {
            "assetId": self.assetId,
            "name": self.name,
            "folderPath": self.folderPath,
            "type": "webcomp",
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "durationFrames": self.durationFrames,
        }

    @classmethod
    def fromDict(cls, data: dict) -> "WebCompAsset":
        return cls(
            assetId=data["assetId"],
            name=data.get("name", "WebComp"),
            folderPath=data.get("folderPath", ""),
            width=data.get("width", 1920),
            height=data.get("height", 1080),
            fps=data.get("fps", 30.0),
            durationFrames=data.get("durationFrames", 150),
        )
