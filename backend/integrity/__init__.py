"""
backend/integrity - Artifact integrity verification for Fade exports.

3-layer approach:
  Layer 1: SHA-256 exact hash         (works for exact file copy)
  Layer 2: videohash perceptual hash  (works after platform re-encode)
  Layer 3: invisible-watermark DWT-DCT (works after platform upload+download)

Core classes re-exported from echo_integrity.py (copied from blockchain repo):
  Integrity, LocalLedger, EVMLedger, sha256_file
"""
from .echo_integrity import Integrity, LocalLedger, EVMLedger, sha256_file
from .service import ArtifactIntegrityService
from .perceptual import compute_phash, phash_distance, phash_match, PHASH_THRESHOLD
from .watermark import embed_watermark, extract_watermark

__all__ = [
    "Integrity", "LocalLedger", "EVMLedger", "sha256_file",
    "ArtifactIntegrityService",
    "compute_phash", "phash_distance", "phash_match", "PHASH_THRESHOLD",
    "embed_watermark", "extract_watermark",
]
