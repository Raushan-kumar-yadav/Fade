 
from __future__ import annotations
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path

try:
    import httpx as _httpx
    _HTTPX_OK = True
except ImportError:
    _HTTPX_OK = False


from backend.integrity.echo_integrity import (
    Integrity, LocalLedger, sha256_file
)
from backend.integrity.perceptual import (
    compute_phash, phash_distance, PHASH_THRESHOLD
)
from backend.integrity.watermark import embed_watermark, extract_watermark

logger = logging.getLogger(__name__)

# Data dir: backend/integrity/data/  
_DATA_DIR = Path(__file__).parent / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)


def _get_svc() -> Integrity:
    ledger = LocalLedger(_DATA_DIR / "ledger.jsonl")


def _publish_to_server(payload: dict) -> None:
   
    if not _HTTPX_OK:
        logger.warning("[integrity] httpx not installed — skipping server publish")
        return

    server_url = os.environ.get("VERIFICATION_SERVER_URL", "").rstrip("/")
    api_key    = os.environ.get("VERIFICATION_SERVER_KEY", "")

    if not server_url:
        logger.debug("[integrity] VERIFICATION_SERVER_URL not set — skipping publish")
        return

    if not api_key:
        logger.warning("[integrity] VERIFICATION_SERVER_KEY not set — skipping publish")
        return

    endpoint = f"{server_url}/registerContent"
    headers  = {"X-API-Key": api_key, "Content-Type": "application/json"}

    try:
        resp = _httpx.post(
            endpoint,
            json=payload,
            headers=headers,
            timeout=90,          # Increased from 15 to 90s to handle Render free tier cold starts
        )
        if resp.status_code == 200:
            logger.info("[integrity] Published to server OK: artifact_id=%s", payload.get("artifact_id"))
        elif resp.status_code == 409:
            logger.info("[integrity] Artifact already on server (409) — skipping")
        else:
            logger.warning(
                "[integrity] Server returned %d for artifact %s: %s",
                resp.status_code, payload.get("artifact_id"), resp.text[:200]
            )
    except _httpx.TimeoutException:
        logger.warning("[integrity] Server publish timed out (artifact_id=%s) — local record kept",
                       payload.get("artifact_id"))
    except _httpx.ConnectError as e:
        logger.warning("[integrity] Cannot reach server %s: %s — local record kept", server_url, e)
    except Exception as e:
        logger.warning("[integrity] Unexpected error publishing to server: %s", e)


def _get_svc() -> Integrity:
    ledger = LocalLedger(_DATA_DIR / "ledger.jsonl")

    svc = Integrity(_DATA_DIR / "registry.db", ledger)
    _extend_db(svc.db)
    return svc


def _extend_db(db: sqlite3.Connection) -> None:
    """Add phash + wm_id columns to artifacts table (idempotent)."""
    for col in ("phash TEXT", "wm_id TEXT"):
        try:
            db.execute(f"ALTER TABLE artifacts ADD COLUMN {col}")
            db.commit()
        except sqlite3.OperationalError:
            pass  # already exists


_VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".ts", ".flv"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff", ".tif"}
_PDF_EXTS   = {".pdf"}

