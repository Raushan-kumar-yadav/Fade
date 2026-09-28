"""
backend/routers/pii.py
======================
FastAPI router that exposes the FADE PII detection + sanitization API.

Endpoints:
    POST /pii/detect    -> DetectionResult list
    POST /pii/sanitize  -> sanitized file bytes

These endpoints follow the same conventions as the rest of the FADE backend:
  - multipart/form-data for file upload
  - JSON body for redaction requests (supplied as a form field)
  - all file paths are never logged in full
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
