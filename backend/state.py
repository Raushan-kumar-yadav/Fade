from backend.engine.engine import Engine
from backend.media.asset.mediaAsset import MediaAsset

engine: Engine = Engine()

_library: dict[str, MediaAsset] = {}
_clipTrackMap: dict[str, int] = {}
_exportJobs: dict[str, object] = {}
_selected_clip_id: str | None = None