def _guess_content_type(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in _VIDEO_EXTS:
        return "video"
    if ext in _IMAGE_EXTS:
        return "image"
    if ext in _PDF_EXTS:
        return "pdf"
    return "video"  # default


class ArtifactIntegrityService:
    """
    Registers exports and verifies videos using all 3 layers.
    Thread-safe for FastAPI (each call creates its own DB connection via _get_svc).
    """

    def register_export(
        self,
        video_path: str,
        watermarked_output_path: str | None = None,
    ) -> dict:
         
        svc = _get_svc()

        # Derive watermarked output path
        if watermarked_output_path is None:
            p = Path(video_path)
            watermarked_output_path = str(p.parent / (p.stem + "_wm" + p.suffix))

        # ── Step 1 (fast, synchronous): SHA-256 + register in SQLite ──
        rec = svc.register(video_path)
        artifact_id = rec["id"]
        logger.info("Registered artifact %s sha256=%s", artifact_id, rec["sha256"][:16])

        # Return immediately so the UI is not blocked.
        # pHash + watermark + Render publish run in a background thread.
        result = {
            "artifact_id": artifact_id,
            "sha256": rec["sha256"],
            "filename": rec["filename"],
            "size_bytes": rec["size"],
            "phash": None,
            "phash_available": False,
            "wm_id": None,
            "wm_available": False,
            "watermarked_output_path": None,
            "batch": None,
            "registered_at": rec["registered_at"],
        }

        # ── Step 2 (slow, background): pHash + watermark + Merkle + Render ──
        def _background_work(
            _video_path=video_path,
            _wm_out=watermarked_output_path,
            _artifact_id=artifact_id,
            _rec=rec,
        ):
            try:
                _svc2 = _get_svc()
                final_sha256 = _rec["sha256"]
                final_size = _rec["size"]

                # pHash (slow – frame extraction)
                phash = compute_phash(_video_path)
                if phash:
                    logger.info("pHash %s for artifact %s", phash, _artifact_id)

                # Embed invisible watermark
                wm_ok = embed_watermark(_video_path, _wm_out, _artifact_id)
                wm_id = _artifact_id[:8] if wm_ok else None

                if wm_ok:
                    logger.info("Watermark done. Replacing original with watermarked copy…")
                    from backend.integrity.echo_integrity import sha256_file
                    final_sha256 = sha256_file(_wm_out)
                    final_size = os.path.getsize(_wm_out)
                    try:
                        os.replace(_wm_out, _video_path)
                    except OSError:
                        import shutil
                        shutil.move(_wm_out, _video_path)

                # Update DB with final values
                _svc2.db.execute(
                    "UPDATE artifacts SET sha256=?, size=?, phash=?, wm_id=? WHERE id=?",
                    (final_sha256, final_size, phash, wm_id, _artifact_id),
                )
                _svc2.db.commit()

                # Seal Merkle tree
                batch = _svc2.seal()

                # Publish to Render server (90s timeout, cold-start aware)
                _publish_to_server({
                    "artifact_id":  _artifact_id,
                    "sha256":       final_sha256,
                    "phash":        phash,
                    "wm_id":        wm_id,
                    "merkle_proof": batch.get("proof") if batch else None,
                    "merkle_root":  batch.get("root")  if batch else None,
                    "ledger_tx":    batch.get("tx")    if batch else None,
                    "filename":     _rec["filename"],
                    "content_type": _guess_content_type(_rec["filename"] or _video_path),
                    "size_bytes":   final_size,
                })
                logger.info("[integrity] Background registration complete for %s", _artifact_id)
            except Exception as exc:
                logger.warning("[integrity] Background registration failed for %s: %s", _artifact_id, exc)

        t = threading.Thread(target=_background_work, daemon=True)
        t.start()
        logger.info("[integrity] Background thread started for pHash+wm+publish (artifact=%s)", artifact_id)

        return result



    def verify_video(self, video_path: str) -> dict:
         
        svc = _get_svc()

        #   Layer 1: exact SHA-256  
        current_sha = sha256_file(video_path)
        row = svc.db.execute(
            "SELECT id, phash, wm_id FROM artifacts WHERE sha256=? LIMIT 1",
            (current_sha,),
        ).fetchone()
        if row:
            bundle = svc.bundle(row["id"])
            return {
                "verdict": "AUTHENTIC",
                "method": "sha256",
                "artifact_id": row["id"],
                "detail": "Exact byte-for-byte match with registered export.",
                "bundle": bundle,
            }

        #   Layer 2: perceptual hash  
        current_phash = compute_phash(video_path)
        if current_phash:
            rows = svc.db.execute(
                "SELECT id, phash, wm_id FROM artifacts WHERE phash IS NOT NULL"
            ).fetchall()
            best_dist = 999
            best_row  = None
            for r in rows:
                d = phash_distance(current_phash, r["phash"])
                if d < best_dist:
                    best_dist, best_row = d, r
            if best_row and best_dist <= PHASH_THRESHOLD:
                bundle = svc.bundle(best_row["id"])
                return {
                    "verdict": "AUTHENTIC_REENCODED",
                    "method": "phash",
                    "artifact_id": best_row["id"],
                    "hamming": best_dist,
                    "detail": f"Perceptual fingerprint matched ({best_dist}/64 bits differ). Video was re-encoded but content is authentic.",
                    "bundle": bundle,
                }

        #   Layer 3: watermark extraction  
        wm_id = extract_watermark(video_path) 
        if wm_id:
            row = svc.db.execute(
                "SELECT id, phash FROM artifacts WHERE wm_id=? LIMIT 1", (wm_id,)
            ).fetchone()
            if row:
                bundle = svc.bundle(row["id"])
                return {
                    "verdict": "AUTHENTIC_PLATFORM_COPY",
                    "method":      "watermark",
                    "artifact_id": row["id"],
                    "wm_id": wm_id,
                    "detail": "Invisible watermark extracted and matched a registered artifact. Content is authentic (may have been uploaded to a platform).",
                    "bundle": bundle,
                }

        #   No match  
        return {
            "verdict": "UNVERIFIED",
            "method":  None,
            "detail":  (
                "No matching artifact found by exact hash, perceptual fingerprint, "
                "or embedded watermark. This file was not registered with Fade, "
                "or has been significantly modified."
            ),
        }

    def export_proof(self, artifact_id: str) -> dict | None:
        """Portable proof bundle (hashes only, safe to share publicly)."""
        svc = _get_svc()
        row = svc.db.execute(
            "SELECT phash, wm_id FROM artifacts WHERE id=?", (artifact_id,)
        ).fetchone()
        bundle = svc.bundle(artifact_id)
        if bundle and row:
            bundle["phash"] = row["phash"]
            bundle["wm_id"] = row["wm_id"]
        return bundle

    def list_artifacts(self) -> list[dict]:
        """List all registered artifacts."""
        svc = _get_svc()
        rows = svc.db.execute(
            "SELECT id, filename, sha256, size, registered_at, batch_id, phash, wm_id "
            "FROM artifacts ORDER BY registered_at DESC"
        ).fetchall()
        return [
            {
                "artifact_id": r["id"],
                "filename": r["filename"],
                "sha256": r["sha256"],
                "size_bytes": r["size"],
                "registered_at": r["registered_at"],
                "sealed": r["batch_id"] is not None,
                "phash": r["phash"],
                "wm_id": r["wm_id"],
            }
            for r in rows
        ]

    def audit_ledger(self) -> dict:
        """Validate the local ledger hash chain."""
        ledger = LocalLedger(_DATA_DIR / "ledger.jsonl")
        ok, msg = ledger.validate()
        return {"ok": ok, "message": msg}
