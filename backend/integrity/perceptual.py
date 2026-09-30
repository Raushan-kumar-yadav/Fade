"""
perceptual.py - Perceptual video hashing for Fade artifact integrity.
Uses `videohash` which extracts frames, builds a wavelet-based 64-bit hash.
Survives: H.264/H.265 re-encode, platform upload, resize, bitrate change.
Fails on: >10deg rotation, reversed playback, >30% crop.
"""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

PHASH_THRESHOLD = 10  # Hamming bits. <= 10 = same video (tuned for platform re-encode)

# ── Pillow 10+ compatibility ──────────────────────────────────────────────────
# PIL.Image.ANTIALIAS was removed in Pillow 10.0.0 (replaced by LANCZOS).
# videohash (and ImageHash) still reference it at call time, so we patch the
# PIL.Image module object globally — this affects all code in this process.
try:
    import PIL.Image as _pil_img
    if not hasattr(_pil_img, "ANTIALIAS"):
        _pil_img.ANTIALIAS = _pil_img.LANCZOS  # type: ignore[attr-defined]
except Exception:
    pass
# ─────────────────────────────────────────────────────────────────────────────

try:
    from videohash import VideoHash as _VideoHash
    _VIDEOHASH_AVAILABLE = True
except ImportError:
    _VIDEOHASH_AVAILABLE = False
    logger.warning("videohash not installed. pip install videohash. Perceptual hash layer disabled.")


def compute_phash(video_path: str) -> str | None:
    """
    Compute perceptual hash for a video file.
    Returns 16-char hex string (64 bits) or None if videohash unavailable.
    Takes 5-30s depending on video length (CPU-bound frame extraction).
    """
    if not _VIDEOHASH_AVAILABLE:
        return None
    # Re-apply patch here too in case PIL was reloaded between calls
    try:
        import PIL.Image as _pi
        if not hasattr(_pi, "ANTIALIAS"):
            _pi.ANTIALIAS = _pi.LANCZOS  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        vh = _VideoHash(path=video_path)
        return vh.hash_hex
    except Exception as exc:
        logger.warning("compute_phash failed for %s: %s", video_path, exc)
        return None


def phash_distance(hex1: str, hex2: str) -> int:
    """
    Hamming distance between two 16-char hex phashes (no file I/O).
    Lower = more similar. 0 = identical. >10 = different video.
    """
    try:
        n1 = int(hex1, 16)
        n2 = int(hex2, 16)
        return bin(n1 ^ n2).count("1")
    except (ValueError, TypeError):
        return 64  # treat as maximally different on error


def phash_match(hex1: str, hex2: str) -> bool:
    """True if two phashes are within PHASH_THRESHOLD (same video, re-encoded)."""
    return phash_distance(hex1, hex2) <= PHASH_THRESHOLD
