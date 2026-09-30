 
from __future__ import annotations
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from backend.tracking import jobs as _jobs
from backend.tracking import service as _svc

router = APIRouter(prefix="/tracking", tags=["tracking"])


#   Request models  

class StartTrackRequest(BaseModel):
    clip_id: str
    video_path: str
    from_frame: int = 0
    to_frame: int = -1
    detection_mode:  str = "face"       # face | person | text | image | manual
    initial_bbox: Optional[list] = None   # [x, y, w, h] pixels
    text_pattern: str = "email|phone"
    template_path: Optional[str] = None   # local path to reference image
    label: str = ""
    fps: float = 30.0
    comp_w: int = 1920
    comp_h: int = 1080


class LinkTrackRequest(BaseModel):
    track_id:     str
    target_clip_id: str
    properties:   list[str] = ["pos_x", "pos_y"]
    offset_x: float = 0.0
    offset_y: float = 0.0
    scale_factor: float = 1.0


#   Routes  

@router.post("/start")
def start_tracking(req: StartTrackRequest):
     
    if req.detection_mode == "manual" and not req.initial_bbox:
        raise HTTPException(400, "initial_bbox required for manual mode")
    if req.detection_mode == "image" and not req.template_path:
        raise HTTPException(400, "template_path required for image mode")
    if req.template_path and not os.path.exists(req.template_path):
        raise HTTPException(400, f"template_path not found: {req.template_path}")

    job_id = _svc.start_track_job(
        clip_id=req.clip_id,
        video_path=req.video_path,
        from_frame=req.from_frame,
        to_frame=req.to_frame,
        detection_mode=req.detection_mode,
        initial_bbox=req.initial_bbox,
        text_pattern=req.text_pattern,
        template_path=req.template_path,
        label=req.label or req.detection_mode,
        fps=req.fps,
        comp_w=req.comp_w,
        comp_h=req.comp_h,
    )
    return {"ok": True, "job_id": job_id}


@router.get("/progress/{job_id}")
def get_progress(job_id: str):
    """Poll tracking job progress."""
    job = _jobs.get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id!r} not found")
    return job


@router.post("/cancel/{job_id}")
def cancel_tracking(job_id: str):
    ok = _jobs.cancel_job(job_id)
    return {"ok": ok}


@router.get("/tracks/{clip_id}")
def list_tracks(clip_id: str):
    """List all completed tracks for a clip."""
    return {"tracks": _svc.list_tracks_for_clip(clip_id)}


@router.get("/track/{track_id}")
def get_track(track_id: str):
    """Get full track data including per-frame positions."""
    data = _svc.get_track(track_id)
    if data is None:
        raise HTTPException(404, f"Track {track_id!r} not found")
    return data


@router.delete("/track/{track_id}")
def delete_track(track_id: str):
    ok = _svc.delete_track(track_id)
    return {"ok": ok}


@router.get("/frame/{track_id}/{frame}")
def get_frame(track_id: str, frame: int):
    """
    Get interpolated tracking data at a specific frame.
    Used by the expression evaluator at render time.
    """
    data = _svc.get_track(track_id)
    if data is None:
        raise HTTPException(404, f"Track {track_id!r} not found")
    return {
        "frame": frame,
        "cx": _svc.interpolate_at(track_id, frame, "cx"),
        "cy": _svc.interpolate_at(track_id, frame, "cy"),
        "w": _svc.interpolate_at(track_id, frame, "w"),
        "h": _svc.interpolate_at(track_id, frame, "h"),
        "confidence": _svc.interpolate_at(track_id, frame, "confidence"),
    }


@router.get("/jobs")
def list_jobs():
    """List all tracking jobs (running + completed)."""
    return {"jobs": _jobs.list_jobs()}


# ── Add Blur ─────────────────────────────────────────────────────────────────

class AddBlurRequest(BaseModel):
    track_id: str
    clip_id: str
    padding: float = 8.0        # extra pixels around the tracked region


