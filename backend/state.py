from backend.engine.engine import Engine
from backend.media.asset.mediaAsset import MediaAsset

engine: Engine = Engine()

_library: dict[str, MediaAsset] = {}
_clipTrackMap: dict[str, int] = {}
_exportJobs: dict[str, object] = {}
_selected_clip_id: str | None = None
# Multi-select: all currently selected clipIds from the frontend
_selected_clip_ids: set[str] = set()

# WebComp export frame cache — Electron pre-renders and pushes RGBA frames here
# so the Python fallback encoder can composite WebComp clips via Skia.
# Keys: (webcompId: str, frame: int)  Values: {"rgba": bytes, "width": int, "height": int}
_webcompExportCache: dict[tuple, dict] = {}

