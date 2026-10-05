 
from __future__ import annotations
import logging
import os
import re
import sys
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)

 
def _resolve_models_dir() -> Path:
    if getattr(sys, "frozen", False):
        # Running as a PyInstaller bundle
        base = Path(sys._MEIPASS)   
    else:
         
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


#   MediaPipe Face (new Tasks API — mediapipe >= 0.10)
_mp_face_detector = None

def _get_mp_face():
    global _mp_face_detector
    if _mp_face_detector is None:
        try:
            import mediapipe as mp
            model_path = MODELS_DIR / "blaze_face_short_range.tflite"
            if not model_path.exists():
                logger.warning("[tracker] blaze_face_short_range.tflite not found at %s — downloading...", model_path)
                try:
                    import urllib.request
                    url = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
                    urllib.request.urlretrieve(url, str(model_path))
                    logger.info("[tracker] downloaded face model to %s", model_path)
                except Exception as dl_err:
                    logger.warning("[tracker] failed to download face model: %s", dl_err)

            if model_path.exists():
                BaseOptions = mp.tasks.BaseOptions
                FaceDetector = mp.tasks.vision.FaceDetector
                FaceDetectorOptions = mp.tasks.vision.FaceDetectorOptions
                RunningMode = mp.tasks.vision.RunningMode
                options = FaceDetectorOptions(
                    base_options=BaseOptions(model_asset_path=str(model_path)),
                    running_mode=RunningMode.IMAGE,
                    min_detection_confidence=0.2,
                )
                _mp_face_detector = FaceDetector.create_from_options(options)
                logger.info("[tracker] MediaPipe FaceDetector (Tasks API) loaded")
            else:
                logger.warning("[tracker] face model not available, will use OpenCV fallback")
        except Exception as e:
            logger.warning("[tracker] MediaPipe face detector init error: %s", e)
    return _mp_face_detector


def detect_faces(frame_bgr) -> list[BBox]:
    """Detect faces in a BGR frame using MediaPipe Tasks API. Falls back to OpenCV Haar cascade."""
    det = _get_mp_face()
    if det is not None:
        try:
            import mediapipe as mp
            import cv2
            h, w = frame_bgr.shape[:2]
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = det.detect(mp_img)
            if not result.detections:
                return []
            boxes = []
            for d in result.detections:
                bb = d.bounding_box
                score = d.categories[0].score if d.categories else 0.9
                boxes.append(BBox(float(bb.origin_x), float(bb.origin_y),
                                  float(bb.width), float(bb.height),
                                  float(score), "face"))
            return boxes
        except Exception as e:
            logger.warning("[tracker] MediaPipe face detection error: %s", e)

    # OpenCV Haar cascade fallback
    try:
        import cv2
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        cascade_path = str(MODELS_DIR / "haarcascade_frontalface_default.xml")
        if not os.path.exists(cascade_path):
            # Use OpenCV built-in
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        clf = cv2.CascadeClassifier(cascade_path)
        faces = clf.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        boxes = []
        for (x, y, w, h) in faces:
            boxes.append(BBox(float(x), float(y), float(w), float(h), 0.8, "face"))
        logger.info("[tracker] OpenCV Haar cascade found %d faces", len(boxes))
        return boxes
    except Exception as e:
        logger.warning("[tracker] OpenCV face detection error: %s", e)
        return []


#   YOLOv8 Person  
_yolo_model = None

def _get_yolo():
    global _yolo_model
    if _yolo_model is None:
        try:
            from ultralytics import YOLO
            # Use bundled model;  
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


#   EasyOCR Text  
_ocr_reader = None

def _get_ocr():
    global _ocr_reader
    if _ocr_reader is None:
        try:
            import easyocr
         
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
    "email": r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+[\.\s][a-zA-Z]{2,}",
    "phone": r"(\+?\d[\d\s\-().]{7,}\d)",
    "any": r".",        # match all text
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


