"""
backend/pii/detector.py
=======================
Pure-read detection layer — NEVER modifies the source asset.

Exports:
    detect_text(text, use_ner=True)  -> list[dict]   # TextDetection
    detect_image(path)               -> list[dict]   # ImageDetection
    detect_video(path, every_sec)    -> list[dict]   # VideoDetection

Coordinate system (IMAGE / VIDEO)
----------------------------------
coordinateSpace = "source"
x      = pixels from left edge of the original source frame
y      = pixels from top  edge of the original source frame
width  = bbox width  in source pixels
height = bbox height in source pixels

_ocr_boxes() already divides by OCR_SCALE so all values returned here are in
source resolution.  No further conversion is needed by callers.
"""
from __future__ import annotations

import sys
import uuid
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bootstrap: make the standalone pii/ package importable.
# ---------------------------------------------------------------------------
_PII_DIR = Path(__file__).resolve().parent.parent.parent / "pii"
if str(_PII_DIR) not in sys.path:
    sys.path.insert(0, str(_PII_DIR))

from scrubber import find_spans, _ocr_boxes, OCR_SCALE  # noqa: E402  pylint: disable=wrong-import-position

# ---------------------------------------------------------------------------
# Confidence constants
# ---------------------------------------------------------------------------
_REGEX_CONFIDENCE: dict[str, float] = {
    "PRIVATE_KEY":  0.999,
    "JWT":          0.99,
    "AWS_KEY":      0.99,
    "GITHUB_TOKEN": 0.99,
    "BEARER_TOKEN": 0.97,
    "SECRET":       0.95,
    "EMAIL":        0.98,
    "CREDIT_CARD":  0.97,   # already Luhn-validated by find_spans
    "AADHAAR":      0.92,
    "PAN":          0.93,
    "PHONE":        0.91,
    "IPV4":         0.95,
    "PERSON":       0.82,   # spaCy NER — softer
}

_OCR_CONFIDENCE: dict[str, float] = {
    k: max(0.70, v - 0.15) for k, v in _REGEX_CONFIDENCE.items()
}


def _make_id() -> str:
    return "det_" + uuid.uuid4().hex[:8]


# ─────────────────────────────────────────────────────────────────────────────
# TEXT
# ─────────────────────────────────────────────────────────────────────────────

def detect_text(text: str, use_ner: bool = True) -> list[dict[str, Any]]:
    """Detect PII in a plain-text string.

    Returns a list of TextDetection dicts:
        {
            "id":         str,
            "type":       str,    e.g. "EMAIL"
            "confidence": float,
            "start":      int,    inclusive char offset into `text`
            "end":        int,    exclusive char offset
            "value":      str,    matched text — UI-only; NEVER log or send to LLM
        }
    """
    spans = find_spans(text, use_ner=use_ner)
    results: list[dict[str, Any]] = []
    for start, end, label in spans:
        results.append({
            "id":         _make_id(),
            "type":       label,
            "confidence": _REGEX_CONFIDENCE.get(label, 0.85),
            "start":      start,
            "end":        end,
            "value":      text[start:end],  # safe for UI; do NOT log
        })
    logger.info("[PII/detect_text] found %d detection(s)", len(results))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# IMAGE
# ─────────────────────────────────────────────────────────────────────────────

def detect_image(path: str | Path) -> list[dict[str, Any]]:
    """Detect PII in an image via OCR.  Source file is NOT modified.

    Returns a list of ImageDetection dicts:
        {
            "id":              str,
            "type":            str,
            "confidence":      float,
            "bbox":            {"x": int, "y": int, "width": int, "height": int},
            "coordinateSpace": "source",
            "sourceWidth":     int,
            "sourceHeight":    int,
        }
    """
    from PIL import Image  # pylint: disable=import-outside-toplevel

    img = Image.open(path).convert("RGB")
    src_w, src_h = img.width, img.height

    boxes, labels = _ocr_boxes(img)   # already in source resolution

    results: list[dict[str, Any]] = []
    for (x, y, w, h), label in zip(boxes, labels):
        results.append({
            "id":              _make_id(),
            "type":            label,
            "confidence":      _OCR_CONFIDENCE.get(label, 0.70),
            "bbox": {"x": x, "y": y, "width": w, "height": h},
            "coordinateSpace": "source",
            "sourceWidth":     src_w,
            "sourceHeight":    src_h,
        })

    logger.info("[PII/detect_image] %s -> %d detection(s)", Path(path).name, len(results))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# VIDEO