@router.post("/add-blur")
def add_blur_track(req: AddBlurRequest):
    """
    For a completed tracking job, create a censor box on the timeline that
    automatically follows the track position and size frame-by-frame.

    Uses KEYFRAMES (not locked expressions) so the user can still manually
    drag or resize the box in the inspector.

    Steps:
      1. Look up the track data.
      2. Find a free video track (or create one).
      3. Create a fully-opaque black shape clip sized to the tracked region.
      4. Bake one keyframe per tracked frame for pos_x, pos_y, scale_x, scale_y.
    """
    import uuid
    from backend.state import engine
    from backend.timeline.clips.shapeClip import ShapeClip, ShapeStyle
    from backend.animation.animatableProperty import Interpolation

    # ── 1. Fetch track ────────────────────────────────────────────────────────
    track_data = _svc.get_track(req.track_id)
    if track_data is None:
        raise HTTPException(404, f"Track {req.track_id!r} not found")

    from_frame: int = track_data.get("from_frame", 0)
    to_frame:   int = track_data.get("to_frame", 0)
    duration = max(1, to_frame - from_frame + 1)

    frames: dict = track_data.get("frames", {})

    # Use the first frame for initial size/position
    if frames:
        first = frames[min(frames.keys(), key=int)]
        init_w  = max(10.0, float(first.get("w", 100)) + req.padding * 2)
        init_h  = max(10.0, float(first.get("h",  40)) + req.padding * 2)
        init_cx = float(first.get("cx", 960))
        init_cy = float(first.get("cy", 540))
    else:
        init_w, init_h, init_cx, init_cy = 200.0, 80.0, 960.0, 540.0

    # ── 2. Find a free video track ────────────────────────────────────────────
    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(400, "No active timeline")

    target_track = None
    for tr in tl.tracks:
        if getattr(tr, "type", "video") != "video":
            continue
        occupied = any(
            c.startFrame < from_frame + duration and c.startFrame + c.duration > from_frame
            for c in tr.clips
        )
        if not occupied:
            target_track = tr
            break

    if target_track is None:
        from backend.timeline.timeline import Track
        new_tr = Track(name=f"Censor {req.track_id[:6]}")
        tl.tracks.append(new_tr)
        target_track = new_tr

    # ── 3. Create a fully-opaque solid shape clip ─────────────────────────────
    style = ShapeStyle()
    style.shapeType   = "rect"
    style.width       = init_w
    style.height      = init_h
    style.fillColor   = [0.0, 0.0, 0.0, 1.0]   # FULLY opaque — guaranteed to cover
    style.fillOpacity = 1.0
    style.strokeWidth = 0.0
    style.cornerRadius = 2.0

    shape_clip = ShapeClip(
        clipId=str(uuid.uuid4()),
        startFrame=from_frame,
        duration=duration,
        style=style,
    )
    # Set the static base position (shown before first keyframe)
    shape_clip.transform.position.x.base = init_cx
    shape_clip.transform.position.y.base = init_cy

    target_track.clips.append(shape_clip)
    clip_id = shape_clip.clipId

    # ── 4. Bake keyframes for position and size ───────────────────────────────
    # Bake every Nth frame to keep performance reasonable (not every single frame)
    BAKE_EVERY = 3   # keyframe every 3 frames; interpolation fills gaps smoothly

    sorted_frame_keys = sorted(frames.keys(), key=int)

    for raw_key in sorted_frame_keys:
        abs_frame = int(raw_key)
        fd = frames[raw_key]
        cx = float(fd.get("cx", init_cx))
        cy = float(fd.get("cy", init_cy))
        w  = max(10.0, float(fd.get("w",  init_w  - req.padding * 2)) + req.padding * 2)
        h  = max(10.0, float(fd.get("h",  init_h  - req.padding * 2)) + req.padding * 2)

        # Only bake every Nth frame (always include first and last)
        local = abs_frame - from_frame
        if local % BAKE_EVERY != 0 and abs_frame != to_frame:
            continue

        # pos_x / pos_y in timeline-absolute frames
        shape_clip.transform.position.x.addKeyframe(local, cx, Interpolation.Bezier)
        shape_clip.transform.position.y.addKeyframe(local, cy, Interpolation.Bezier)

        # scale_x / scale_y: scale = current_dim / base_dim
        sx = w / init_w
        sy = h / init_h
        shape_clip.transform.scale.x.addKeyframe(local, sx, Interpolation.Bezier)
        shape_clip.transform.scale.y.addKeyframe(local, sy, Interpolation.Bezier)

    # ── 5. Notify frontend ────────────────────────────────────────────────────
    try:
        from backend.events import notify
        notify("timeline")
    except Exception:
        pass

    return {
        "ok": True,
        "blur_clip_id": clip_id,
        "track_id": req.track_id,
        "from_frame": from_frame,
        "to_frame": to_frame,
        "duration": duration,
        "keyframes_baked": len([k for k in sorted_frame_keys
                                if (int(k) - from_frame) % BAKE_EVERY == 0]),
    }


