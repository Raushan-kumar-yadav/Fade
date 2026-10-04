 
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
    BBox, detect_faces, detect_persons, detect_text, detect_image_template,
    detect_face_by_reference, extract_face_embedding,
)
from backend.tracking.tracker import track_clip

logger = logging.getLogger(__name__)

# Track Registry  
 
_registry: dict[str, dict] = {}
_reg_lock  = threading.Lock()

_DATA_DIR = Path(__file__).parent / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_data_dir() -> Path:
    """Return current tracking data directory."""
    return _DATA_DIR


def set_data_dir(new_dir: str | Path) -> None:
    """Switch tracking data directory (called by project save/load)."""
    global _DATA_DIR
    _DATA_DIR = Path(new_dir)
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("[tracking] data dir switched to: %s", _DATA_DIR)
    print(f"[tracking] data dir switched to: {_DATA_DIR}", flush=True)


def copy_all_tracks_to(dest_dir: str | Path, clip_ids: set[str] | None = None) -> int:
    """Write in-registry tracks to dest_dir, preserving clip_id subdirs.

    Args:
        dest_dir: Destination directory.
        clip_ids: If given, only copy tracks whose clip_id is in this set
                  (i.e. only current project's clips). If None, copy all.
    Returns:
        Number of tracks written.
    """
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    with _reg_lock:
        for tid, data in _registry.items():
            clip_id = data.get("clip_id", "unknown")
            if clip_ids is not None and clip_id not in clip_ids:
                continue  # skip tracks from other projects
            sub = dest / clip_id
            sub.mkdir(parents=True, exist_ok=True)
            out_path = sub / f"{tid}.json"
            out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            count += 1
            print(f"[tracking] saved track {tid} -> {out_path}", flush=True)
    logger.info("[tracking] saved %d tracks to %s", count, dest)
    return count


def load_all_tracks() -> int:
    """Scan _DATA_DIR for JSON sidecars and load them into the in-memory registry.
    Called by project.py when loading a project that has bundled tracking data."""
    count = 0
    with _reg_lock:
        _registry.clear()
    for clip_dir in _DATA_DIR.iterdir():
        if not clip_dir.is_dir():
            continue
        for json_file in clip_dir.glob("*.json"):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                tid = data.get("track_id", json_file.stem)
                with _reg_lock:
                    _registry[tid] = data
                count += 1
            except Exception as e:
                print(f"[tracking] Failed to load {json_file}: {e}", flush=True)
    print(f"[tracking] Loaded {count} tracks from {_DATA_DIR}", flush=True)
    return count


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

    print(f"[tracking] START job={job_id} track={track_id} clip={clip_id[:8]} "
          f"mode={detection_mode} frames={from_frame}-{to_frame} "
          f"video={video_path} comp={comp_w}x{comp_h}", flush=True)

    # Pre-compute face reference embedding (outside thread — fail fast)
    ref_embedding = None
    if detection_mode == "face_ref":
        if not template_path:
            raise ValueError("face_ref mode requires template_path (reference face image)")
        import cv2
        ref_img = cv2.imread(template_path)
        if ref_img is None:
            raise ValueError(f"Cannot read reference image: {template_path}")
        ref_embedding = extract_face_embedding(ref_img)
        if ref_embedding is None:
            raise ValueError("No face detected in the reference image. Use a clear face photo.")
        print(f"[tracking] face_ref: embedding extracted from {template_path}", flush=True)

    def _run():
        try:
            # Check if this is an image file  
            _IMG_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif', '.webp', '.svg'}
            is_image = Path(video_path).suffix.lower() in _IMG_EXTS

            if is_image:
                # Image clip: single-frame detection only  
                import cv2
                img = cv2.imread(video_path)
                if img is None:
                    raise RuntimeError(f"Cannot read image: {video_path}")

                bbox = initial_bbox
                if not bbox:
                    boxes = _detect(img, detection_mode, text_pattern, template_path)
                    if not boxes:
                        raise RuntimeError(
                            f"No {detection_mode} detected in image. "
                            "Try manual ROI or a different detection mode."
                        )
                    b = boxes[0]
                    bbox = [b.x, b.y, b.w, b.h]

                x, y, w, h = [float(v) for v in bbox]
                # Produce tracking data for every frame of the clip duration
                frame_data = {}
                for fi in range(from_frame, to_frame + 1):
                    frame_data[fi] = {
                        "cx": x + w / 2, "cy": y + h / 2,
                        "w": w, "h": h, "confidence": 1.0,
                    }
                print(f"[tracking] Image mode: detected bbox at ({x:.0f},{y:.0f},{w:.0f},{h:.0f}), "
                      f"replicated to {len(frame_data)} frames", flush=True)

            else:
                 
                 
                bbox = initial_bbox
                if not bbox:
                    import cv2
                    cap = cv2.VideoCapture(video_path)
                    
                     
                    scan_frames = []
                    frame_range = max(1, to_frame - from_frame)
                    for i in range(5):
                        scan_frames.append(from_frame + int(frame_range * i / 4)) if frame_range > 1 else scan_frames.append(from_frame)
                    scan_frames = list(dict.fromkeys(scan_frames))  # deduplicate
                    
                    boxes = []
                    checked_frame = from_frame
                    for sf in scan_frames:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, float(sf))
                        ret, frame = cap.read()
                        if not ret:
                            continue
                        checked_frame = sf
                        boxes = _detect(frame, detection_mode, text_pattern, template_path, ref_embedding)
                        if boxes:
                            break
                    cap.release()
                    
                    if not boxes:
                        raise RuntimeError(
                            f"No {detection_mode} detected in any of {len(scan_frames)} scanned frames. "
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
                    ref_embedding=ref_embedding,
                    job=job,
                )

            # Step 3: store
            track_record = {
                "track_id": track_id,
                "clip_id": clip_id,
                "label": label,
                "video_path": video_path,
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

            # Tracks are stored in RAM only — written to disk on project save.
            # Do NOT write to backend/tracking/data here.
            _jobs.finish_job(job, track_id)
            print(f"[tracking] DONE job={job_id} track={track_id} "
                  f"frames={len(frame_data)} (RAM only, write on save)", flush=True)
            logger.info("[tracking] job %s done -> track_id=%s (%d frames)",
                        job_id, track_id, len(frame_data))

        except Exception as e:
            logger.error("[tracking] job %s failed: %s", job_id, e, exc_info=True)
            _jobs.fail_job(job, str(e))

    t = threading.Thread(target=_run, daemon=True, name=f"track-{job_id}")
    t.start()
    return job_id


def _detect(frame, mode: str, text_pattern: str, template_path: str | None,
            ref_embedding=None) -> list[BBox]:
    if mode == "face":
        return detect_faces(frame)
    if mode == "face_ref" and ref_embedding is not None:
        return detect_face_by_reference(frame, ref_embedding)
    if mode == "person":
        return detect_persons(frame)
    if mode == "text":
        return detect_text(frame, text_pattern)
    if mode == "image" and template_path:
        return detect_image_template(frame, template_path)
    return []


def _sidecar_path(dest_dir: Path, clip_id: str, track_id: str) -> Path:
    """Return the sidecar path inside a given destination directory."""
    d = dest_dir / clip_id
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{track_id}.json"



