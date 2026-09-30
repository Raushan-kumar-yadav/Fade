 
from __future__ import annotations
import json
import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from backend.tracking import jobs as _jobs
from backend.tracking.detector import (
    BBox, detect_faces, detect_persons, detect_text, detect_image_template
)
from backend.tracking.tracker import track_clip

logger = logging.getLogger(__name__)

# Track Registry  
 
_registry: dict[str, dict] = {}
_reg_lock  = threading.Lock()

_DATA_DIR = Path(__file__).parent / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_track(track_id: str) -> dict | None:
    with _reg_lock:
        return _registry.get(track_id)


def interpolate_at(track_id: str, frame: int, field: str) -> float:
     
    data = get_track(track_id)
    if data is None:
        return 0.0
    frames_dict: dict = data.get("frames", {})
    if not frames_dict:
        return 0.0

    keys = sorted(int(k) for k in frames_dict.keys())
    if frame <= keys[0]:
        return float(frames_dict[str(keys[0])].get(field, 0.0))
    if frame >= keys[-1]:
        return float(frames_dict[str(keys[-1])].get(field, 0.0))

    # Find surrounding keys
    lo = max(k for k in keys if k <= frame)
    hi = min(k for k in keys if k >= frame)
    if lo == hi:
        return float(frames_dict[str(lo)].get(field, 0.0))

    v0 = float(frames_dict[str(lo)].get(field, 0.0))
    v1 = float(frames_dict[str(hi)].get(field, 0.0))
    t  = (frame - lo) / (hi - lo)
    return v0 + (v1 - v0) * t


def list_tracks_for_clip(clip_id: str) -> list[dict]:
    """Return all track summaries stored for a clip_id."""
    out = []
    with _reg_lock:
        for tid, data in _registry.items():
            if data.get("clip_id") == clip_id:
                out.append({
                    "track_id": tid,
                    "label": data.get("label", ""),
                    "from_frame": data.get("from_frame"),
                    "to_frame": data.get("to_frame"),
                    "fps": data.get("fps"),
                    "frame_count": len(data.get("frames", {})),
                })
    return out


def delete_track(track_id: str) -> bool:
    with _reg_lock:
        if track_id in _registry:
            clip_id = _registry[track_id].get("clip_id", "")
            del _registry[track_id]
            # remove sidecar
            _sidecar(clip_id, track_id).unlink(missing_ok=True)
            return True
    return False


#   Main entry point  

def start_track_job(
    clip_id: str,
    video_path: str,
    from_frame: int,
    to_frame: int,
    detection_mode: str = "face",   # "face"|"person"|"text"|"image"|"manual"
    initial_bbox: list | None = None,   # [x,y,w,h] for "manual" or override
    text_pattern: str = "email|phone",
    template_path: str | None = None,   # for "image" mode
    label: str = "",
    fps: float = 30.0,
    comp_w: int = 1920,
    comp_h: int = 1080,
) -> str:
    """Start async tracking job. Returns job_id immediately."""
    label = label or detection_mode
    job = _jobs.create_job(clip_id, label)
    job_id = job["job_id"]
    track_id = str(uuid.uuid4())[:12]

    def _run():
        try:
            # Step 1: detect initial bbox if not provided
            bbox = initial_bbox
            if not bbox:
                import cv2
                cap = cv2.VideoCapture(video_path)
                cap.set(cv2.CAP_PROP_POS_FRAMES, float(from_frame))
                ret, frame = cap.read()
                cap.release()
                if not ret:
                    raise RuntimeError(f"Cannot read frame {from_frame} from {video_path}")
                boxes = _detect(frame, detection_mode, text_pattern, template_path)
                if not boxes:
                    raise RuntimeError(
                        f"No {detection_mode} detected in frame {from_frame}. "
                        "Try manual ROI or a different detection mode."
                    )
                b = boxes[0]
                bbox = [b.x, b.y, b.w, b.h]

            # Step 2: track
            frame_data = track_clip(
                video_path=video_path,
                initial_bbox=tuple(bbox),
                from_frame=from_frame,
                to_frame=to_frame,
                detection_mode=detection_mode,
                text_pattern=text_pattern,
                template_path=template_path,
                job=job,
            )

            # Step 3: store
            track_record = {
                "track_id": track_id,
                "clip_id": clip_id,
                "label": label,
                "detection_mode": detection_mode,
                "from_frame": from_frame,
                "to_frame": to_frame,
                "fps": fps,
                "comp_w": comp_w,
                "comp_h": comp_h,
                "frames": {str(k): v for k, v in frame_data.items()},
                "created_at": time.time(),
            }
            with _reg_lock:
                _registry[track_id] = track_record

            # Save JSON sidecar
            _sidecar(clip_id, track_id).write_text(
                json.dumps(track_record, indent=2), encoding="utf-8"
            )

            _jobs.finish_job(job, track_id)
            logger.info("[tracking] job %s done → track_id=%s (%d frames)",
                        job_id, track_id, len(frame_data))

        except Exception as e:
            logger.error("[tracking] job %s failed: %s", job_id, e, exc_info=True)
            _jobs.fail_job(job, str(e))

    t = threading.Thread(target=_run, daemon=True, name=f"track-{job_id}")
    t.start()
    return job_id


def _detect(frame, mode: str, text_pattern: str, template_path: str | None) -> list[BBox]:
    if mode == "face":
        return detect_faces(frame)
    if mode == "person":
        return detect_persons(frame)
    if mode == "text":
        return detect_text(frame, text_pattern)
    if mode == "image" and template_path:
        return detect_image_template(frame, template_path)
    return []


def _sidecar(clip_id: str, track_id: str) -> Path:
    d = _DATA_DIR / clip_id
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{track_id}.json"


# Load persisted tracks on startup  

def load_all_tracks():
    """Load all JSON sidecars from disk into registry. Call on app startup."""
    count = 0
    for f in _DATA_DIR.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            tid = data.get("track_id")
            if tid:
                with _reg_lock:
                    _registry[tid] = data
                count += 1
        except Exception as e:
            logger.warning("[tracking] failed to load %s: %s", f, e)
    logger.info("[tracking] loaded %d tracks from disk", count)
