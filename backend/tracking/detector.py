"""
backend/tracking/detector.py

Detects target regions in a single video frame.
Supports three modes:
  - "face"   : MediaPipe FaceDetection (fast CPU)
  - "person" : YOLOv8n (lazy-loaded, optional)
  - "text"   : EasyOCR + regex filter for emails / phone numbers / custom patterns
  - "image"  : OpenCV template matching against a reference asset image

Returns a list of (x, y, w, h) bounding boxes in pixel coordinates.
"""
from __future__ import annotations
import logging
import os
import re
import sys
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)

# ── PyInstaller-safe model directory ─────────────────────────────────────────
# Dev:    <repo>/AIModels/
# Frozen: <bundle>/_MEIPASS/AIModels/
def _resolve_models_dir() -> Path:
    if getattr(sys, "frozen", False):
        # Running as a PyInstaller bundle
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        # Dev: go up two levels from backend/tracking/ to repo root
        base = Path(__file__).parent.parent.parent
    d = base / "AIModels"
    d.mkdir(parents=True, exist_ok=True)
    return d

MODELS_DIR = _resolve_models_dir()
logger.info("[detector] MODELS_DIR = %s", MODELS_DIR)

class BBox(NamedTuple):
    x: float
    y: float
    w: float
    h: float
    confidence: float = 1.0
    label: str = ""


# ── MediaPipe Face ─────────────────────────────────────────────────────────────
_mp_face = None

def _get_mp_face():
    global _mp_face
    if _mp_face is None:
        try:
            import mediapipe as mp
            _mp_face = mp.solutions.face_detection.FaceDetection(
                model_selection=1,          # 1 = full-range model
                min_detection_confidence=0.5,
            )
        except ImportError:
            logger.warning("[tracker] mediapipe not installed: pip install mediapipe")
    return _mp_face


def detect_faces(frame_bgr) -> list[BBox]:
    """Detect faces in a BGR frame. Returns list of BBox (pixel coords)."""
    det = _get_mp_face()
    if det is None:
        return []
    try:
        import cv2
        h, w = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        res = det.process(rgb)
        if not res.detections:
            return []
        boxes = []
        for d in res.detections:
            bb = d.location_data.relative_bounding_box
            x = bb.xmin * w
            y = bb.ymin * h
            bw = bb.width * w
            bh = bb.height * h
            score = d.score[0] if d.score else 0.9
            boxes.append(BBox(x, y, bw, bh, float(score), "face"))
        return boxes
    except Exception as e:
        logger.warning("[tracker] face detection error: %s", e)
        return []


# ── YOLOv8 Person ─────────────────────────────────────────────────────────────
_yolo_model = None

def _get_yolo():
    global _yolo_model
    if _yolo_model is None:
        try:
            from ultralytics import YOLO
            # Use bundled model; fall back to auto-download if missing
            model_path = MODELS_DIR / "yolov8n.pt"
            _yolo_model = YOLO(str(model_path) if model_path.exists() else "yolov8n.pt")
        except ImportError:
            logger.warning("[tracker] ultralytics not installed: pip install ultralytics")
        except Exception as e:
            logger.warning("[tracker] YOLO load error: %s", e)
    return _yolo_model


def detect_persons(frame_bgr) -> list[BBox]:
    """Detect persons using YOLOv8n. Falls back to empty list if not installed."""
    model = _get_yolo()
    if model is None:
        return []
    try:
        results = model(frame_bgr, classes=[0], verbose=False)  # class 0 = person
        boxes = []
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                boxes.append(BBox(x1, y1, x2 - x1, y2 - y1, float(box.conf[0]), "person"))
        return boxes
    except Exception as e:
        logger.warning("[tracker] person detection error: %s", e)
        return []


# ── EasyOCR Text ──────────────────────────────────────────────────────────────
_ocr_reader = None