# ─────────────────────────────────────────────────────────────────────────────

def detect_video(
    path: str | Path,
    every_sec: float = 1.0,
) -> list[dict[str, Any]]:
    """Detect PII in a video by sampling frames.  Source file is NOT modified.

    Returns a list of VideoDetection dicts:
        {
            "id":              str,
            "type":            str,
            "confidence":      float,
            "coordinateSpace": "source",
            "sourceWidth":     int,
            "sourceHeight":    int,
            "fps":             float,
            "frames": {
                "<frame_num>": {"x": int, "y": int, "width": int, "height": int},
                ...
            }
        }
    Consecutive frames with the same label and approx. position are merged
    into one detection dict so FADE can render a single track.
    """
    import cv2  # pylint: disable=import-outside-toplevel
    from PIL import Image  # pylint: disable=import-outside-toplevel

    cap = cv2.VideoCapture(str(path))
    fps: float = cap.get(cv2.CAP_PROP_FPS) or 25.0
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    step = max(1, int(fps * every_sec))

    pending: list[dict[str, Any]] = []
    active_boxes: list[tuple[int, int, int, int]] = []
    active_labels: list[str] = []
    frame_num = 0
    last_small = None
    last_ocr = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        if frame_num % step == 0:
            small = cv2.cvtColor(
                cv2.resize(frame, (max(1, src_w // 4), max(1, src_h // 4))),
                cv2.COLOR_BGR2GRAY,
            )
            changed = last_small is None or cv2.absdiff(small, last_small).mean() > 1.5
            if changed or frame_num - last_ocr >= fps * 5:
                pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                active_boxes, active_labels = _ocr_boxes(pil)
                last_small = small
                last_ocr = frame_num

        for (x, y, w, h), label in zip(active_boxes, active_labels):
            pending.append({
                "frame": frame_num, "type": label,
                "x": x, "y": y, "width": w, "height": h,
            })
        frame_num += 1

    cap.release()

    # Merge consecutive same-label, same-position hits into one detection.
    detections: list[dict[str, Any]] = []

    def _match(det: dict[str, Any], label: str, x: int, y: int) -> bool:
        if det["type"] != label:
            return False
        sample = next(iter(det["frames"].values()))
        return abs(sample["x"] - x) <= 5 and abs(sample["y"] - y) <= 5

    for hit in pending:
        matched = next(
            (d for d in detections if _match(d, hit["type"], hit["x"], hit["y"])),
            None,
        )
        if matched:
            matched["frames"][str(hit["frame"])] = {
                "x": hit["x"], "y": hit["y"],
                "width": hit["width"], "height": hit["height"],
            }
        else:
            detections.append({
                "id":              _make_id(),
                "type":            hit["type"],
                "confidence":      _OCR_CONFIDENCE.get(hit["type"], 0.70),
                "coordinateSpace": "source",
                "sourceWidth":     src_w,
                "sourceHeight":    src_h,
                "fps":             fps,
                "frames": {
                    str(hit["frame"]): {
                        "x": hit["x"], "y": hit["y"],
                        "width": hit["width"], "height": hit["height"],
                    }
                },
            })

    logger.info(
        "[PII/detect_video] %s -> %d detection(s) across %d frames",
        Path(path).name, len(detections), frame_num,
    )
    return detections
