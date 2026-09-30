"""
router.py - FastAPI endpoints for artifact integrity verification.

Endpoints:
  POST  /integrity/register   - register export + embed watermark
  POST  /integrity/verify     - 3-layer verify (by file path)
  GET   /integrity/proof/{id} - portable proof JSON
  GET   /integrity/list       - all registered artifacts
  POST  /integrity/audit      - validate ledger hash chain
"""
from __future__ import annotations
import os
import tempfile
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from backend.integrity.service import ArtifactIntegrityService

integrity_router = APIRouter(tags=["integrity"])
_svc = ArtifactIntegrityService()


# ── Request / Response models ─────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    video_path:              str
    watermarked_output_path: Optional[str] = None

class VerifyByPathRequest(BaseModel):
    video_path: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@integrity_router.post("/register")
def register_export(req: RegisterRequest):
    """
    Register a Fade-exported video for integrity verification.
    Steps: SHA-256 hash + perceptual hash + embed invisible watermark.
    Returns artifact_id and paths.

    Note: This is a slow operation (perceptual hash = frame extraction,
    watermark = re-encode). Run as a background job in production.
    """
    if not os.path.exists(req.video_path):
        raise HTTPException(404, f"File not found: {req.video_path}")
    try:
        result = _svc.register_export(req.video_path, req.watermarked_output_path)
        return result
    except Exception as exc:
        raise HTTPException(500, str(exc))


@integrity_router.post("/verify")
def verify_by_path(req: VerifyByPathRequest):
    """
    3-layer verification by local file path.
    Tries: exact SHA-256 -> perceptual hash -> watermark extraction.
    Returns verdict: AUTHENTIC | AUTHENTIC_REENCODED | AUTHENTIC_PLATFORM_COPY | UNVERIFIED
    """
    if not os.path.exists(req.video_path):
        raise HTTPException(404, f"File not found: {req.video_path}")
    try:
        return _svc.verify_video(req.video_path)
    except Exception as exc:
        raise HTTPException(500, str(exc))


@integrity_router.post("/verify-upload")
async def verify_by_upload(file: UploadFile = File(...)):
    """
    3-layer verification via file upload.
    User uploads a video file directly (e.g. downloaded from YouTube).
    Saved to a temp file, verified, then deleted.
    """
    suffix = os.path.splitext(file.filename or ".mp4")[1] or ".mp4"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name
        content = await file.read()
        tmp.write(content)
    try:
        result = _svc.verify_video(tmp_path)
    except Exception as exc:
        raise HTTPException(500, str(exc))
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    return result


@integrity_router.get("/proof/{artifact_id}")
def get_proof(artifact_id: str):
    """
    Export a portable proof bundle for an artifact.
    Contains hashes only (SHA-256, phash, Merkle proof, ledger tx).
    Safe to share publicly. The file itself is never included.
    """
    bundle = _svc.export_proof(artifact_id)
    if bundle is None:
        raise HTTPException(404, f"Artifact {artifact_id} not found or not yet sealed.")
    return bundle


@integrity_router.get("/list")
def list_artifacts():
    """List all registered artifacts with their integrity status."""
    return {"artifacts": _svc.list_artifacts()}


@integrity_router.post("/audit")
def audit_ledger():
    """
    Validate the local ledger hash chain.
    Detects any tampering with the local ledger file.
    """
    return _svc.audit_ledger()
