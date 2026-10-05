 
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
    detection_mode:  str = "face"       # face | person | text | image | manual | face_ref
    initial_bbox: Optional[list] = None   # [x, y, w, h] pixels
    text_pattern: str = "email|phone"
    template_path: Optional[str] = None   # local path to reference image
    label: str = ""
    fps: float = 30.0
    comp_w: int = 1920
    comp_h: int = 1080
 
    auto_blur_clip_id: Optional[str] = None
    auto_blur_padding: float = 8.0


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
        auto_blur_clip_id=req.auto_blur_clip_id,
        auto_blur_padding=req.auto_blur_padding,
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


# Add Blur  

class AddBlurRequest(BaseModel):
    track_id: str
    clip_id: str
    padding: float = 8.0       


@router.get("/debug-state")
def debug_state():
    from backend.state import engine
    tl = engine.activeTimeline
    clips = []
    if tl:
        for tr in tl.tracks:
            for c in tr.clips:
                if getattr(c, "type", "") == "video":
                    clips.append({
                        "id": c.clipId,
                        "filepath": getattr(c, "filepath", None),
                        "assetId": getattr(c, "assetId", None)
                    })
    return {"clips": clips}

@router.post("/add-blur")
def add_blur_track(req: AddBlurRequest):
    """
    For a completed tracking job, create a censor box on the timeline that
    automatically follows the track position and size frame-by-frame.

    Uses KEYFRAMES (not locked expressions) so the user can still manually
    drag or resize the box in the inspector.
    """
    import uuid
    from backend.state import engine
    from backend.timeline.clips.shapeClip import ShapeClip, ShapeStyle
    from backend.animation.animatableProperty import Interpolation

    print(f"\n[add-blur] ========== START ==========", flush=True)
    print(f"[add-blur] track_id={req.track_id} clip_id={req.clip_id} padding={req.padding}", flush=True)

    #   Fetch track & find target video clip  
    track_data = _svc.get_track(req.track_id)
    if track_data is None:
        print(f"[add-blur] ERROR: track {req.track_id!r} not found in registry", flush=True)
        raise HTTPException(404, f"Track {req.track_id!r} not found")

    print(f"[add-blur] Track loaded: {len(track_data.get('frames', {}))} frames, "
          f"from={track_data.get('from_frame')} to={track_data.get('to_frame')}", flush=True)

    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(400, "No active timeline")

    cw = float(getattr(tl, "width", 1920))
    ch = float(getattr(tl, "height", 1080))
    comp_cx = cw * 0.5
    comp_cy = ch * 0.5
    print(f"[add-blur] Composition: {cw}x{ch}, center=({comp_cx}, {comp_cy})", flush=True)

    actual_clip_id = req.clip_id or track_data.get("clip_id")
    target_video = None
    for tr in tl.tracks:
        for c in tr.clips:
            if getattr(c, "clipId", None) == actual_clip_id:
                target_video = c
                break
        if target_video:
            break

    if target_video:
        print(f"[add-blur] Found target video clip: {actual_clip_id[:8]} "
              f"start={target_video.startFrame} dur={target_video.duration}", flush=True)
    else:
        print(f"[add-blur] WARNING: target video clip {actual_clip_id[:8]} NOT FOUND in timeline", flush=True)

    iw, ih = cw, ch
    if target_video and hasattr(target_video, "assetId"):
        from backend.state import _library
        asset = _library.get(target_video.assetId)
        if asset:
            if getattr(asset, "width", 0) > 0:
                iw = float(asset.width)
            if getattr(asset, "height", 0) > 0:
                ih = float(asset.height)
            print(f"[add-blur] Asset dimensions: {iw}x{ih}", flush=True)
        
    # Fallback to reading the file directly if library is empty or width is 0
    video_path = track_data.get("video_path")
    if not video_path and target_video:
        video_path = getattr(target_video, "filepath", None)
        
    if iw == cw and ih == ch and video_path:
        try:
            import cv2
            cap = cv2.VideoCapture(video_path)
            if cap.isOpened():
                vid_w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                vid_h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                if vid_w > 0 and vid_h > 0:
                    iw, ih = float(vid_w), float(vid_h)
                    print(f"[add-blur] Video file dimensions: {iw}x{ih}", flush=True)
            cap.release()
        except Exception as e:
            print(f"[add-blur] Failed to read video dimensions from {video_path}: {e}", flush=True)

    # Letterbox mapping
    lb_scale = min(cw / iw, ch / ih) if iw > 0 and ih > 0 else 1.0
    dx = (cw - iw * lb_scale) / 2.0
    dy = (ch - ih * lb_scale) / 2.0
    print(f"[add-blur] Letterbox: scale={lb_scale:.4f} offset=({dx:.1f}, {dy:.1f})", flush=True)

    # Video transform mapping
    v_tx, v_ty, v_sx, v_sy = 0.0, 0.0, 1.0, 1.0
    if target_video and hasattr(target_video, "transform"):
        vt = target_video.transform
        v_tx = float(vt.position.x.baseValue)
        v_ty = float(vt.position.y.baseValue)
        v_sx = float(vt.scale.x.baseValue)
        v_sy = float(vt.scale.y.baseValue)
    print(f"[add-blur] Video transform: tx={v_tx} ty={v_ty} sx={v_sx} sy={v_sy}", flush=True)

    def map_coords(raw_x, raw_y, raw_w, raw_h):
        """Convert tracker pixel coords (top-left origin) to ShapeClip
        transform coords (0,0 = center of composition)."""
        # Step 1: apply letterbox scaling
        lx = raw_x * lb_scale + dx
        ly = raw_y * lb_scale + dy
        lw = raw_w * lb_scale
        lh = raw_h * lb_scale
        # Step 2: apply video transform (scale around center + translate)
        abs_x = v_sx * (lx - comp_cx) + v_tx + comp_cx
        abs_y = v_sy * (ly - comp_cy) + v_ty + comp_cy
        final_w = lw * v_sx
        final_h = lh * v_sy
        # Step 3: convert to centered coordinates (0,0 = center of comp)
        centered_x = abs_x - comp_cx
        centered_y = abs_y - comp_cy
        return centered_x, centered_y, final_w, final_h

    from_frame: int = track_data.get("from_frame", 0)
    to_frame:   int = track_data.get("to_frame", 0)
    duration = max(1, to_frame - from_frame + 1)
    frames: dict = track_data.get("frames", {})
    print(f"[add-blur] Frame range: {from_frame}-{to_frame} duration={duration} "
          f"tracked_frames={len(frames)}", flush=True)

    # Use the first frame for initial size/position
    if frames:
        first_key = min(frames.keys(), key=int)
        first = frames[first_key]
        raw_w = max(10.0, float(first.get("w", 100)) + req.padding * 2)
        raw_h = max(10.0, float(first.get("h",  40)) + req.padding * 2)
        raw_cx = float(first.get("cx", cw / 2))
        raw_cy = float(first.get("cy", ch / 2))
        print(f"[add-blur] First frame ({first_key}): raw cx={raw_cx:.1f} cy={raw_cy:.1f} "
              f"w={raw_w:.1f} h={raw_h:.1f}", flush=True)
    else:
        raw_w, raw_h, raw_cx, raw_cy = 200.0, 80.0, cw / 2, ch / 2
        print(f"[add-blur] WARNING: No frames in track data! Using defaults", flush=True)

    init_cx, init_cy, init_w, init_h = map_coords(raw_cx, raw_cy, raw_w, raw_h)
    # Prevent completely degenerate sizes
    init_w, init_h = max(init_w, 1.0), max(init_h, 1.0)
    print(f"[add-blur] Mapped initial: cx={init_cx:.1f} cy={init_cy:.1f} "
          f"w={init_w:.1f} h={init_h:.1f}", flush=True)

    # ── 2. Find a free video track BELOW the target video (Foreground) ────────
    actual_clip_id = req.clip_id or track_data.get("clip_id")
    video_track_idx = 0
    for i, tr in enumerate(tl.tracks):
        if any(getattr(c, "clipId", None) == actual_clip_id for c in tr.clips):
            video_track_idx = i
            break

    target_track = None
    # Only search tracks that render OVER the video track (higher index)
    for i in range(video_track_idx + 1, len(tl.tracks)):
        tr = tl.tracks[i]
        if getattr(tr, "type", "video") != "video" or getattr(tr, "isAudio", lambda: False)():
            continue
        occupied = any(
            c.startFrame < from_frame + duration and c.startFrame + c.duration > from_frame
            for c in tr.clips
        )
        if not occupied:
            target_track = tr
            break

    if target_track is None:
        from backend.timeline.tracks.videoTrack import VideoTrack
        new_tr = VideoTrack(name=f"Censor {req.track_id[:6]}")
        # Append to the end of the timeline so it renders correctly as the foreground layer
        tl.tracks.append(new_tr)
        target_track = new_tr
        print(f"[add-blur] Created new track: '{new_tr.name}'", flush=True)
    else:
        print(f"[add-blur] Using existing track at index {tl.tracks.index(target_track)}", flush=True)

    #   Create a Shape clip  
    from backend.timeline.clips.shapeClip import ShapeClip, ShapeStyle

    style = ShapeStyle()
    style.shapeType   = "ellipse"
    style.radiusX = init_w / 2    # half-width of tracked bbox
    style.radiusY = init_h / 2    # half-height of tracked bbox
    style.fillColor   = [0.0, 0.0, 0.0, 1.0]   # black — rendered as blur mask
    style.fillOpacity = 1.0
    style.strokeWidth = 0.0

    shape_clip = ShapeClip(
        clipId=str(uuid.uuid4()),
        startFrame=from_frame,
        duration=duration,
        style=style,
    )

    shape_clip.transform.position.x.setBaseValue(init_cx)
    shape_clip.transform.position.y.setBaseValue(init_cy)
    shape_clip.transform.scale.x.setBaseValue(1.0)
    shape_clip.transform.scale.y.setBaseValue(1.0)

    target_track.clips.append(shape_clip)
    clip_id = shape_clip.clipId
    print(f"[add-blur] Created shape clip: {clip_id[:8]} start={from_frame} dur={duration}", flush=True)

    from backend.state import _clipTrackMap
    _clipTrackMap[clip_id] = tl.tracks.index(target_track)

    # ── 4. Bake keyframes for position (tracks face movement) ─────────────────
    BAKE_EVERY = 1  # Bake EVERY frame for accuracy (was 3 — caused jumping)

    sorted_frame_keys = sorted(frames.keys(), key=int)
    baked_count = 0
    for raw_key in sorted_frame_keys:
        abs_frame = int(raw_key)
        fd = frames[raw_key]
        
        raw_cx = float(fd.get("cx", cw / 2))
        raw_cy = float(fd.get("cy", ch / 2))
        raw_w  = max(10.0, float(fd.get("w", 100)) + req.padding * 2)
        raw_h  = max(10.0, float(fd.get("h",  40)) + req.padding * 2)

        cx, cy, bw, bh = map_coords(raw_cx, raw_cy, raw_w, raw_h)

        local = abs_frame - from_frame
        if local < 0 or local >= duration:
            continue

        shape_clip.transform.position.x.addKeyframe(local, cx, Interpolation.Bezier)
        shape_clip.transform.position.y.addKeyframe(local, cy, Interpolation.Bezier)

        sx = bw / init_w if init_w > 0 else 1.0
        sy = bh / init_h if init_h > 0 else 1.0
        shape_clip.transform.scale.x.addKeyframe(local, sx, Interpolation.Bezier)
        shape_clip.transform.scale.y.addKeyframe(local, sy, Interpolation.Bezier)
        baked_count += 1

        # Debug: log first 5 and last keyframe
        if baked_count <= 5 or abs_frame == int(sorted_frame_keys[-1]):
            print(f"[add-blur] KF local={local} abs={abs_frame}: "
                  f"pos=({cx:.1f},{cy:.1f}) scale=({sx:.3f},{sy:.3f}) "
                  f"raw=({raw_cx:.1f},{raw_cy:.1f},{raw_w:.1f},{raw_h:.1f})", flush=True)

    # Verify keyframes were actually added
    kf_count_x = len(shape_clip.transform.position.x.track)
    kf_count_y = len(shape_clip.transform.position.y.track)
    kf_count_sx = len(shape_clip.transform.scale.x.track)
    print(f"[add-blur] Baked {baked_count} keyframes total", flush=True)
    print(f"[add-blur] position.x keyframes: {kf_count_x}, position.y: {kf_count_y}, scale.x: {kf_count_sx}", flush=True)
    print(f"[add-blur] position.x isAnimated: {shape_clip.transform.position.x.isAnimated}", flush=True)

    # ── 5. Notify frontend ────────────────────────────────────────────────────
    try:
        from backend.events import notify
        notify("timeline")
        print(f"[add-blur] Notified frontend (timeline)", flush=True)
    except Exception as e:
        print(f"[add-blur] Notify failed: {e}", flush=True)

    print(f"[add-blur] ========== DONE ==========\n", flush=True)

    return {
        "ok": True,
        "blur_clip_id": clip_id,
        "track_id": req.track_id,
        "from_frame": from_frame,
        "to_frame": to_frame,
        "duration": duration,
        "keyframes_baked": baked_count,
    }


