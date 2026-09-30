"""
backend/routers/pii.py
======================
FastAPI router that exposes the FADE PII detection + sanitization API.

Endpoints:
    POST /pii/detect                    -> DetectionResult list
    POST /pii/sanitize                  -> sanitized file bytes
    POST /pii/register-sanitized        -> swap timeline refs + mark security states
    GET  /pii/security-state/{asset_id} -> current security state for an asset
"""
from __future__ import annotations

import json
import logging
import tempfile
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from backend.pii.detector  import detect_text, detect_image, detect_video
from backend.pii.sanitizer import sanitize_text, sanitize_image, sanitize_video

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pii", tags=["pii"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEXT_EXTS = {".txt", ".md", ".log", ".csv", ".json"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
_VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv"}


def _asset_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in _TEXT_EXTS:
        return "text"
    if ext in _IMAGE_EXTS:
        return "image"
    if ext in _VIDEO_EXTS:
        return "video"
    return "unknown"


# ---------------------------------------------------------------------------
# POST /pii/detect
# ---------------------------------------------------------------------------

@router.post("/detect")
async def pii_detect(
    file: UploadFile = File(...),
    use_ner: bool = Form(default=True),
) -> dict[str, Any]:
    """Run PII detection on the uploaded asset.

    Returns:
        {
            "assetType":  "text" | "image" | "video",
            "filename":   str,
            "detections": [ ...TextDetection | ImageDetection | VideoDetection ]
        }

    The source asset is NEVER modified by this endpoint.
    Detection metadata is safe to send to the FADE review UI.
    """
    filename = file.filename or "upload"
    asset_type = _asset_type(filename)

    if asset_type == "unknown":
        raise HTTPException(status_code=415, detail=f"Unsupported file type: {Path(filename).suffix}")

    raw = await file.read()
    logger.info("[/pii/detect] received %s (%d bytes, type=%s)", filename, len(raw), asset_type)

    detections: list[dict[str, Any]]

    if asset_type == "text":
        text = raw.decode("utf-8", errors="ignore")
        detections = detect_text(text, use_ner=use_ner)

    else:
        # Image / Video — need a real temp file for PIL / OpenCV
        suffix = Path(filename).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(raw)
            tmp_path = tmp.name

        try:
            if asset_type == "image":
                detections = detect_image(tmp_path)
            else:
                detections = detect_video(tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    return {
        "assetType":  asset_type,
        "filename":   filename,
        "detections": detections,
    }


# ---------------------------------------------------------------------------
# POST /pii/sanitize
# ---------------------------------------------------------------------------

@router.post("/sanitize")
async def pii_sanitize(
    file: UploadFile = File(...),
    redaction_request: str = Form(...),   # JSON-encoded RedactionRequest
) -> Response:
    """Apply the final FADE RedactionRequest to the uploaded asset.

    The ``redaction_request`` form field must be a JSON string matching:
        {
            "assetId":   str,
            "assetType": "text" | "image" | "video",
            "redactions": [
                {
                    "id":      str,
                    "type":    str,
                    "action":  "redact" | "pseudonymize",
                    "enabled": bool,
                    -- for text:
                    "start":   int,
                    "end":     int,
                    -- for image:
                    "bbox":    {"x", "y", "width", "height"},
                    "coordinateSpace": "source",
                    -- for video:
                    "frames":  {"<frame_num>": {"x", "y", "width", "height"}, ...},
                }
            ]
        }

    IMPORTANT: The sanitizer operates on the final user-approved redactions
    from FADE.  It does NOT re-run detection and does NOT ignore user edits.
    Disabled redactions (enabled=false) are completely skipped.

    Returns the sanitized asset as a file download.
    """
    try:
        req: dict[str, Any] = json.loads(redaction_request)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid redaction_request JSON: {exc}") from exc

    redactions: list[dict[str, Any]] = req.get("redactions", [])
    filename = file.filename or "upload"
    asset_type = _asset_type(filename)

    if asset_type == "unknown":
        raise HTTPException(status_code=415, detail=f"Unsupported file type: {Path(filename).suffix}")

    raw = await file.read()
    logger.info(
        "[/pii/sanitize] %s (%d bytes, type=%s, redactions=%d)",
        filename, len(raw), asset_type, len(redactions),
    )

    if asset_type == "text":
        text = raw.decode("utf-8", errors="ignore")
        cleaned = sanitize_text(text, redactions)
        return Response(
            content=cleaned.encode("utf-8"),
            media_type="text/plain",
            headers={"Content-Disposition": f'attachment; filename="sanitized_{filename}"'},
        )

    suffix = Path(filename).suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(raw)
        tmp_path = tmp.name

    try:
        if asset_type == "image":
            sanitized_bytes = sanitize_image(tmp_path, redactions)
            media_type = "image/png"
            out_name = f"sanitized_{Path(filename).stem}.png"
        else:
            sanitized_bytes = sanitize_video(tmp_path, redactions)
            media_type = "video/mp4"
            out_name = f"sanitized_{Path(filename).stem}.mp4"
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    return Response(
        content=sanitized_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{out_name}"'},
    )


# ---------------------------------------------------------------------------
# POST /pii/register-sanitized
# ---------------------------------------------------------------------------

class RegisterSanitizedRequest(BaseModel):
    originalAssetId:  str
    sanitizedAssetId: str


@router.post("/register-sanitized")
def pii_register_sanitized(req: RegisterSanitizedRequest) -> dict[str, Any]:
    """Complete the PII sanitization workflow:

    1. Mark ``originalAssetId``  as RESTRICTED in the security registry.
    2. Mark ``sanitizedAssetId`` as SANITIZED and record the link.
    3. Walk every active timeline and swap all clips whose assetId is
       ``originalAssetId`` to point at ``sanitizedAssetId`` instead.
    4. Fire SSE events so the frontend timeline and library panels refresh.

    This endpoint is called by the frontend immediately after the sanitized
    file has been uploaded to /library/upload and a new assetId is known.

    The ORIGINAL asset remains in _library for local recovery/editing but is
    now RESTRICTED and will be blocked from AI/LLM/external transmission.
    """
    from backend.pii import security as _sec
    from backend.state import engine, _library
    from backend.events import notify

    original_id  = req.originalAssetId
    sanitized_id = req.sanitizedAssetId

    # Verify both assets exist
    if original_id not in _library:
        raise HTTPException(404, f"Original asset '{original_id}' not found in library")
    if sanitized_id not in _library:
        raise HTTPException(404, f"Sanitized asset '{sanitized_id}' not found in library")

    # 1 & 2 — mark security states and link
    _sec.mark(original_id,  "RESTRICTED")
    _sec.mark(sanitized_id, "SANITIZED")
    _sec.link(original_id,  sanitized_id)

    # 3 — swap timeline clip references
    swapped_clips: list[str] = []
    timelines = engine.project.timelines if engine.project else []
    if not timelines and engine.activeTimeline:
        timelines = [engine.activeTimeline]

    new_asset = _library.get(sanitized_id)
    new_filepath = getattr(new_asset, "filepath", "") if new_asset else ""

    for tl in timelines:
        for track in getattr(tl, "tracks", []):
            for clip in getattr(track, "clips", []):
                if getattr(clip, "assetId", None) == original_id:
                    clip.assetId = sanitized_id
                    # ImageClip and VideoClip also carry filepath
                    if hasattr(clip, "filepath") and new_filepath:
                        clip.filepath = new_filepath
                    swapped_clips.append(getattr(clip, "clipId", "?"))
                    logger.info(
                        "[/pii/register-sanitized] swapped clip %s: %s -> %s",
                        clip.clipId, original_id[:8], sanitized_id[:8],
                    )

    # 4 — refresh frontend
    notify("timeline")
    notify("library")

    print(
        f"[PII] register-sanitized: original={original_id[:8]} RESTRICTED | "
        f"sanitized={sanitized_id[:8]} SANITIZED | clips swapped={len(swapped_clips)}",
        flush=True,
    )

    return {
        "status":             "ok",
        "originalAssetId":    original_id,
        "sanitizedAssetId":   sanitized_id,
        "originalState":      "RESTRICTED",
        "sanitizedState":     "SANITIZED",
        "clipsSwapped":       len(swapped_clips),
        "swappedClipIds":     swapped_clips,
    }


 
# GET /pii/security-state/{asset_id}
 

@router.get("/security-state/{asset_id}")
def pii_security_state(asset_id: str) -> dict[str, Any]:
    """Return the current PII security state for a given asset.

    Response:
        {
            "assetId":       str,
            "securityState": "NONE" | "RESTRICTED" | "SANITIZED",
            "sanitizedAssetId": str | null,  # set if this asset is the ORIGINAL
            "originalAssetId":  str | null,  # set if this asset is the SANITIZED copy
        }
    """
    from backend.pii import security as _sec
    state = _sec.get_state(asset_id)
    return {
        "assetId":          asset_id,
        "securityState":    state,
        "sanitizedAssetId": _sec.get_sanitized(asset_id),
        "originalAssetId":  _sec.get_original(asset_id),
    }


 
# POST /pii/detect-by-id  
 

class DetectByIdRequest(BaseModel):
    asset_id: str
    use_ner: bool = True


@router.post("/detect-by-id")
def pii_detect_by_id(req: DetectByIdRequest) -> dict[str, Any]:
    """Detect PII in a library asset by asset_id — no file upload required.

    The agent calls this with just an asset_id. The backend resolves the
    filepath from the library and runs detection server-side.

    Returns:
        { assetId, assetType, filename, detections: [...] }
    """
    from backend.state import _library

    asset = _library.get(req.asset_id)
    if asset is None:
        raise HTTPException(404, f"Asset '{req.asset_id}' not found in library")

    filepath: str = getattr(asset, "filepath", "") or ""
    if not filepath or not Path(filepath).exists():
        raise HTTPException(422, f"Asset '{req.asset_id}' has no accessible file at '{filepath}'")

    asset_type = _asset_type(filepath)
    if asset_type == "unknown":
        raise HTTPException(415, f"Unsupported file type: {Path(filepath).suffix}")

    filename = Path(filepath).name
    logger.info("[/pii/detect-by-id] %s  (%s, type=%s)", req.asset_id[:8], filename, asset_type)

    if asset_type == "text":
        text = Path(filepath).read_text(encoding="utf-8", errors="ignore")
        detections = detect_text(text, use_ner=req.use_ner)
    elif asset_type == "image":
        detections = detect_image(filepath)
    else:
        detections = detect_video(filepath)

    return {
        "assetId": req.asset_id,
        "assetType": asset_type,
        "filename": filename,
        "detections": detections,
    }


 
# POST /pii/sanitize-by-id  
 

class SanitizeByIdRequest(BaseModel):
    asset_id: str
    """Library asset_id of the original file."""
    auto_redact_all: bool = True
    """If True, auto-detect + redact everything (agent default).
    If False, provide redactions list manually."""
    redactions: list[dict[str, Any]] = []
    """Optional manual redaction list (same schema as /pii/sanitize)."""


@router.post("/sanitize-by-id")
def pii_sanitize_by_id(req: SanitizeByIdRequest) -> dict[str, Any]:
    """Full PII sanitization pipeline — no file upload needed.

    Steps (all server-side):
      1. Resolve filepath from library.
      2. Run detection if auto_redact_all=True.
      3. Sanitize → write sanitized file.
      4. Register sanitized file as a new library asset.
      5. Swap all timeline clip references + mark security states.

    Returns:
        { originalAssetId, sanitizedAssetId, clipsSwapped, detectionCount, sanitizedFilename }
    """
    import uuid
    import shutil
    from backend.state import _library, engine
    from backend.pii import security as _sec
    from backend.events import notify

    asset = _library.get(req.asset_id)
    if asset is None:
        raise HTTPException(404, f"Asset '{req.asset_id}' not found in library")

    filepath: str = getattr(asset, "filepath", "") or ""
    if not filepath or not Path(filepath).exists():
        raise HTTPException(422, f"Asset '{req.asset_id}' has no accessible file")

    asset_type = _asset_type(filepath)
    if asset_type == "unknown":
        raise HTTPException(415, f"Unsupported file type: {Path(filepath).suffix}")

    logger.info("[/pii/sanitize-by-id] asset=%s type=%s", req.asset_id[:8], asset_type)

    # 2 — detect or use provided redactions
    if req.auto_redact_all:
        if asset_type == "text":
            redactions = detect_text(Path(filepath).read_text(encoding="utf-8", errors="ignore"))
        elif asset_type == "image":
            redactions = detect_image(filepath)
        else:
            redactions = detect_video(filepath)
        for r in redactions:
            r["enabled"] = True
    else:
        redactions = req.redactions

    enabled = [r for r in redactions if r.get("enabled", True)]
    logger.info("[/pii/sanitize-by-id] %d redaction(s)", len(enabled))

    # 3 — sanitize
    suffix = Path(filepath).suffix
    out_suffix = ".png" if asset_type == "image" else suffix

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_in:
        import shutil as _sh
        _sh.copy2(filepath, tmp_in.name)
        tmp_in_path = tmp_in.name

    try:
        if asset_type == "text":
            text = Path(filepath).read_text(encoding="utf-8", errors="ignore")
            out_bytes = sanitize_text(text, enabled).encode("utf-8")
        elif asset_type == "image":
            out_bytes = sanitize_image(tmp_in_path, enabled)
        else:
            out_bytes = sanitize_video(tmp_in_path, enabled)
    finally:
        try:
            os.unlink(tmp_in_path)
        except OSError:
            pass

    # 4 — save sanitized file next to original
    san_stem = f"sanitized_{Path(filepath).stem}"
    san_dest = Path(filepath).parent / f"{san_stem}{out_suffix}"
    counter = 1
    while san_dest.exists():
        san_dest = Path(filepath).parent / f"{san_stem}_{counter}{out_suffix}"
        counter += 1
    san_dest.write_bytes(out_bytes)

    # Register in library using the library router helper if available
    san_asset_id = uuid.uuid4().hex[:12]
    try:
        from backend.routers.library import _register_file
        san_asset_id = _register_file(str(san_dest))
    except Exception:
        try:
            from backend.library import Asset
            _library[san_asset_id] = Asset(
                assetId=san_asset_id, filepath=str(san_dest),
                filename=san_dest.name, type=asset_type,
            )
        except Exception as e:
            logger.warning("[/pii/sanitize-by-id] library registration fallback failed: %s", e)

    # 5 — swap timeline clips + mark security states
    _sec.mark(req.asset_id,  "RESTRICTED")
    _sec.mark(san_asset_id,  "SANITIZED")
    _sec.link(req.asset_id,  san_asset_id)

    swapped = 0
    timelines = getattr(getattr(engine, "project", None), "timelines", []) or []
    if not timelines and getattr(engine, "activeTimeline", None):
        timelines = [engine.activeTimeline]

    for tl in timelines:
        for track in getattr(tl, "tracks", []):
            for clip in getattr(track, "clips", []):
                if getattr(clip, "assetId", None) == req.asset_id:
                    clip.assetId = san_asset_id
                    if hasattr(clip, "filepath"):
                        clip.filepath = str(san_dest)
                    swapped += 1

    notify("timeline")
    notify("library")

    logger.info(
        "[/pii/sanitize-by-id] done: original=%s RESTRICTED | sanitized=%s SANITIZED | clips=%d",
        req.asset_id[:8], san_asset_id[:8], swapped,
    )

    return {
        "originalAssetId":   req.asset_id,
        "sanitizedAssetId":  san_asset_id,
        "clipsSwapped":      swapped,
        "detectionCount":    len(enabled),
        "sanitizedFilename": san_dest.name,
    }