#   Template Matching    
def detect_image_template(frame_bgr, template_path: str, threshold: float = 0.5) -> list[BBox]:
    """
    Find occurrences of a template image inside the frame using OpenCV matchTemplate.
    Uses multi-scale search and always returns the best match found even if below threshold
    (with lower confidence score). Best for logos, watermarks, or any static image target.
    """
    try:
        import cv2
        import numpy as np
        template = cv2.imread(template_path, cv2.IMREAD_COLOR)
        if template is None:
            logger.warning("[tracker] could not read template: %s", template_path)
            return []

        fh, fw = frame_bgr.shape[:2]
        th, tw = template.shape[:2]

        # Ensure template fits inside frame
        if th > fh or tw > fw:
            scale = min(fh / th, fw / tw) * 0.9
            template = cv2.resize(template, (int(tw * scale), int(th * scale)))
            th, tw = template.shape[:2]

         
        scales = [1.0, 0.8, 0.6, 0.4]
        best_val = -1.0
        best_loc = (0, 0)
        best_tw = tw
        best_th = th

        for scale in scales:
            scaled_tw = max(4, int(tw * scale))
            scaled_th = max(4, int(th * scale))
            if scaled_tw >= fw or scaled_th >= fh:
                continue
            scaled_tmpl = cv2.resize(template, (scaled_tw, scaled_th))
            result = cv2.matchTemplate(frame_bgr, scaled_tmpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val > best_val:
                best_val = max_val
                best_loc = max_loc
                best_tw = scaled_tw
                best_th = scaled_th

        logger.info("[tracker] template best match: val=%.3f at %s (threshold=%.2f)", best_val, best_loc, threshold)

        if best_val >= threshold:
            # Good match 
            scaled_tmpl = cv2.resize(template, (best_tw, best_th))
            result = cv2.matchTemplate(frame_bgr, scaled_tmpl, cv2.TM_CCOEFF_NORMED)
            locs = np.where(result >= threshold)
            boxes = []
            for py, px in zip(*locs):
                boxes.append(BBox(float(px), float(py), float(best_tw), float(best_th), float(result[py, px]), "image"))
            return _simple_nms(boxes, iou_threshold=0.3)
        elif best_val >= 0.3:
             
            px, py = best_loc
            logger.warning("[tracker] template match below threshold (%.3f < %.2f), using best guess", best_val, threshold)
            return [BBox(float(px), float(py), float(best_tw), float(best_th), float(best_val), "image")]
        else:
            logger.warning("[tracker] template match too poor (%.3f), no detection", best_val)
            return []
    except Exception as e:
        logger.warning("[tracker] template matching error: %s", e)
        return []


# Face by Reference  

def extract_face_embedding(img_bgr) -> "np.ndarray | None":
    """Crop the largest face from an image and return a normalised feature vector.
    Uses HOG histogram over the face crop as a lightweight embedding (no extra deps)."""
    import cv2
    import numpy as np

    faces = detect_faces(img_bgr)
    if not faces:
        return None

    # Use the largest detected face
    best = max(faces, key=lambda b: b.w * b.h)
    x, y, w, h = int(best.x), int(best.y), int(best.w), int(best.h)
    x, y = max(0, x), max(0, y)
    crop = img_bgr[y:y+h, x:x+w]
    if crop.size == 0:
        return None

    # Resize to fixed size for consistent embedding
    SIZE = 64
    face_resized = cv2.resize(crop, (SIZE, SIZE))

    # HOG descriptor as embedding
    try:
        hog = cv2.HOGDescriptor(
            _winSize=(SIZE, SIZE),
            _blockSize=(16, 16),
            _blockStride=(8, 8),
            _cellSize=(8, 8),
            _nbins=9,
        )
        vec = hog.compute(face_resized).flatten()
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec
    except Exception:
        # Fallback: flattened colour histogram
        hist = cv2.calcHist([face_resized], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
        vec = hist.flatten().astype(float)
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec


def _face_similarity(crop_bgr, ref_embedding: "np.ndarray") -> float:
    """Return cosine similarity [0..1] between a face crop and a reference embedding."""
    import cv2
    import numpy as np

    SIZE = 64
    resized = cv2.resize(crop_bgr, (SIZE, SIZE))
    try:
        hog = cv2.HOGDescriptor(
            _winSize=(SIZE, SIZE),
            _blockSize=(16, 16),
            _blockStride=(8, 8),
            _cellSize=(8, 8),
            _nbins=9,
        )
        vec = hog.compute(resized).flatten()
    except Exception:
        hist = cv2.calcHist([resized], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
        vec = hist.flatten().astype(float)

    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    sim = float(np.dot(vec, ref_embedding))
    return max(0.0, min(1.0, sim))


def detect_face_by_reference(
    frame_bgr,
    ref_embedding: "np.ndarray",
    min_similarity: float = 0.60,
) -> list[BBox]:
    """Detect all faces in a frame and return the one most similar to the reference.

    Args:
        frame_bgr:       BGR video frame.
        ref_embedding:   HOG embedding from extract_face_embedding() on the reference image.
        min_similarity:  Minimum cosine similarity to accept a match (0..1).

    Returns:
        List with at most one BBox — the best matching face, or [] if no face is similar enough.
    """
    import cv2
    import numpy as np

    faces = detect_faces(frame_bgr)
    if not faces:
        return []

    best_box: BBox | None = None
    best_sim = -1.0

    for face in faces:
        x, y, w, h = int(face.x), int(face.y), int(face.w), int(face.h)
        x, y = max(0, x), max(0, y)
        crop = frame_bgr[y:y+h, x:x+w]
        if crop.size == 0:
            continue

        sim = _face_similarity(crop, ref_embedding)
        logger.debug("[tracker] face_ref candidate sim=%.3f at (%d,%d,%d,%d)", sim, x, y, w, h)

        if sim > best_sim:
            best_sim = sim
            best_box = face

    if best_box is not None and best_sim >= min_similarity:
        logger.info("[tracker] face_ref matched: sim=%.3f (threshold=%.2f)", best_sim, min_similarity)
        return [BBox(best_box.x, best_box.y, best_box.w, best_box.h,
                     float(best_sim), "face_ref")]

    if best_box is not None:
        logger.warning("[tracker] face_ref best sim=%.3f below threshold %.2f",
                       best_sim, min_similarity)

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