def _get_ocr():
    global _ocr_reader
    if _ocr_reader is None:
        try:
            import easyocr
            # Use AIModels/ as the model storage directory so no internet download at runtime
            _ocr_reader = easyocr.Reader(
                ["en"],
                gpu=False,
                verbose=False,
                model_storage_directory=str(MODELS_DIR),
                download_enabled=True,   # allow download if model is somehow missing
            )
        except ImportError:
            logger.warning("[tracker] easyocr not installed: pip install easyocr")
        except Exception as e:
            logger.warning("[tracker] EasyOCR load error: %s", e)
    return _ocr_reader


# Common privacy patterns
_PATTERNS = {
    "email":   r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}",
    "phone":   r"(\+?\d[\d\s\-().]{7,}\d)",
    "any":     r".",        # match all text
}

def detect_text(frame_bgr, text_pattern: str = "email|phone") -> list[BBox]:
    """
    Detect text regions matching the given pattern.
    text_pattern: regex string OR shorthand "email", "phone", "any"
    """
    reader = _get_ocr()
    if reader is None:
        return []
    try:
        # Build compiled regex
        expanded = text_pattern
        for k, v in _PATTERNS.items():
            expanded = expanded.replace(k, v)
        rx = re.compile(expanded, re.IGNORECASE)

        results = reader.readtext(frame_bgr)
        boxes = []
        for (pts, text, conf) in results:
            if not rx.search(text):
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            x, y = min(xs), min(ys)
            w, h = max(xs) - x, max(ys) - y
            boxes.append(BBox(x, y, w, h, float(conf), f"text:{text[:20]}"))
        return boxes
    except Exception as e:
        logger.warning("[tracker] text detection error: %s", e)
        return []


# ── Template Matching (Image asset) ───────────────────────────────────────────
def detect_image_template(frame_bgr, template_path: str, threshold: float = 0.7) -> list[BBox]:
    """
    Find occurrences of a template image inside the frame using OpenCV matchTemplate.
    Best for logos, watermarks, or any static image target.
    """
    try:
        import cv2
        import numpy as np
        template = cv2.imread(template_path, cv2.IMREAD_COLOR)
        if template is None:
            logger.warning("[tracker] could not read template: %s", template_path)
            return []
        # Resize template if larger than frame
        fh, fw = frame_bgr.shape[:2]
        th, tw = template.shape[:2]
        if th > fh or tw > fw:
            scale = min(fh / th, fw / tw) * 0.9
            template = cv2.resize(template, (int(tw * scale), int(th * scale)))
            th, tw = template.shape[:2]

        result = cv2.matchTemplate(frame_bgr, template, cv2.TM_CCOEFF_NORMED)
        locs = np.where(result >= threshold)
        boxes = []
        for py, px in zip(*locs):
            boxes.append(BBox(float(px), float(py), float(tw), float(th), float(result[py, px]), "image"))
        # NMS: merge overlapping boxes
        return _simple_nms(boxes, iou_threshold=0.3)
    except Exception as e:
        logger.warning("[tracker] template matching error: %s", e)
        return []


def _simple_nms(boxes: list[BBox], iou_threshold: float = 0.3) -> list[BBox]:
    """Non-maximum suppression — removes overlapping boxes."""
    if not boxes:
        return []
    boxes = sorted(boxes, key=lambda b: b.confidence, reverse=True)
    kept = []
    for b in boxes:
        overlap = False
        for k in kept:
            if _iou(b, k) > iou_threshold:
                overlap = True
                break
        if not overlap:
            kept.append(b)
    return kept


def _iou(a: BBox, b: BBox) -> float:
    ax1, ay1 = a.x, a.y
    ax2, ay2 = a.x + a.w, a.y + a.h
    bx1, by1 = b.x, b.y
    bx2, by2 = b.x + b.w, b.y + b.h
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    union = a.w * a.h + b.w * b.h - inter
    return inter / union if union > 0 else 0.0
