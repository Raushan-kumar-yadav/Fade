"""
watermark.py - Invisible DWT-DCT watermark embed/extract for Fade artifact integrity.

Uses `invisible-watermark` (imwatermark) library:
  pip install invisible-watermark

Strategy:
  - Embed 4 bytes (32 bits) of artifact_id into every Nth frame (frequency domain)
  - Extract by sampling evenly-spaced frames + majority vote across samples
  - Blind extraction: does NOT need the original video

Robustness:
  - Survives H.264/H.265 re-encode, YouTube/TikTok upload, resize, moderate crop
  - May not survive very aggressive Instagram compression (<15s Reels)
"""
from __future__ import annotations
import logging
from collections import Counter

logger = logging.getLogger(__name__)

WM_BITS = 32              # 4 bytes = 32 bits (enough for artifact_id prefix)
WM_METHOD = "dwtDct"      # DWT + DCT frequency domain - best robustness/capacity trade-off
EMBED_EVERY_N = 5         # embed in every 5th frame (redundancy without huge file size)
EXTRACT_SAMPLES = 12      # sample this many frames during extraction
MIN_CONFIDENCE = 0.30     # watermark must appear in >=30% of sampled frames

try:
    import cv2 as _cv2
    from imwatermark import WatermarkEncoder as _Enc, WatermarkDecoder as _Dec
    _WM_AVAILABLE = True
except ImportError:
    _WM_AVAILABLE = False
    logger.warning("invisible-watermark not installed. pip install invisible-watermark. Watermark layer disabled.")


def embed_watermark(input_path: str, output_path: str, artifact_id: str) -> bool:
    """
    Embed artifact_id (first 4 bytes = 8 hex chars) as invisible watermark.
    Writes a NEW video file to output_path. Original is untouched.
    Returns True on success, False if library unavailable or error.

    The watermarked copy is what gets uploaded to social platforms.
    """
    if not _WM_AVAILABLE:
        logger.warning("embed_watermark: imwatermark not available, skipping")
        return False

    wm_bytes = bytes.fromhex(artifact_id[:8])   # 4 bytes
    if len(wm_bytes) != 4:
        raise ValueError("artifact_id must be at least 8 hex chars")

    try:
        cap = _cv2.VideoCapture(input_path)
        if not cap.isOpened():
            raise IOError(f"Cannot open video: {input_path}")

        fps    = cap.get(_cv2.CAP_PROP_FPS) or 30.0
        width  = int(cap.get(_cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(_cv2.CAP_PROP_FRAME_HEIGHT))
        fourcc = _cv2.VideoWriter_fourcc(*"mp4v")
        out    = _cv2.VideoWriter(output_path, fourcc, fps, (width, height))

        encoder = _Enc()
        encoder.set_watermark("bytes", wm_bytes)

        frame_idx = 0
        watermarked_count = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % EMBED_EVERY_N == 0:
                try:
                    frame = encoder.encode(frame, WM_METHOD)
                    watermarked_count += 1
                except Exception as e:
                    logger.debug("embed failed on frame %d: %s", frame_idx, e)
            out.write(frame)
            frame_idx += 1

        cap.release()
        out.release()
        logger.info("embed_watermark: %d/%d frames watermarked -> %s",
                    watermarked_count, frame_idx, output_path)
        return True

    except Exception as exc:
        logger.exception("embed_watermark failed: %s", exc)
        return False


def extract_watermark(video_path: str) -> str | None:
    """
    Extract the embedded artifact_id prefix from a video (blind - no original needed).
    Samples EXTRACT_SAMPLES evenly-spaced frames and takes majority vote.
    Returns 8-char hex string (artifact_id prefix) or None if not found/confident.
    """
    if not _WM_AVAILABLE:
        return None

    try:
        cap = _cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None

        total_frames = int(cap.get(_cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            cap.release()
            return None

        # Evenly-spaced sample indices, skip first and last 2% (may be black frames)
        margin = max(1, total_frames // 50)
        indices = [
            margin + int(i * (total_frames - 2 * margin) / (EXTRACT_SAMPLES - 1))
            for i in range(EXTRACT_SAMPLES)
        ]

        decoder = _Dec("bytes", WM_BITS)
        votes: list[str] = []

        for idx in indices:
            cap.set(_cv2.CAP_PROP_POS_FRAMES, float(idx))
            ret, frame = cap.read()
            if not ret:
                continue
            try:
                wm = decoder.decode(frame, WM_METHOD)
                if wm and len(wm) == 4:   # expect exactly 4 bytes back
                    votes.append(wm.hex())
            except Exception:
                pass

        cap.release()

        if not votes:
            return None

        winner, count = Counter(votes).most_common(1)[0]
        confidence = count / len(votes)

        logger.info("extract_watermark: winner=%s confidence=%.0f%% (%d/%d samples)",
                    winner, confidence * 100, count, len(votes))

        return winner if confidence >= MIN_CONFIDENCE else None

    except Exception as exc:
        logger.exception("extract_watermark failed: %s", exc)
        return None
