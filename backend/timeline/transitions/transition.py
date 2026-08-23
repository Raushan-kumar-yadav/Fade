 
from __future__ import annotations
import uuid


TRANSITION_CATALOG = [
    {
        "typeId": "dissolve",
        "name": "Dissolve",
        "icon": "◌",
        "category":  "Basic",
        "desc": "Cross-dissolve blend",
        "params": [
            {"id": "softness", "displayName": "Softness",
             "type": "FloatSlider", "default": 0.0, "min": 0.0, "max": 0.5},
        ],
    },
    {
        "typeId": "fade_black",
        "name": "Fade to Black",
        "icon": "◆",
        "category": "Basic",
        "desc": "Dip to black",
        "params":   [],
    },
    {
        "typeId": "wipe_left",
        "name": "Wipe Left",
        "icon": "◁",
        "category": "Wipe",
        "desc": "Reveals from left edge",
        "params": [
            {"id": "edge_softness", "displayName": "Edge Softness",
             "type": "FloatSlider", "default": 0.02, "min": 0.0, "max": 0.1},
        ],
    },
    {
        "typeId": "wipe_right",
        "name": "Wipe Right",
        "icon": "▷",
        "category": "Wipe",
        "desc":     "Reveals from right edge",
        "params": [
            {"id": "edge_softness", "displayName": "Edge Softness",
             "type": "FloatSlider", "default": 0.02, "min": 0.0, "max": 0.1},
        ],
    },
    {
        "typeId": "zoom_in",
        "name": "Zoom In",
        "icon": "⊕",
        "category": "Motion",
        "desc": "Incoming clip zooms in from centre",
        "params": [
            {"id": "scale_start", "displayName": "Start Scale",
             "type": "FloatSlider", "default": 0.3, "min": 0.05, "max": 0.9},
        ],
    },
    {
        "typeId": "slide_left",
        "name": "Slide Left",
        "icon": "◂",
        "category": "Motion",
        "desc": "Incoming clip slides in from right",
        "params": [],
    },
]

# Map typeId 
_CATALOG_MAP: dict[str, dict] = {t["typeId"]: t for t in TRANSITION_CATALOG}


class Transition:
    """Transition between clipA (out) and clipB (in) on the same track."""

    def __init__(
        self,
        typeId: str = "dissolve",
        duration: int = 30,         
        clipA_id: str = "",
        clipB_id: str = "",
    ) -> None:
        self.transId = str(uuid.uuid4())
        self.typeId = typeId
        self.duration = max(1, duration)
        self.clipA_id = clipA_id
        self.clipB_id = clipB_id

        # Runtime param values  
        meta = _CATALOG_MAP.get(typeId, {})
        self._values: dict[str, float] = {
            p["id"]: p["default"]
            for p in meta.get("params", [])
        }

    # Geometry helpers  

    def transitionStart(self, clipA_endFrame: int) -> int:
        """First frame inside the transition zone."""
        return clipA_endFrame - self.duration

    def transitionEnd(self, clipA_endFrame: int) -> int:
        """Last frame inside the transition zone (exclusive)."""
        return clipA_endFrame

    def progress(self, frame: int, clipA_endFrame: int) -> float:
        """Normalised progress 0→1 at the given timeline frame."""
        start = self.transitionStart(clipA_endFrame)
        if self.duration <= 0:
            return 1.0
        return max(0.0, min(1.0, (frame - start) / self.duration))

    #   Param access  

    def params(self) -> dict:
        """Return {id: (value, min, max, displayName, type)} for the inspector."""
        meta = _CATALOG_MAP.get(self.typeId, {})
        out = {}
        for p in meta.get("params", []):
            pid = p["id"]
            out[pid] = {
                "value": self._values.get(pid, p["default"]),
                "min": p["min"],
                "max": p["max"],
                "type": p["type"],
                "displayName": p["displayName"],
            }
        return out

    def setParam(self, key: str, val: float) -> None:
        self._values[key] = float(val)

    #   Serialisation  

    def toDict(self) -> dict:
        return {
            "transId": self.transId,
            "typeId": self.typeId,
            "duration": self.duration,
            "clipA_id": self.clipA_id,
            "clipB_id": self.clipB_id,
            "values": dict(self._values),
        }

    @classmethod
    def fromDict(cls, data: dict) -> "Transition":
        t = cls(
            typeId   = data.get("typeId",   "dissolve"),
            duration = data.get("duration", 30),
            clipA_id = data.get("clipA_id", ""),
            clipB_id = data.get("clipB_id", ""),
        )
        t.transId = data.get("transId", t.transId)
        for k, v in data.get("values", {}).items():
            t._values[k] = float(v)
        return t
