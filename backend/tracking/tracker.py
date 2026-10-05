 
from __future__ import annotations
import logging
from typing import Callable

import cv2

from backend.tracking.detector import BBox, detect_faces, detect_persons, detect_text, detect_image_template

logger = logging.getLogger(__name__)


def track_clip(
    video_path: str,
    initial_bbox: tuple[float, float, float, float],   # (x, y, w, h) pixels
    from_frame: int,
    to_frame: int,
    detection_mode: str = "manual",        # "face"|"face_ref"|"person"|"text"|"image"|"manual"
    text_pattern: str = "email|phone",
    template_path: str | None = None,
    ref_embedding = None,                  # pre-computed HOG embedding for face_ref mode
    redetect_every: int = 60,
    job: dict | None = None,               
) -> dict[int, dict]:
     
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    to_frame = min(to_frame, total_frames - 1) if to_frame >= 0 else total_frames - 1

    results: dict[int, dict] = {}

    # Seek to from_frame
    cap.set(cv2.CAP_PROP_POS_FRAMES, float(from_frame))
    ret, frame = cap.read()
    if not ret:
        cap.release()
        raise RuntimeError(f"Cannot read frame {from_frame}")

    tracker = _make_tracker()
    x, y, w, h = [float(v) for v in initial_bbox]
    ok = tracker.init(frame, (int(x), int(y), int(w), int(h)))
    if not ok:
        logger.warning("[tracker] MIL init failed on frame %d", from_frame)

    # Record first frame
    results[from_frame] = {"cx": x + w / 2, "cy": y + h / 2, "w": w, "h": h, "confidence": 1.0}

    total = to_frame - from_frame
    for fi in range(from_frame + 1, to_frame + 1):
        ret, frame = cap.read()
        if not ret:
            break

        # Optional re-detection to correct drift
        if fi > from_frame and (fi - from_frame) % redetect_every == 0:
            new_box = _redetect(frame, detection_mode, text_pattern, template_path, x, y, w, h, ref_embedding)
            if new_box:
                x, y, w, h = new_box.x, new_box.y, new_box.w, new_box.h
                tracker = _make_tracker()
                tracker.init(frame, (int(x), int(y), int(w), int(h)))

        ok, rect = tracker.update(frame)
        if ok:
            x, y, w, h = rect
            results[fi] = {"cx": x + w / 2, "cy": y + h / 2, "w": w, "h": h, "confidence": 0.9}
        else:
            # Lost 
            new_box = _redetect(frame, detection_mode, text_pattern, template_path, x, y, w, h, ref_embedding)
            if new_box:
                x, y, w, h = new_box.x, new_box.y, new_box.w, new_box.h
                tracker = _make_tracker()
                tracker.init(frame, (int(x), int(y), int(w), int(h)))
                results[fi] = {"cx": x + w / 2, "cy": y + h / 2, "w": w, "h": h, "confidence": 0.6}
            else:
                # Carry last known position
                if results:
                    last = results[max(results.keys())]
                    results[fi] = {**last, "confidence": 0.3}

        # Update progress
        if job is not None:
            done = fi - from_frame
            job["percent"] = int(done / total * 100) if total > 0 else 100
            job["current_frame"] = fi
            if job.get("cancelled"):
                break

    cap.release()
    if job is not None:
        job["percent"] = 100

    return results


def _make_tracker():
    """Create a fresh tracker instance."""
    return cv2.TrackerMIL_create()


def _redetect(frame, mode: str, text_pattern: str, template_path: str | None,
              last_x: float, last_y: float, last_w: float, last_h: float,
              ref_embedding=None) -> BBox | None:
    """Try to re-detect target. Returns best match closest to last known position, or None."""
    candidates: list[BBox] = []

    if mode in ("face", "face_ref"):
        if template_path and ref_embedding is not None:
            # Specific face: match against reference embedding
            from backend.tracking.detector import detect_face_by_reference
            hits = detect_face_by_reference(frame, ref_embedding)
            return hits[0] if hits else None
        else:
            # Auto-detect all faces, pick closest to last known position
            candidates = detect_faces(frame)
    elif mode == "person":
        candidates = detect_persons(frame)
    elif mode == "text":
        candidates = detect_text(frame, text_pattern)
    elif mode == "image" and template_path:
        candidates = detect_image_template(frame, template_path)
 

    if not candidates:
        return None

    # Pick the candidate closest to the last known position
    last_cx, last_cy = last_x + last_w / 2, last_y + last_h / 2
    best = min(candidates, key=lambda b: (b.x + b.w / 2 - last_cx) ** 2 + (b.y + b.h / 2 - last_cy) ** 2)
    return best
