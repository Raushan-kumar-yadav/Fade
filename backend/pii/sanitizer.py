"""
backend/pii/sanitizer.py
========================
Sanitization layer — accepts the FINAL RedactionRequest from FADE and applies it.

The sanitizer NEVER re-detects PII.  It operates exclusively on the redactions
the user has approved (which may differ from the original detections: moved,
resized, added, or removed).

Exports:
    sanitize_text(text, redactions)        -> str
    sanitize_image(in_path, redactions)    -> bytes  (PNG)
    sanitize_video(in_path, redactions)    -> bytes  (MP4)
"""
from __future__ import annotations

import hashlib
import logging
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SALT = "fade-demo-salt"


def _pseudonym(value: str, label: str) -> str:
    h = hashlib.sha256((SALT + value).encode()).hexdigest()[:4]
    return f"[{label}_{h}]"


# ─────────────────────────────────────────────────────────────────────────────
# TEXT
# ─────────────────────────────────────────────────────────────────────────────

def sanitize_text(text: str, redactions: list[dict[str, Any]]) -> str:
    """Apply final FADE redactions to plain text.

    Each redaction must have:
        {
            "enabled": bool,
            "action":  "redact" | "pseudonymize",
            "start":   int,
            "end":     int,
            "type":    str,
        }

    Disabled redactions are skipped (user unchecked them in FADE).
    Overlapping ranges are merged to avoid double-processing.
    """
    # Filter enabled only, sort by start offset
    active = sorted(
        [r for r in redactions if r.get("enabled", True)],
        key=lambda r: r["start"],
    )

    out: list[str] = []
    last = 0
    for r in active:
        start, end = r["start"], r["end"]
        if start < last:
            continue   # skip overlap / duplicate
        out.append(text[last:start])
        original = text[start:end]
        action = r.get("action", "redact")
        if action == "pseudonymize":
            out.append(_pseudonym(original, r.get("type", "PII")))
        else:
            out.append("[REDACTED]")
        last = end

    out.append(text[last:])
    result = "".join(out)
    logger.info("[PII/sanitize_text] applied %d redaction(s)", len(active))
    return result


# ─────────────────────────────────────────────────────────────────────────────
# IMAGE
# ─────────────────────────────────────────────────────────────────────────────

def sanitize_image(in_path: str | Path, redactions: list[dict[str, Any]]) -> bytes:
    """Apply final FADE redactions to an image.

    Each redaction must have:
        {
            "enabled": bool,
            "action":  "redact",            # image only supports 'redact'
            "bbox":    {"x", "y", "width", "height"},
            "coordinateSpace": "source",
        }

    Returns PNG bytes of the redacted image.
    The source file is NOT modified.
    """
    from PIL import Image, ImageDraw  # pylint: disable=import-outside-toplevel

    img = Image.open(in_path).convert("RGB")
    draw = ImageDraw.Draw(img)

    active = [r for r in redactions if r.get("enabled", True)]
    for r in active:
        bbox = r.get("bbox", {})
        x = int(bbox.get("x", 0))
        y = int(bbox.get("y", 0))
        w = int(bbox.get("width", 0))
        h = int(bbox.get("height", 0))
        if w <= 0 or h <= 0:
            logger.warning("[PII/sanitize_image] skipping zero-size bbox for %s", r.get("id"))
            continue
        # 2-px padding matches the original scrubber behaviour
        draw.rectangle([x - 2, y - 2, x + w + 2, y + h + 2], fill="black")

    import io  # pylint: disable=import-outside-toplevel
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    logger.info("[PII/sanitize_image] applied %d redaction(s)", len(active))
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# VIDEO
# ─────────────────────────────────────────────────────────────────────────────

def sanitize_video(in_path: str | Path, redactions: list[dict[str, Any]]) -> bytes:
    """Apply final FADE redactions to a video.

    Each redaction must have:
        {
            "enabled": bool,
            "frames": {"<frame_num>": {"x", "y", "width", "height"}},
        }

    The sanitizer draws black rectangles on exactly the frames/bboxes
    the user approved in FADE.  It does NOT re-run detection.

    Returns the MP4 bytes of the redacted video.
    The source file is NOT modified.
    """
    import cv2, shutil, subprocess, os  # pylint: disable=import-outside-toplevel

    active = [r for r in redactions if r.get("enabled", True)]

    # Build a lookup: frame_number -> list[bbox]
    frame_map: dict[int, list[dict[str, int]]] = {}
    for r in active:
        for fn_str, bbox in r.get("frames", {}).items():
            fn = int(fn_str)
            frame_map.setdefault(fn, []).append(bbox)

    cap = cv2.VideoCapture(str(in_path))
    fps: float = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    with tempfile.TemporaryDirectory() as tmp:
        silent_path = os.path.join(tmp, "silent.mp4")
        out_path    = os.path.join(tmp, "out.mp4")

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        vw = cv2.VideoWriter(silent_path, fourcc, fps, (w, h))

        frame_num = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            for bbox in frame_map.get(frame_num, []):
                fx = int(bbox.get("x", 0)) - 2
                fy = int(bbox.get("y", 0)) - 2
                fw = int(bbox.get("width", 0)) + 4
                fh = int(bbox.get("height", 0)) + 4
                if fw > 0 and fh > 0:
                    cv2.rectangle(frame, (fx, fy), (fx + fw, fy + fh), (0, 0, 0), -1)
            vw.write(frame)
            frame_num += 1

        cap.release()
        vw.release()

        if shutil.which("ffmpeg"):
            subprocess.run(
                [
                    "ffmpeg", "-v", "error", "-y",
                    "-i", silent_path, "-i", str(in_path),
                    "-map", "0:v", "-map", "1:a?",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "copy", "-shortest",
                    out_path,
                ],
                check=True,
            )
        else:
            shutil.copy(silent_path, out_path)

        video_bytes = Path(out_path).read_bytes()

    logger.info(
        "[PII/sanitize_video] applied redactions to %d frame slot(s)", len(frame_map)
    )
    return video_bytes
