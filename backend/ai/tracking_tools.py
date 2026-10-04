"""
Tracking and Privacy tools for the Fade AI agent.

Workflow:
  1. start_track(clip_id, detection_mode) -> {job_id}
  2. wait_for_track(job_id)              -> {track_id}
  3. add_blur_to_track(track_id, clip_id) -> blur applied
     OR add_follow_to_track(track_id, target_clip_id) -> clip follows track
"""
from __future__ import annotations
import time, json
import requests
from langchain_core.tools import tool

_BASE = "http://127.0.0.1:8000"

def _post(path, body):
    r = requests.post(f"{_BASE}{path}", json=body, timeout=30)
    r.raise_for_status()
    return r.json()

def _get(path):
    r = requests.get(f"{_BASE}{path}", timeout=15)
    r.raise_for_status()
    return r.json()


@tool
def start_track(
    clip_id: str,
    detection_mode: str = "face",
    from_frame: int = 0,
    to_frame: int = -1,
    label: str = "",
    text_pattern: str = "email|phone",
    template_path: str | None = None,
    initial_bbox: list[float] | None = None,
) -> str:
    """Start an object-tracking job on a timeline clip. Returns job_id immediately (non-blocking).

    Args:
        clip_id: The clipId of the video or image clip to track.
        detection_mode: "face" | "face_ref" | "person" | "text" | "image" | "manual"
            - face     : auto-detect all faces
            - face_ref : track a specific face — provide template_path (reference photo)
            - person   : full-body detection — provide template_path
            - text     : OCR text matching text_pattern (phone numbers, emails, etc.)
            - image    : template-match template_path image in each frame
            - manual   : fixed bbox defined by initial_bbox [x,y,w,h]
        from_frame: Timeline frame to start (0 = clip start).
        to_frame: Timeline frame to stop (-1 = clip end).
        label: Human-readable name for this track, e.g. "speaker_face".
        text_pattern: Regex for text mode. Shortcuts: "email", "phone", "any".
        template_path: Absolute path to reference image (required for face_ref/person/image).
        initial_bbox: [x, y, w, h] in pixels, required for manual mode only.

    Returns:
        JSON {"job_id": "...", "hint": "call wait_for_track(job_id)"}
    """
    try:
        tl = _get("/timeline/state")
        clip_info = None
        for tr in tl.get("tracks", []):
            for c in tr.get("clips", []):
                if c.get("clipId") == clip_id:
                    clip_info = c
                    break
            if clip_info:
                break
        if not clip_info:
            return json.dumps({"error": f"Clip '{clip_id}' not found in timeline"})

        video_path = (clip_info.get("filepath") or clip_info.get("mediaPath")
                      or clip_info.get("filePath") or "")
        if not video_path:
            assets = _get("/library/assets")
            asset_id = clip_info.get("assetId", "")
            for a in assets:
                if a.get("assetId") == asset_id:
                    video_path = a.get("filepath", "")
                    break
        if not video_path:
            return json.dumps({"error": "Could not resolve media path for this clip."})

        clip_start = clip_info.get("startFrame", 0)
        clip_dur = clip_info.get("durationFrames", clip_info.get("duration", 300))
        if from_frame == 0:
            from_frame = clip_start
        if to_frame == -1:
            to_frame = clip_start + clip_dur - 1

        result = _post("/tracking/start", {
            "clip_id": clip_id,
            "video_path": video_path,
            "from_frame": from_frame,
            "to_frame": to_frame,
            "detection_mode": detection_mode,
            "label": label or detection_mode,
            "text_pattern": text_pattern,
            "template_path": template_path,
            "initial_bbox": initial_bbox,
        })
        if "job_id" in result:
            return json.dumps({"job_id": result["job_id"], "clip_id": clip_id,
                               "mode": detection_mode, "from": from_frame, "to": to_frame,
                               "hint": f"Call wait_for_track('{result['job_id']}') to wait."})
        return json.dumps({"error": result.get("detail", "Failed to start tracking")})
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def check_track_job(job_id: str) -> str:
    """Check status of a tracking job. Returns percent, status, track_id when done."""
    try:
        return json.dumps(_get(f"/tracking/progress/{job_id}"))
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def wait_for_track(job_id: str, timeout_s: int = 120) -> str:
    """Poll until tracking job completes. Returns track_id needed for add_blur_to_track.

    Args:
        job_id: Returned by start_track.
        timeout_s: Max seconds to wait (default 120).
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            s = _get(f"/tracking/progress/{job_id}")
        except Exception as e:
            return json.dumps({"error": f"Poll failed: {e}"})
        if s.get("done"):
            if s.get("error"):
                return json.dumps({"error": s["error"]})
            return json.dumps({"track_id": s.get("track_id"), "job_id": job_id,
                                "frame_count": s.get("frame_count"), "label": s.get("label", "")})
        time.sleep(1.5)
    return json.dumps({"error": f"Timed out after {timeout_s}s. Use check_track_job() later."})


@tool
def list_tracks_for_clip(clip_id: str) -> str:
    """List all completed tracks for a clip. Returns track_id, label, frame range."""
    try:
        result = _get(f"/tracking/tracks/{clip_id}")
        tracks = result.get("tracks", [])
        return json.dumps(tracks, indent=2) if tracks else f"No tracks found for clip '{clip_id}'."
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def delete_track(track_id: str) -> str:
    """Delete a tracking track and its data."""
    try:
        r = requests.delete(f"{_BASE}/tracking/track/{track_id}", timeout=10)
        r.raise_for_status()
        return f"Track '{track_id}' deleted."
    except Exception as e:
        return f"Failed: {e}"


@tool
def add_blur_to_track(
    track_id: str,
    clip_id: str,
    padding: float = 8.0,
    blur_strength: float = 40.0,
) -> str:
    """Create a motion-tracked blur shape that covers the tracked object every frame.

    Use after wait_for_track() to blur faces, text, or any tracked object.

    Args:
        track_id: From wait_for_track() or list_tracks_for_clip().
        clip_id: The clipId of the clip that was tracked.
        padding: Extra pixels of blur around the bbox (default 8).
        blur_strength: Gaussian blur radius (default 40).
    """
    try:
        result = _post("/tracking/add-blur", {
            "track_id": track_id, "clip_id": clip_id,
            "padding": padding, "blur_strength": blur_strength,
        })
        if result.get("ok"):
            return json.dumps({"ok": True, "shape_clip_id": result.get("shape_clip_id"),
                                "keyframe_count": result.get("keyframe_count"),
                                "message": f"Blur applied with {result.get('keyframe_count')} keyframes."})
        return json.dumps({"error": result.get("detail", "Failed to add blur")})
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def add_follow_to_track(
    track_id: str,
    target_clip_id: str,
    properties: list[str] | None = None,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    scale_factor: float = 1.0,
) -> str:
    """Make a clip (text, sticker, emoji) follow a tracking track across all frames.

    Args:
        track_id: Track ID from wait_for_track.
        target_clip_id: The clip to animate (e.g. a text label or shape).
        properties: Properties to animate, default ["pos_x", "pos_y"]. Can add "scale_x","scale_y".
        offset_x/offset_y: Pixel offset from the tracked center.
        scale_factor: Scale tracked size for the target clip.
    """
    try:
        result = _post("/tracking/link-track", {
            "track_id": track_id, "target_clip_id": target_clip_id,
            "properties": properties or ["pos_x", "pos_y"],
            "offset_x": offset_x, "offset_y": offset_y, "scale_factor": scale_factor,
        })
        if result.get("ok"):
            kf = result.get("keyframe_count", 0)
            return json.dumps({"ok": True, "keyframe_count": kf,
                                "message": f"Clip follows track ({kf} keyframes)."})
        return json.dumps({"error": result.get("detail", "Failed to link")})
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def track_and_blur_face(
    clip_id: str,
    label: str = "face",
    padding: float = 8.0,
    from_frame: int = 0,
    to_frame: int = -1,
) -> str:
    """One-shot: track all faces on a clip and blur them. Blocks until done (up to 3 min).

    Args:
        clip_id: Video clip to process.
        label: Track label (default "face").
        padding: Blur padding pixels (default 8).
        from_frame / to_frame: Frame range (defaults to full clip).
    """
    try:
        s = json.loads(start_track.invoke({"clip_id": clip_id, "detection_mode": "face",
                                            "label": label, "from_frame": from_frame, "to_frame": to_frame}))
        if "error" in s:
            return json.dumps({"error": f"Start failed: {s['error']}"})
        w = json.loads(wait_for_track.invoke({"job_id": s["job_id"], "timeout_s": 180}))
        if "error" in w:
            return json.dumps({"error": f"Track failed: {w['error']}"})
        b = json.loads(add_blur_to_track.invoke({"track_id": w["track_id"], "clip_id": clip_id, "padding": padding}))
        if "error" in b:
            return json.dumps({"error": f"Blur failed: {b['error']}"})
        return json.dumps({"ok": True, "track_id": w["track_id"],
                            "shape_clip_id": b.get("shape_clip_id"),
                            "keyframe_count": b.get("keyframe_count"),
                            "message": f"Face tracked + blurred across {w.get('frame_count','?')} frames."})
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def track_and_blur_text(
    clip_id: str,
    text_pattern: str = "phone",
    label: str = "",
    padding: float = 4.0,
    from_frame: int = 0,
    to_frame: int = -1,
) -> str:
    """One-shot: detect and blur sensitive text (phones, emails) on a clip. Blocks until done.

    Args:
        clip_id: Video/image clip to process.
        text_pattern: "phone", "email", "any", or custom regex.
        label: Track label.
        padding: Blur padding pixels.
    """
    try:
        s = json.loads(start_track.invoke({"clip_id": clip_id, "detection_mode": "text",
                                            "label": label or f"text:{text_pattern}",
                                            "text_pattern": text_pattern,
                                            "from_frame": from_frame, "to_frame": to_frame}))
        if "error" in s:
            return json.dumps({"error": f"Start failed: {s['error']}"})
        w = json.loads(wait_for_track.invoke({"job_id": s["job_id"], "timeout_s": 180}))
        if "error" in w:
            return json.dumps({"error": f"Track failed: {w['error']}"})
        b = json.loads(add_blur_to_track.invoke({"track_id": w["track_id"], "clip_id": clip_id, "padding": padding}))
        if "error" in b:
            return json.dumps({"error": f"Blur failed: {b['error']}"})
        return json.dumps({"ok": True, "track_id": w["track_id"],
                            "shape_clip_id": b.get("shape_clip_id"),
                            "message": f"Text '{text_pattern}' tracked + blurred across {w.get('frame_count','?')} frames."})
    except Exception as e:
        return json.dumps({"error": str(e)})


TRACKING_TOOLS = [
    start_track, check_track_job, wait_for_track,
    list_tracks_for_clip, delete_track,
    add_blur_to_track, add_follow_to_track,
    track_and_blur_face, track_and_blur_text,
]
