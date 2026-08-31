 
from __future__ import annotations
import json
import httpx
from langchain_core.tools import tool

# helpers  

_PORT: int = 8000

def _base() -> str:
    return f"http://127.0.0.1:{_PORT}"

def _get(path: str) -> dict:
    r = httpx.get(f"{_base()}{path}", timeout=10)
    r.raise_for_status()
    return r.json()

def _get_long(path: str, timeout: int = 300) -> dict:
    """Like _get but with a long timeout for endpoints that run heavy CPU work
    (e.g. Whisper transcription on CPU can take 30-120s per file)."""
    r = httpx.get(f"{_base()}{path}", timeout=timeout)
    r.raise_for_status()
    return r.json()

def _post(path: str, body: dict | None = None) -> dict:
    r = httpx.post(f"{_base()}{path}", json=body or {}, timeout=30)
    r.raise_for_status()
    return r.json()

def _post_long(path: str, body: dict | None = None, timeout: int = 300) -> dict:
    """Like _post but with a long timeout for heavy AI generation calls (TTS, video)."""
    r = httpx.post(f"{_base()}{path}", json=body or {}, timeout=timeout)
    r.raise_for_status()
    return r.json()

def _delete(path: str) -> dict:
    r = httpx.delete(f"{_base()}{path}", timeout=10)
    r.raise_for_status()
    return r.json()

def _patch(path: str, body: dict | None = None) -> dict:
    r = httpx.patch(f"{_base()}{path}", json=body or {}, timeout=30)
    r.raise_for_status()
    return r.json()

def set_port(port: int) -> None:
    global _PORT
    _PORT = port

# timeline read  
 
@tool
def get_timeline_state() -> str:
    """Return the full current timeline state as JSON (tracks, clips, durations, fps)."""
    data = _get("/timeline/state")
    return json.dumps(data, indent=2)

@tool
def get_library() -> str:
    """Return the list of all imported media assets (assetId, filename, type)."""
    data = _get("/library/assets")
    return json.dumps(data, indent=2)

@tool
def get_playback_state() -> str:
    """Return current playback state: frame, fps, totalFrames, playing."""
    data = _get("/playback/state")
    return json.dumps(data, indent=2)

# playback  

@tool
def seek_to(frame: int) -> str:
    """Seek the timeline playhead to a specific frame number."""
    _post("/playback/seek", {"frame": frame})
    return f"Seeked to frame {frame}"

# clip editing  

@tool
def split_clip(clip_id: str, frame: int) -> str:
    """Split a clip at a specific timeline frame, creating two clips.
    Args:
        clip_id: The clipId of the clip to split.
        frame: The timeline frame number where the split should occur.
    """
    result = _post("/timeline/split-clip", {"clipId": clip_id, "frame": frame})
    return f"Split clip {clip_id} at frame {frame}. New clip IDs: {result}"

@tool
def trim_clip(clip_id: str, side: str, frame_delta: int) -> str:
    """Trim the start or end of a clip by a number of frames.
    Args:
        clip_id: The clipId of the clip to trim.
        side: 'left' to trim the start, 'right' to trim the end.
        frame_delta: Number of frames to trim (positive number).
    """
    result = _post("/timeline/trim-clip", {
        "clipId": clip_id,
        "side": side,
        "frameDelta": frame_delta
    })
    return f"Trimmed {side} of clip {clip_id} by {frame_delta} frames."

@tool
def move_clip(clip_id: str, new_start_frame: int, track_index: int) -> str:
    """Move a clip to a new position on the timeline.
    Args:
        clip_id: The clipId to move.
        new_start_frame: The new start frame on the timeline.
        track_index: The track index (0-based) to move the clip to.
    """
    result = _post("/timeline/move-clip", {
        "clipId": clip_id,
        "newStartFrame": new_start_frame,
        "trackIndex": track_index
    })
    return f"Moved clip {clip_id} to frame {new_start_frame} on track {track_index}."

@tool
def delete_clip(clip_id: str) -> str:
    """Remove a clip from the timeline entirely.
    Args:
        clip_id: The clipId to delete.
    """
    _delete(f"/timeline/clips/{clip_id}")
    return f"Deleted clip {clip_id}."

# effects  

@tool
def get_effects_catalog() -> str:
    """Return all available visual effects and their parameter schemas."""
    data = _get("/effects/catalog")
    return json.dumps(data, indent=2)

@tool
def add_effect(clip_id: str, effect_type: str) -> str:
    """Add a visual effect to a clip.
    Args:
        clip_id: The clipId to apply the effect to.
        effect_type: Effect type ID, e.g. 'blur', 'brightness_contrast', 'color_grade'.
                     Use get_effects_catalog() to see valid types.
    """
    result = _post(f"/clips/{clip_id}/effects", {"effectType": effect_type})
    return f"Added effect '{effect_type}' to clip {clip_id}. effectId: {result.get('effectId')}"

@tool
def remove_effect(clip_id: str, effect_id: str) -> str:
    """Remove a visual effect from a clip.
    Args:
        clip_id: The clipId that has the effect.
        effect_id: The effectId to remove.
    """
    _delete(f"/clips/{clip_id}/effects/{effect_id}")
    return f"Removed effect {effect_id} from clip {clip_id}."

@tool
def set_effect_param(clip_id: str, effect_id: str, params: str) -> str:
    """Update parameters of an existing effect. params is a JSON string of key-value pairs.
    Args:
        clip_id: The clipId.
        effect_id: The effectId to update.
        params: JSON string like '{"intensity": 0.5, "radius": 10}'.
    """
    p = json.loads(params)
    _post(f"/clips/{clip_id}/effects/{effect_id}", p)
    return f"Updated effect {effect_id} on clip {clip_id} with {params}."

# clip params  

@tool
def set_clip_param(clip_id: str, key: str, value: float) -> str:
    """Set an animatable parameter on a clip (opacity, pos_x, pos_y, scale_x, scale_y, rotation).
    Args:
        clip_id: The clipId.
        key: Parameter name: 'opacity', 'pos_x', 'pos_y', 'scale_x', 'scale_y', 'rotation'.
        value: Numeric value (opacity: 0.0-1.0, pos: pixels, scale: 1.0=100%, rotation: degrees).
    """
    _post(f"/clips/{clip_id}/params/{key}", {"value": value})
    return f"Set {key}={value} on clip {clip_id}."


@tool
def update_clip(clip_id: str, params: dict) -> str:
    """Update any combination of properties on a single clip in one call.

    This is the preferred way to change clip properties when you know the clipId.
    Pass a flat dict with any mix of the keys below — only the keys you include
    are changed; everything else is left untouched.

    TRANSFORM / ANIMATABLE  (all numeric):
        pos_x, pos_y – position in pixels
        scale_x, scale_y – scale (1.0 = 100%)
        rotation – degrees
        opacity – 0.0 – 1.0
        anchor_x, anchor_y – anchor point in pixels

    TIMING:
        startFrame – move clip start
        duration – clip length in frames
        (both optional; omit either to keep its current value)

    TEXT STYLE  (TextClip only — pass any TextStyle fields):
        text – new text content
        fontSize – pt size
        fontFamily – font name
        bold, italic – bool
        color – [r, g, b, a] 0-255
        textAlign – 'left' | 'center' | 'right'
        letterSpacing – em units
        lineHeight – em units
        (and any other TextStyle field by its camelCase name)

    SHAPE STYLE  (ShapeClip only):
        fillColor – [r, g, b, a] 0-255
        strokeColor – [r, g, b, a] 0-255
        strokeWidth – px
        borderRadius – px
        width, height – dimensions in px

    WEBCOMP PARAMS  (WebCompClip only):
        Pass any key that the component exposes; values are forwarded directly.

    Examples:
        update_clip(id, {"opacity": 0.5, "pos_x": 100})
        update_clip(id, {"text": "Hello", "fontSize": 64, "bold": True})
        update_clip(id, {"startFrame": 30, "duration": 90})
        update_clip(id, {"fillColor": [255, 80, 0, 255], "strokeWidth": 3})

    Args:
        clip_id: The clipId to update.
        params:  Dict of property names → values (see categories above).
    """
    TRANSFORM_PARAMS = {"pos_x", "pos_y", "scale_x", "scale_y",
                        "rotation", "opacity", "anchor_x", "anchor_y"}
    TIMING_PARAMS    = {"startFrame", "duration"}

    # Partition keys into categories
    transform = {k: params[k] for k in params if k in TRANSFORM_PARAMS}
    timing    = {k: params[k] for k in params if k in TIMING_PARAMS}
    other = {k: params[k] for k in params
             if k not in TRANSFORM_PARAMS and k not in TIMING_PARAMS}

    # --- 1. Transform / animatable params ---
    applied: list[str] = []
    errors:  list[str] = []

    for key, val in transform.items():
        try:
            _post(f"/clips/{clip_id}/params/{key}", {"value": float(val)})
            applied.append(f"{key}={val}")
        except Exception as exc:
            errors.append(f"{key}: {exc}")

    # --- 2. Timing ---
    if timing:
        try:
            _post(f"/clips/{clip_id}/trim", timing)
            applied.append(f"timing={timing}")
        except Exception as exc:
            errors.append(f"timing: {exc}")

    # --- 3. Text / Shape / WebComp style — try all routes; first success wins ---
    if other:
        # Separate text key from rest of style
        text_content = other.pop("text", None)

        # Try text clip
        try:
            body: dict = {}
            if text_content is not None:
                body["text"] = text_content
            if other:
                body["style"] = other
            if body:
                _patch(f"/clips/text/{clip_id}", body)
                if text_content is not None:
                    applied.append(f"text={text_content!r}")
                if other:
                    applied.append(f"style={list(other.keys())}")
        except Exception:
            # Not a text clip — try shape
            if other:
                try:
                    _patch(f"/clips/shape/{clip_id}", {"style": other})
                    applied.append(f"shape_style={list(other.keys())}")
                except Exception:
                    # Fall back to WebComp params
                    try:
                        all_params = dict(other)
                        if text_content is not None:
                            all_params["text"] = text_content
                        _post(f"/webcomp/{clip_id}/params",
                              {"params": all_params})
                        applied.append(f"webcomp_params={list(all_params.keys())}")
                    except Exception as exc:
                        errors.append(f"style/params: {exc}")

    if errors:
        return (f"update_clip {clip_id[:8]}: applied [{', '.join(applied)}] "
                f"| ERRORS: {'; '.join(errors)}")
    return f"update_clip {clip_id[:8]}: {', '.join(applied) or 'nothing changed'}"


@tool
def bulk_update_clips(updates: list[dict]) -> str:
    """Apply parameter or text-style changes to multiple clips in a single call.

    Each item in `updates` is a dict describing one operation. Supported schemas:

      { "clipId": "abc", "param": "opacity",   "value": 0.8 }
        → calls POST /clips/{clipId}/params/{param}  (transform / opacity / etc.)

      { "clipId": "abc", "style": { "fontSize": 72, "bold": true } }
        → calls PATCH /clips/text/{clipId}  (text-clip style fields)

      { "clipId": "abc", "startFrame": 30, "duration": 90 }
        → calls POST /clips/{clipId}/trim  (move in/out points)

    Args:
        updates: List of operation dicts as described above.

    Returns a summary string listing each result.
    """
    lines: list[str] = []
    for op in updates:
        clip_id = op.get("clipId", "")
        if not clip_id:
            lines.append("SKIP: missing clipId")
            continue
        try:
            if "param" in op:
                _post(f"/clips/{clip_id}/params/{op['param']}", {"value": op["value"]})
                lines.append(f"OK  {clip_id[:8]} → {op['param']}={op['value']}")
            elif "style" in op:
                _patch(f"/clips/text/{clip_id}", {"style": op["style"]})
                lines.append(f"OK  {clip_id[:8]} → style {list(op['style'].keys())}")
            elif "startFrame" in op or "duration" in op:
                body: dict = {}
                if "startFrame" in op: body["startFrame"] = op["startFrame"]
                if "duration"   in op: body["duration"]   = op["duration"]
                _post(f"/clips/{clip_id}/trim", body)
                lines.append(f"OK  {clip_id[:8]} → trim {body}")
            else:
                lines.append(f"SKIP {clip_id[:8]}: no recognised op keys")
        except Exception as exc:
            lines.append(f"ERR {clip_id[:8]}: {exc}")
    return "\n".join(lines) if lines else "No updates performed."


@tool
def get_selected_clips() -> str:
    """Return a flat list of ALL clips across all tracks in the current timeline.

    NOTE: The editor's visual selection state (which clips are highlighted) is
    managed by the frontend and is not visible to the AI. Use this tool to get
    the full clip list so you can identify clips by their properties (type,
    startFrame, duration, name) and then act on them with update_clip() or
    bulk_update_clips().

    Each entry contains: clipId, trackId, trackIndex, type, name, startFrame,
    duration. Use get_timeline_state() for the full hierarchical view.
    """
    tl = _get("/timeline/state")
    clips: list[dict] = []
    for ti, track in enumerate(tl.get("tracks", [])):
        track_id = track.get("trackId") or track.get("id", "")
        for clip in track.get("clips", []):
            clips.append({
                "clipId":     clip.get("id") or clip.get("clipId", ""),
                "trackId":    track_id,
                "trackIndex": ti,
                "type":       clip.get("type", ""),
                "name":       clip.get("name", ""),
                "startFrame": clip.get("startFrame", 0),
                "duration":   clip.get("duration", 0),
            })
    return json.dumps(clips, indent=2)



@tool
def add_text_clip(
    track_index: int,
    start_frame: int,
    duration: int,
    text: str,
    font: str = "Arial",
    comp_id: str | None = None
) -> str:
    """Add a text clip to the timeline.

    Args:
        track_index: Track index (0 = first).
        start_frame: Frame where the clip starts.
        duration: Duration in frames.
        text: The text to display.
        font: Font family (e.g. Arial).
        comp_id: Optional compId to add the clip inside a specific nested composition.
                 Leave None (default) to add to the main/root timeline.
                 The UI's currently-open comp tab does NOT affect where the clip lands.
    """
    result = _post("/clips/text", {
        "trackIndex": track_index,
        "startFrame": start_frame,
        "duration": duration,
        "text": text,
        "fontFamily": font,
        "compId": comp_id,     # None = root timeline; str = target that comp directly
    })
    return json.dumps(result, indent=2)

# transitions  

@tool
def get_transitions_catalog() -> str:
    """Return all available transition types with their typeId values."""
    data = _get("/transitions/catalog")
    return json.dumps(data, indent=2)

@tool
def add_transition(clip_a_id: str, clip_b_id: str,
                   type_id: str = "dissolve", duration_frames: int = 30) -> str:
    """Add a transition between two consecutive clips.
    Args:
        clip_a_id: The clipId of the outgoing (first) clip.
        clip_b_id: The clipId of the incoming (second) clip.
        type_id: Transition type. Valid values: 'dissolve', 'fade_black',
                 'wipe_left', 'wipe_right', 'zoom_in', 'slide_left'.
        duration_frames: Overlap length in frames (default 30 = 1s @ 30fps).
    Returns a confirmation string.
    """
    _post("/transitions", {
        "typeId": type_id,
        "duration": duration_frames,
        "clipA_id": clip_a_id,
        "clipB_id": clip_b_id,
    })
    return f"Transition '{type_id}' ({duration_frames}f) added between clip {clip_a_id[:8]}… → {clip_b_id[:8]}…"


@tool
def add_transitions_between_all_clips(
    type_id: str = "dissolve",
    duration_frames: int = 30,
    track_index: int = -1,
) -> str:
    """Automatically add transitions between ALL consecutive clip pairs on the timeline.
    Scans every video track (or just one if track_index is given), finds adjacent
    clips sorted by startFrame, and adds the requested transition to each boundary.

    Use this after placing multiple clips to instantly polish the video with transitions.

    Args:
        type_id: Transition type to use for every boundary.
                 Valid: 'dissolve', 'fade_black', 'wipe_left', 'wipe_right',
                        'zoom_in', 'slide_left'.
        duration_frames: Overlap length in frames (30 = 1 second @ 30fps).
        track_index: If -1 (default) process all tracks.
                     If 0, 1, 2 … process only that track index.
    Returns a summary of how many transitions were added.
    """
    tl = _get("/timeline/state")
    tracks = tl.get("tracks", [])

    added = 0
    skipped = 0
    errors = []

    for ti, track in enumerate(tracks):
        if track_index >= 0 and ti != track_index:
            continue
        clips = sorted(track.get("clips", []), key=lambda c: c["startFrame"])
        if len(clips) < 2:
            continue
        for i in range(len(clips) - 1):
            a = clips[i]
            b = clips[i + 1]
             
            a_id = a.get("clipId") or a.get("id", "")
            b_id = b.get("clipId") or b.get("id", "")
            if not a_id or not b_id:
                errors.append(f"track{ti}/clip{i}: missing clipId in timeline state")
                continue
             
            gap = b["startFrame"] - (a["startFrame"] + a["duration"])
            if gap > 90:          
                skipped += 1
                continue
            try:
                _post("/transitions", {
                    "typeId":   type_id,
                    "duration": duration_frames,
                    "clipA_id": a_id,
                    "clipB_id": b_id,
                })
                added += 1
            except Exception as exc:
                errors.append(f"track{ti}/{a_id[:8]}: {exc}")

    result = f"✅ Added {added} '{type_id}' transitions ({duration_frames}f each)"
    if skipped:
        result += f", {skipped} gaps skipped (>3s)"
    if errors:
        result += f"\n⚠️ Errors: {'; '.join(errors)}"
    return result

# history  

@tool
def undo() -> str:
    """Undo the last editing action."""
    _post("/history/undo")
    return "Undo applied."

@tool
def redo() -> str:
    """Redo the previously undone action."""
    _post("/history/redo")
    return "Redo applied."

#   track mute/solo  

@tool
def mute_track(track_id: str, muted: bool) -> str:
    """Mute or unmute a track.
    Args:
        track_id: The trackId to mute.
        muted: True to mute, False to unmute.
    """
    _post(f"/timeline/track/{track_id}/mute", {"muted": muted})
    return f"Track {track_id} {'muted' if muted else 'unmuted'}."


@tool
def add_track(track_type: str = "video", name: str = "") -> str:
    """Add a new empty track to the active timeline.

    Use this when you need extra room to place clips — for example, adding a second
    video track for overlays, or an audio track for music / voiceover.

    Args:
        track_type: Either 'video' (default) or 'audio'.
        name: Optional display name for the track.
               If omitted, a sensible default is generated (e.g. 'Video 2').
    Returns:
        JSON with {trackId, name, type} of the newly created track.
    """
    result = _post("/timeline/add-track", {"type": track_type, "name": name})
    return json.dumps(result, indent=2)


@tool
def find_free_overlay_track(start_frame: int, end_frame: int) -> str:
    """Find (or create) the lowest track index that is guaranteed to render
    ABOVE all opaque clips in the given frame range.

    ALWAYS call this before placing any text, title, shape, or overlay clip.
    Placing overlays on track 0 will bury them under video clips. This tool
    returns the correct track index so your clip is always visible.

    HOW IT WORKS:
    • Track 0 = bottom of the composite stack (drawn first = background).
    • Higher index = drawn later = visually on top.
    • The tool scans every video/image/comp clip that overlaps [start_frame, end_frame]
      and finds the highest track index that has one. It then returns that index + 1
      (one track above). If that track does not exist yet, it creates it automatically.

    Args:
        start_frame: First frame of the clip you are about to place.
        end_frame: Last frame of the clip (start_frame + duration - 1).

    Returns:
        JSON with:
          track_index  – the safe track index to pass to add_text_clip / place_clip
          track_id – the trackId of that track
          created – true if a new track was auto-created
          reason – human-readable explanation of the decision
    """
    data = _get("/timeline/state")
    tracks = data.get("tracks", [])

     
    opaque_track_indices: list[int] = []
    for i, track in enumerate(tracks):
        track_type = track.get("type", "video")
        if track_type == "audio":
            continue
        for clip in track.get("clips", []):
            clip_end = clip["startFrame"] + clip["duration"] - 1
             
            if clip["startFrame"] <= end_frame and start_frame <= clip_end:
                clip_type = clip.get("type", "video")
                 
                if clip_type not in ("adjustment",):
                    opaque_track_indices.append(i)
                    break  

    if not opaque_track_indices:
        # No opaque clips at all  
        reason = "No opaque clips found in this range; track 0 is safe."
        track_id = tracks[0]["id"] if tracks else None
        return json.dumps({"track_index": 0, "track_id": track_id,
                           "created": False, "reason": reason}, indent=2)

    highest_opaque = max(opaque_track_indices)
    overlay_index  = highest_opaque + 1

    created = False
    if overlay_index < len(tracks):
        track_id = tracks[overlay_index]["id"]
        reason = (f"Track {highest_opaque} has opaque clips in range; "
                  f"using existing track {overlay_index} above it.")
    else:
        # Need a new track on top
        new_track = _post("/timeline/add-track", {"type": "video", "name": "Overlay"})
        track_id  = new_track.get("trackId")
        created   = True
        reason    = (f"Track {highest_opaque} has opaque clips; "
                     f"auto-created new track {overlay_index} on top.")

    return json.dumps({
        "track_index": overlay_index,
        "track_id": track_id,
        "created": created,
        "reason": reason,
    }, indent=2)


@tool
def remove_track(track_id: str) -> str:
    """Remove an entire track (and all its clips) by its trackId.

    Use when you already have the exact trackId from get_timeline_state().
    If you only know the track's position (e.g. 'track 2'), use
    remove_track_at_index() instead.

    ⚠️  Irreversible via this tool — call undo() afterwards if needed.

    Args:
        track_id: The trackId string (get it from get_timeline_state()).
    """
    _delete(f"/timeline/track/{track_id}")
    return f"Track {track_id} removed."


@tool
def remove_track_at_index(track_index: int) -> str:
    """Remove an entire track (and all its clips) by its zero-based position.

    This is the most convenient tool when you can see the track list from
    get_timeline_state() and just want to drop track number N.

    ⚠️  Irreversible via this tool — call undo() afterwards if needed.

    Args:
        track_index: Zero-based position in the tracks list
                     (track 0 = topmost/first track shown in the timeline UI).
    Returns:
        JSON with {removed: trackId, index: N} confirming what was deleted.
    """
    result = _delete(f"/timeline/track-by-index/{track_index}")
    return json.dumps(result, indent=2)

# downloader

@tool
def download_videos(query: str, num_videos: int = 2) -> str:
    """Search YouTube and download videos into the project media library.
    Each video gets its own job card in the library panel with a progress bar.

    Args:
        query: Search query string, e.g. 'cinematic sunset 4k'.
        num_videos: Number of top results to download (default 2, max 5).

    Returns JSON with imported assetIds so you can immediately use place_clip().
    """
    import time as _time
    num_videos = max(1, min(num_videos, 5))
    resp = _post("/jobs/video-download", {"query": query, "numVideos": num_videos})
    # Backend creates one job per video; 
    job_ids: list[str] = resp.get("jobIds", [resp["jobId"]])

    pending = set(job_ids)
    asset_ids: list[str] = []
    errors: list[str] = []
    for _ in range(450):   # 450 × 2s = 15 min max
        _time.sleep(2)
        still_pending: set[str] = set()
        for jid in pending:
            s = _get(f"/jobs/{jid}")
            if s["status"] == "done":
                asset_ids.extend(s.get("assetIds", []))
            elif s["status"] == "error":
                errors.append(s.get("error", "unknown"))
            else:
                still_pending.add(jid)
        pending = still_pending
        if not pending:
            break

    if not asset_ids:
        return f"All downloads failed: {'; '.join(errors)}"
    result: dict = {"assets": [{"assetId": a} for a in asset_ids]}
    if errors:
        result["errors"] = errors
    return json.dumps(result, indent=2)

@tool
def schedule_download(query: str, num_videos: int = 2, intent: str = "") -> str:
    """Schedule a background YouTube video download — returns IMMEDIATELY with jobIds.
    The agent will be automatically resumed when all downloads finish.
    Use this instead of download_videos() for non-blocking workflows.

    Args:
        query: Search query, e.g. 'cinematic sunset 4k'.
        num_videos: Number of videos to download (default 2, max 5).
        intent: What you plan to do with these videos once downloaded.
                e.g. 'make a compilation', 'use as B-roll for the intro'.

    Returns JSON with jobIds. Agent resumes automatically when done.
    """
    from backend.ai import agent_jobs as _aj
    num_videos = max(1, min(num_videos, 5))
    resp = _post("/jobs/video-download", {"query": query, "numVideos": num_videos})
    job_ids: list[str] = resp.get("jobIds", [resp.get("jobId", "")])
    job_ids = [j for j in job_ids if j]
    intent_text = intent or f"download videos for query: {query}"
    for jid in job_ids:
        _aj.schedule(jid, intent_text)
    return json.dumps({
        "status": "scheduled",
        "jobIds": job_ids,
        "query": query,
        "message": f"Downloading {num_videos} video(s) in background. I will automatically continue when ready.",
    }, indent=2)

@tool
def schedule_image_download(query: str, num_images: int = 3, intent: str = "") -> str:
    """Schedule a background image download — returns IMMEDIATELY with jobIds.
    The agent will be automatically resumed when all downloads finish.

    Args:
        query: Search query, e.g. 'cyberpunk city night'.
        num_images: Number of images to download (default 3, max 10).
        intent: What you plan to do with these images once downloaded.

    Returns JSON with jobIds. Agent resumes automatically when done.
    """
    from backend.ai import agent_jobs as _aj
    num_images = max(1, min(num_images, 10))
    resp = _post("/jobs/image-download", {"query": query, "numImages": num_images})
    job_ids: list[str] = resp.get("jobIds", [resp.get("jobId", "")])
    job_ids = [j for j in job_ids if j]
    intent_text = intent or f"download images for query: {query}"
    for jid in job_ids:
        _aj.schedule(jid, intent_text)
    return json.dumps({
        "status": "scheduled",
        "jobIds": job_ids,
        "query": query,
        "message": f"Downloading {num_images} image(s) in background. I will automatically continue when ready.",
    }, indent=2)

@tool
def download_images(query: str, num_images: int = 2) -> str:
    """Search DuckDuckGo and download images into the project media library.
    Each image gets its own job card in the library panel.

    Args:
        query: Search query string, e.g. 'cyberpunk city'.
        num_images: Number of top results to download (default 2, max 10).

    Returns JSON with imported assetIds so you can immediately use place_clip().
    """
    import time as _time
    num_images = max(1, min(num_images, 10))
    resp = _post("/jobs/image-download", {"query": query, "numImages": num_images})
    job_ids: list[str] = resp.get("jobIds", [resp["jobId"]])

    pending = set(job_ids)
    asset_ids: list[str] = []
    errors: list[str] = []
    for _ in range(150):   # up to 5 min
        _time.sleep(2)
        still_pending: set[str] = set()
        for jid in pending:
            s = _get(f"/jobs/{jid}")
            if s["status"] == "done":
                asset_ids.extend(s.get("assetIds", []))
            elif s["status"] == "error":
                errors.append(s.get("error", "unknown"))
            else:
                still_pending.add(jid)
        pending = still_pending
        if not pending:
            break

    if not asset_ids:
        return f"All image downloads failed: {'; '.join(errors)}"
    result: dict = {"assets": [{"assetId": a} for a in asset_ids]}
    if errors:
        result["errors"] = errors
    return json.dumps(result, indent=2)

@tool
def place_clip(
    asset_id: str,
    track_index: int,
    start_frame: int,
    duration: int,
    comp_id: str | None = None
) -> str:
    """Place a media asset (video/image) onto a timeline as a clip.

    Args:
        asset_id: The assetId of the media (from download_videos or get_library).
        track_index: Track index to place it on (0-based).
        start_frame: Timeline frame where the clip starts.
        duration: Duration of the clip in frames.
        comp_id: Optional compId to place inside a specific nested composition.
                     Leave None (default) to place on the main/root timeline.
                     The UI's currently-open comp tab does NOT affect placement.
    """
    result = _post("/timeline/add-clip", {
        "assetId": asset_id,
        "trackIndex": track_index,
        "startFrame": start_frame,
        "duration": duration,
        "compId": comp_id,    
    })
    return f"Placed asset {asset_id} on track {track_index} at frame {start_frame} with clipId {result.get('clipId')}."

@tool
def generate_image(prompt: str, num_images: int = 1) -> str:
    """Generate AI image(s) from a text prompt using the Gemini Imagen model.
    A job card appears immediately in the library panel with a spinner.

    Args:
        prompt:     Detailed description of the image to create.
                    Example: 'a cinematic sunset over mountains, photorealistic 4k'
        num_images: Number of images to generate (1-4, default 1).

    Returns JSON with assetIds so you can immediately place them on the timeline
    using place_clip().
    """
    import time as _time
    num_images = max(1, min(num_images, 4))
    job = _post("/jobs/image-generate", {"prompt": prompt, "numImages": num_images})
    job_id = job["jobId"]
    for _ in range(150):  # up to 5 min
        _time.sleep(2)
        status = _get(f"/jobs/{job_id}")
        if status["status"] == "done":
            asset_ids = status.get("assetIds", [])
            return json.dumps({"assets": [{"assetId": a} for a in asset_ids]}, indent=2)
        if status["status"] == "error":
            return f"Generation failed: {status.get('error', 'unknown error')}"
    return f"Generation timed out for job {job_id}."

@tool
def get_pending_jobs() -> str:
    """List all currently running or pending media/indexing jobs.

    Call this to understand what background tasks are active before deciding
    what to do next. Examples:
    - A video is still being indexed → wait before calling search_video_scenes()
    - Images are still downloading → don't place clips yet
    - Transcription is running → captions will be available soon

    Job types and what they mean:
    - video_download : Agent downloading YouTube video(s)
    - image_download : Agent downloading images
    - image_generate : Agent generating AI images with Gemini
    - video_index : Semantic indexing running (Vision LLM + Whisper) on a video
    - image_index : Semantic indexing running (Ollama) on an image
    - transcription    : Whisper transcription running for captions

    Returns a readable summary, or "No pending jobs" if everything is done.
    """
    result = _get("/jobs/?active_only=true")
    jobs = result.get("jobs", [])
    if not jobs:
        return "No pending jobs — all media tasks are complete."
    lines = [f"{len(jobs)} active job(s):"]
    for j in jobs:
        pct = int(j.get("progress", 0) * 100)
        asset = f"  assetId={j['assetId'][:8]}" if j.get("assetId") else ""
        lines.append(
            f"  [{j['status'].upper():8}] {j['type']:18} {pct:3}%  {j['label']}{asset}"
        )
    return "\n".join(lines)

@tool
def get_selected_clip() -> str:
    """Get info about the clip currently selected by the user in the timeline.

    Returns the clipId, track, frame range, clip type, and effect count.
    If nothing is selected, returns null. Always call this before applying effects
    so you know which clip to target.
    """
    result = _get("/clips/selected")
    return json.dumps(result, indent=2)

@tool
def list_effects_catalog() -> str:
    """List all available effect types that can be applied to clips.

    Returns name, type key, category (Color / Stylize / Cinematic / Keying),
    description, and available parameters for each effect.
    Use the 'type' field as the effectType when calling apply_effect_to_clip().
    """
    result = _get("/effects/catalog")
    return json.dumps(result, indent=2)

@tool
def apply_effect_to_clip(clip_id: str, effect_type: str, params: dict | None = None) -> str:
    """Apply an effect to a specific clip.

    Args:
        clip_id:     The clipId to add the effect to. Get it from get_selected_clip()
                     or get_timeline_state().
        effect_type: Effect type key from list_effects_catalog() e.g. 'blur',
                     'brightness_contrast', 'hsl', 'color_grade', 'sharpen',
                     'vignette', 'chroma_key'.
        params:      Optional dict of parameter values to set immediately after adding
                     e.g. {"blur_x": 10, "blur_y": 10} for blur effect.

    Returns the effectId of the newly added effect.
    """
    result = _post(f"/clips/{clip_id}/effects", {"effectType": effect_type})
    effect_id = result.get("effectId")
    # Apply params immediately if provided
    if params and effect_id:
        _post(f"/clips/{clip_id}/effects/{effect_id}", {"params": params})
        result["params_applied"] = params
    return json.dumps(result, indent=2)

@tool
def patch_clip_effect(clip_id: str, effect_id: str, params: dict) -> str:
    """Update the parameters of an existing effect on a clip.

    Args:
        clip_id:   The clipId that has the effect.
        effect_id: The effectId to update. Get it from get_selected_clip() then
                   GET /clips/{clipId}/effects, or from apply_effect_to_clip().
        params:    Dict of parameter key-value pairs to update.
                   e.g. {"blur_x": 5} for blur, {"brightness": 0.3} for brightness.

    Use list_effects_catalog() to see available params per effect type.
    """
    import httpx as _httpx
    r = _httpx.patch(f"{_base()}/clips/{clip_id}/effects/{effect_id}",
                     json={"params": params}, timeout=10)
    r.raise_for_status()
    return json.dumps(r.json(), indent=2)

@tool
def search_news(query: str, max_results: int = 10) -> str:
    """Search DuckDuckGo News for current headlines matching a query.

    Args:
        query: Search term, e.g. "top tech news today", "AI breakthroughs 2026"
        max_results: Number of articles to return (default 10, max 20)

    Returns a JSON list of {title, body, source, url} objects.
    Use this first when the user asks for news-related content before building a video.
    """
    from backend.ai.video_pipeline.news_search import search_news as _search
    items = _search(query, max_results=min(max_results, 20))
    return json.dumps([
        {"title": it.title, "body": it.body[:300], "source": it.source, "url": it.url}
        for it in items
    ], indent=2)

@tool
def create_news_video(query: str, scene_duration_seconds: float = 5.0) -> str:
    """Automatically create a full news video from a search query.

    This runs the COMPLETE pipeline in one call:
      1. Searches DuckDuckGo News for current headlines
      2. Uses AI to generate a frame-accurate scene plan (b-roll, titles, effects)
      3. Downloads YouTube videos and generates AI images in parallel
      4. Assembles everything on the Fade timeline (track 0=broll, 1=titles, 2=lower-thirds)

    Args:
        query:                  Topic to search, e.g. "today top 10 tech news",
                                "latest space exploration news", "AI news this week"
        scene_duration_seconds: How many seconds each news scene lasts (default 5s).
                                Use 3 for quick cuts, 7 for more breathing room.

    Returns a summary of what was created with clip counts and timeline info.

    WHEN TO USE: Any time the user says "create a video about [topic]",
    "make a news video", "build a video about [subject]" — use this tool.
    """
    import asyncio
    from backend.ai.video_pipeline.news_search import search_news as _search
    from backend.ai.video_pipeline.scene_planner import plan_scenes
    from backend.ai.video_pipeline.asset_gatherer import gather_assets
    from backend.ai.video_pipeline.timeline_builder import build_timeline
    from backend.ai.agent import get_agent_llm

    fps = 30.0
    scene_duration = int(scene_duration_seconds * fps)

    # 1. Search news
    print(f"[create_news_video] Searching: {query!r}", flush=True)
    items = _search(query, max_results=10)
    if not items:
        return "❌ No news articles found for that query. Try a different topic."

    # 2. Plan scenes via LLM structured output
    print(f"[create_news_video] Planning {len(items)} scenes…", flush=True)
    llm = get_agent_llm(_PORT)
    plan = plan_scenes(query, items, llm, scene_duration=scene_duration, fps=fps)

    # 3. Gather assets in parallel (yt-dlp + Gemini image gen)
    print(f"[create_news_video] Gathering assets…", flush=True)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                asset_map = pool.submit(asyncio.run, gather_assets(plan, _PORT)).result()
        else:
            asset_map = loop.run_until_complete(gather_assets(plan, _PORT))
    except RuntimeError:
        asset_map = asyncio.run(gather_assets(plan, _PORT))

    # 4. Build timeline
    print(f"[create_news_video] Building timeline…", flush=True)
    result = build_timeline(plan, asset_map, _PORT)

    placed = result.get("placed_clips", 0)
    failed = result.get("failed_scenes", [])
    total_s  = plan.totalFrames / fps
    videos = sum(1 for s in plan.scenes if s.broll.type == "video")
    images = sum(1 for s in plan.scenes if s.broll.type == "image")

    summary = (
        f"✅ News video created!\n"
        f"• Topic: {query}\n"
        f"• {plan.totalScenes} scenes × {scene_duration_seconds:.0f}s = {total_s:.0f}s total\n"
        f"• {videos} YouTube b-roll clips + {images} AI-generated images\n"
        f"• {placed} scenes placed on timeline\n"
        f"• Track 0 = b-roll  |  Track 1 = headlines  |  Track 2 = lower-thirds\n"
    )
    if failed:
        summary += f"• ⚠️ {len(failed)} scenes had issues (no media found): {failed}\n"
    return summary


# Composition tools

@tool
def create_composition(
    name: str,
    width: int = 1920,
    height: int = 1080,
    fps: float = 30.0,
    total_frames: int = 900,
) -> str:
    """Create a new nested composition (sub-timeline) with custom resolution and frame rate.

    Args:
        name: Name for the composition, e.g. 'Intro Scene'.
        width: Frame width in pixels (default 1920).
        height: Frame height in pixels (default 1080).
        fps: Frames per second (default 30.0).
        total_frames: Total duration in frames (default 900 = 30s at 30fps).

    Returns the compId of the new composition.
    Call add_comp_to_timeline() to place it on the main timeline.
    """
    result = _post("/comps", {
        "name": name,
        "width": width,
        "height": height,
        "fps": fps,
        "totalFrames": total_frames,
    })
    return json.dumps(result, indent=2)


@tool
def list_compositions() -> str:
    """List all compositions in the project, including the root timeline.

    Returns compId, name, isRoot, width, height, fps, totalFrames, trackCount, clipCount.
    Use this to find a compId before adding a composition clip to the timeline.
    """
    result = _get("/comps")
    return json.dumps(result, indent=2)


@tool
def add_comp_to_timeline(comp_id: str, start_frame: int, duration: int = 90) -> str:
    """Place a composition onto the main timeline as a nested clip.

    Args:
        comp_id: The compId of the composition (get from list_compositions()).
        start_frame: Timeline frame where the comp clip starts.
        duration: Duration in frames (default 90 = 3s at 30fps).

    Raises an error if adding would create a cycle (comp inside itself).
    """
    result = _post("/clips/comp", {
        "compId": comp_id,
        "startFrame": start_frame,
        "duration": duration,
    })
    return json.dumps(result, indent=2)


@tool
def activate_comp(comp_id: str) -> str:
    """Switch the active composition (changes what the user sees in the editor).

    Args:
        comp_id: The compId to make active, OR 'root' to go back to the main timeline.

    Use this if the user explicitly asks to "open", "go to", or "activate" a specific timeline.
    """
    result = _post(f"/comps/{comp_id}/activate")
    return json.dumps(result, indent=2)


@tool
def get_comp_state(comp_id: str) -> str:
    """Get the full track/clip state of a composition (sub-timeline).

    Args:
        comp_id: The compId to inspect (get from list_compositions()).

    Returns tracks, clips, totalFrames, fps for the given composition.
    Use this to inspect what's inside a comp before editing it.
    """
    result = _get(f"/comps/{comp_id}/state")
    return json.dumps(result, indent=2)


@tool
def add_clip_to_comp(
    comp_id: str,
    asset_id: str,
    track_index: int,
    start_frame: int,
    duration: int,
) -> str:
    """Add a media clip (video or image) from the library into a specific nested composition.

    The comp does NOT need to be open in the UI — it is targeted directly by compId.
    Use get_comp_state(comp_id) first to inspect existing tracks/clips.

    Args:
        comp_id:     The compId of the target composition (from list_compositions()).
        asset_id:    The assetId of the media to add (from get_library()).
        track_index: Which track inside the comp to add to (0 = first).
        start_frame: Frame inside the comp where the clip starts.
        duration:    Duration in frames.
    """
    result = _post("/timeline/add-clip", {
        "assetId": asset_id,
        "trackIndex": track_index,
        "startFrame": start_frame,
        "duration": duration,
        "compId": comp_id,   # target comp directly; no activate/deactivate needed
    })
    return json.dumps(result, indent=2)


@tool
def add_solid_clip(
    track_index: int,
    start_frame: int,
    duration: int,
    r: float = 0.0,
    g: float = 0.0,
    b: float = 0.0,
    a: float = 1.0,
    comp_id: str | None = None
) -> str:
    """Add a solid color clip to a timeline.

    Args:
        track_index: Track to add the solid clip to (0 = first track).
        start_frame: Timeline frame where the clip starts.
        duration: Duration in frames.
        r: Red channel 0.0–1.0 (default 0.0 = black).
        g: Green channel 0.0–1.0.
        b: Blue channel 0.0–1.0.
        a: Alpha 0.0–1.0 (default 1.0 = opaque).
        comp_id: Optional compId to add inside a specific nested composition.
                 Leave None (default) to add to the main/root timeline.
    """
    result = _post("/clips/shape", {
        "trackIndex": track_index,
        "startFrame": start_frame,
        "duration": duration,
        "shapeType": "rectangle",
        "fillR": r, "fillG": g, "fillB": b, "fillA": a,
        "strokeA": 0.0,
        "width": 1920, "height": 1080,
        "compId": comp_id,     # None = root timeline; str = target that comp directly
    })
    return json.dumps(result, indent=2)


@tool
def add_shape_clip(
    track_index: int,
    start_frame: int,
    duration: int,
    shape_type: str = "rectangle",
    fill_r: float = 1.0,
    fill_g: float = 0.0,
    fill_b: float = 0.0,
    fill_a: float = 1.0,
    width: float = 400.0,
    height: float = 300.0,
    comp_id: str | None = None
) -> str:
    """Add a shape clip (rectangle, ellipse, triangle) to a timeline.

    Args:
        track_index: Track index (0 = first).
        start_frame: Frame where the clip starts.
        duration: Duration in frames.
        shape_type: 'rectangle', 'ellipse', or 'triangle'.
        fill_r/g/b/a: Fill color channels 0.0–1.0.
        width/height: Shape dimensions in pixels.
        comp_id: Optional compId to add inside a specific nested composition.
                 Leave None (default) to add to the main/root timeline.
                 The UI's currently-open comp tab does NOT affect where the clip lands.
    """
    result = _post("/clips/shape", {
        "trackIndex": track_index,
        "startFrame": start_frame,
        "duration": duration,
        "shapeType": shape_type,
        "fillR": fill_r, "fillG": fill_g, "fillB": fill_b, "fillA": fill_a,
        "strokeA": 0.0,
        "width": width, "height": height,
        "compId": comp_id,     # None = root timeline; str = target that comp directly
    })
    return json.dumps(result, indent=2)


@tool
def delete_composition(comp_id: str) -> str:
    """Delete a composition (sub-timeline) and all its contents.

    Args:
        comp_id: The compId of the composition to delete.

    WARNING: This also removes any comp clips referencing this comp from all timelines.
    """
    result = _delete(f"/comps/{comp_id}")
    return json.dumps(result, indent=2)


# all tools list

ALL_TOOLS = [
    get_timeline_state,
    get_library,
    get_playback_state,
    seek_to,
    split_clip,
    trim_clip,
    move_clip,
    delete_clip,
    get_effects_catalog,
    add_effect,
    remove_effect,
    set_effect_param,
    set_clip_param,
    add_text_clip,
    get_transitions_catalog,
    add_transition,
    add_transitions_between_all_clips,
    undo,
    redo,
    mute_track,
    add_track,
    find_free_overlay_track,
    remove_track,
    remove_track_at_index,
    download_videos,
    download_images,
    schedule_download,
    schedule_image_download,
    generate_image,
    get_pending_jobs,
    search_news,
    create_news_video,
    get_selected_clip,
    get_selected_clips,
    list_effects_catalog,
    apply_effect_to_clip,
    patch_clip_effect,
    place_clip,
    update_clip,
    bulk_update_clips,
    # Composition tools
    create_composition,
    list_compositions,
    add_comp_to_timeline,
    activate_comp,
    get_comp_state,
    add_clip_to_comp,
    add_solid_clip,
    add_shape_clip,
    delete_composition,
]


# WebComp tools  
 
@tool
def create_webcomp(
    name: str,
    css: str = "",
    js: str = "",
    html_body: str = "",
    template: str = "blank",
    duration_seconds: float = 5.0,
) -> str:
    """Create a WebComp — an animated CSS/JS scene rendered as video pixels on the timeline.

    HOW FILES ARE SAVED (you never need to worry about paths):
      - Project saved → <project-folder>/webcomps/<name>/   (travels with the project)
      - No project    → C:/Users/<user>/.fade/webcomps/<name>/  (global fallback)
    The backend handles this automatically.

    WHAT THE BACKEND GENERATES FOR YOU:
      index.html  ← auto-generated with the correct runtime <script> tag.
                    YOU MUST NOT WRITE THIS FILE. Provide html_body instead if
                    you need custom DOM elements inside the scene div.
      style.css   ← written from your `css` argument
      script.js   ← written from your `js` argument

    GLOBALS INJECTED EACH FRAME by Electron:
      window.FADE_FRAME   — current frame number (int, 0-indexed)
      window.FADE_TIME    — current time in seconds (float)
      window.FADE_FPS     — project FPS
      window.FADE_WIDTH   — canvas width  (1920)
      window.FADE_HEIGHT  — canvas height (1080)
      window.FADE_PARAMS  — runtime params from the inspector panel (object)

    LISTEN FOR FRAME EVENTS in script.js:
      window.addEventListener('fade:frame', (e) => {
        const { frame, time } = e.detail;
        // your animation code here
      });

    FADE REACT (Remotion-style) — available with NO import needed:
      const { useCurrentFrame, interpolate, spring, mount, FadeComposition } = window.FadeReact;

    Args:
        name: Human-readable name for the WebComp
        css: style.css content (pure CSS, no <style> tags)
        js: script.js content (pure JS, no <script> tags)
        html_body: Optional inner HTML for <div id="scene"> — only plain DOM
                        elements like <div>, <canvas>, <h1>, <video>.
                        Do NOT include <head>, <script src>, <link href>, or CDN refs.
        template:       Starter template — "blank" | "lower-third" | "neon-headline" | "kinetic-title"
        duration_seconds: Default clip duration when placed on timeline
    """
    body: dict = {"name": name, "template": template, "js": js, "css": css, "html_body": html_body}
    result = _post("/timeline/webcomp/create", body)
    asset_id = result.get("assetId", "")
    folder = result.get("folderPath", "")

    return json.dumps({
        "status": "ok",
        "assetId": asset_id,
        "folderPath": folder,
        "name": name,
        "message": f"WebComp '{name}' created (assetId={asset_id}). Use add_webcomp_to_timeline() to place it.",
    })


@tool
def list_webcomps() -> str:
    """List all WebComp assets currently in the library.

    Returns assetId, name, folderPath, width, height, fps, and durationFrames
    for each WebComp. Use assetId with other webcomp tools.
    """
    return json.dumps(_get("/timeline/webcomp/list"))


@tool
def list_webcomp_templates() -> str:
    """List all built-in WebComp templates that can be used when creating a new WebComp.

    Returns template names, descriptions, and param schemas.
    Pass the template name to create_webcomp(template=...).
    """
    return json.dumps(_get("/timeline/webcomp/templates"))


@tool
def add_webcomp_to_timeline(
    webcomp_id: str,
    track_index: int = 0,
    start_frame: int = 0,
    duration: int = 150,
) -> str:
    """Place an existing WebComp asset onto the timeline as a video clip.

    Args:
        webcomp_id: The assetId returned by create_webcomp or list_webcomps
        track_index: Which video track to place it on (0 = top/first track)
        start_frame: Start position on the timeline (frames)
        duration: Clip length in frames (150 = 5 s @ 30 fps)
    """
    result = _post("/timeline/add-clip", {
        "trackIndex": track_index,
        "startFrame": start_frame,
        "duration": duration,
        "assetId": webcomp_id,
        "clipType": "webcomp",
        "webcompId": webcomp_id,
    })
    return json.dumps(result)


@tool
def get_webcomp_clip_info(clip_id: str) -> str:
    """Get full info about a WebComp clip that is on the timeline.

    Returns the clip's transform, opacity, webcompId, asset metadata (name/size/fps),
    and the complete param schema so you know which params can be set.

    Args:
        clip_id: The clipId of the WebComp clip on the timeline
    """
    return json.dumps(_get(f"/timeline/webcomp/clip-info?clipId={clip_id}"))


@tool
def read_webcomp_file(webcomp_id: str, filename: str) -> str:
    """Read the content of a file inside a WebComp folder.

    Always call this before edit_webcomp_file() to understand the existing code.

    Args:
        webcomp_id: The assetId of the WebComp
        filename: File to read — e.g. "index.html", "style.css", "script.js", "webcomp.json"
    """
    result = _post("/timeline/webcomp/read-file", {"webcompId": webcomp_id, "filename": filename})
    return json.dumps(result)


@tool
def edit_webcomp_file(webcomp_id: str, filename: str, content: str) -> str:
    """Write or overwrite a file inside a WebComp folder.

    ALLOWED files: script.js, style.css, webcomp.json
    NEVER write index.html — the backend owns it and auto-generates it correctly.
    If you write index.html anyway the backend will silently sanitise it, but
    your custom DOM structure will be overwritten on the next create.

    After editing script.js or style.css, call reload_webcomp() to see changes immediately.

    Args:
        webcomp_id: The assetId of the WebComp
        filename: File to write — "script.js" | "style.css" | "webcomp.json"
        content: Full file content to write (pure JS / CSS / JSON — no <script> or <style> tags)
    """
    result = _post("/timeline/webcomp/write-file", {"webcompId": webcomp_id, "filename": filename, "content": content})
    return json.dumps(result)


@tool
def set_webcomp_params(clip_id: str, params: dict) -> str:
    """Set runtime params on a WebComp clip (drives window.FADE_PARAMS in the page).

    Params appear in the inspector panel and are injected into the WebComp page
    as window.FADE_PARAMS. Match keys to the param schema in webcomp.json.

    Example: set_webcomp_params("clip-123", {"text": "Hello", "color": "#ff0000"})

    Args:
        clip_id: The clipId of the WebComp clip on the timeline
        params: Key-value dict matching the WebComp's param schema
    """
    result = _post("/timeline/webcomp/runtime-params", {"clipId": clip_id, "params": params})
    return json.dumps(result)


@tool
def set_webcomp_transform(
    clip_id: str,
    x: float = 0.0,
    y: float = 0.0,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
    rotation: float = 0.0,
    anchor_x: float = 0.0,
    anchor_y: float = 0.0,
) -> str:
    """Set the position, scale, and rotation of a WebComp clip on the canvas.

    Args:
        clip_id: The clipId of the WebComp clip
        x: Horizontal offset in pixels from canvas centre (negative = left)
        y: Vertical offset in pixels from canvas centre (negative = up)
        scale_x: Horizontal scale factor (1.0 = original size)
        scale_y: Vertical scale factor (1.0 = original size)
        rotation: Rotation in degrees
        anchor_x: Anchor point X offset in pixels
        anchor_y: Anchor point Y offset in pixels
    """
    result = _post("/timeline/webcomp/transform", {
        "clipId": clip_id,
        "x": x, "y": y,
        "scaleX": scale_x, "scaleY": scale_y,
        "rotation": rotation,
        "anchorX": anchor_x, "anchorY": anchor_y,
    })
    return json.dumps(result)


@tool
def set_webcomp_opacity(clip_id: str, opacity: float) -> str:
    """Set the opacity of a WebComp clip.

    Args:
        clip_id: The clipId of the WebComp clip
        opacity: 0.0 (fully transparent) to 1.0 (fully opaque)
    """
    result = _post("/timeline/webcomp/opacity", {"clipId": clip_id, "opacity": max(0.0, min(1.0, opacity))})
    return json.dumps(result)


@tool
def delete_webcomp(webcomp_id: str) -> str:
    """Delete a WebComp asset from the library permanently.

    IMPORTANT: Remove all timeline clips that reference this WebComp first using
    delete_clip(), otherwise the clips will reference a missing asset.

    Args:
        webcomp_id: The assetId of the WebComp to delete
    """
    result = _delete(f"/timeline/webcomp/{webcomp_id}")
    return json.dumps(result)


@tool
def reload_webcomp(webcomp_id: str) -> str:
    """Force-reload a WebComp's browser window and clear its frame cache.

    Call this after edit_webcomp_file() to see the updated code in the preview.

    Args:
        webcomp_id: The assetId of the WebComp to reload
    """
    result = _post("/timeline/webcomp/reload", {"webcompId": webcomp_id})
    return json.dumps(result)


@tool
def update_webcomp_meta(
    webcomp_id: str,
    name: str = "",
    width: int = 0,
    height: int = 0,
    fps: float = 0.0,
    duration_frames: int = 0,
) -> str:
    """Update the metadata of a WebComp asset (name, canvas size, fps, duration).

    Only non-zero/non-empty values are applied. Updates both the in-memory asset
    and webcomp.json on disk so changes persist across project saves.

    Args:
        webcomp_id: The assetId of the WebComp
        name: New display name (leave empty to keep current)
        width: Canvas width in pixels (0 = keep current)
        height: Canvas height in pixels (0 = keep current)
        fps: Frame rate (0.0 = keep current)
        duration_frames: Total duration in frames (0 = keep current)
    """
    body: dict = {"webcompId": webcomp_id}
    if name: body["name"] = name
    if width: body["width"] = width
    if height: body["height"] = height
    if fps: body["fps"] = fps
    if duration_frames: body["durationFrames"] = duration_frames
    result = _post("/timeline/webcomp/update-meta", body)
    return json.dumps(result)


 

WEBCOMP_TOOLS = [
    create_webcomp,
    list_webcomps,
    list_webcomp_templates,
    add_webcomp_to_timeline,
    get_webcomp_clip_info,
    read_webcomp_file,
    edit_webcomp_file,
    set_webcomp_params,
    set_webcomp_transform,
    set_webcomp_opacity,
    delete_webcomp,
    reload_webcomp,
    update_webcomp_meta,
]

# Extend ALL_TOOLS 
ALL_TOOLS.extend(WEBCOMP_TOOLS)


# VideoSemantic and Context tools

@tool
def get_timeline_context(format: str = "txt") -> str:
    """Get a rich semantic breakdown of every video clip currently on the timeline.

    Returns per-second scene descriptions (from Vision LLM) and Whisper speech transcript
    for each clip, merged with timeline position info. Use this to understand WHAT IS
    HAPPENING visually and audibly across the entire edit.

    Args:
        format: "txt" for human-readable (default, best for reasoning), "json" for structured data.
    """
    r = _get(f"/context/timeline?format={format}")
    if isinstance(r, str):
        return r
    return json.dumps(r, indent=2)


@tool
def get_clip_context(clip_id: str, format: str = "txt") -> str:
    """Get frame-by-frame semantic context for a specific clip on the timeline.

    Returns scene descriptions and speech transcript from the clip's inPoint to outPoint,
    at ~2 second intervals. Use this to understand exactly what happens inside a single clip.

    Args:
        clip_id: The clipId of the clip (get from get_timeline_state).
        format: "txt" for human-readable (default), "json" for structured data.
    """
    r = _get(f"/context/clip/{clip_id}?format={format}")
    if isinstance(r, str):
        return r
    return json.dumps(r, indent=2)


@tool
def get_asset_context(asset_id: str, format: str = "txt") -> str:
    """Get full semantic context for a library asset — even if it's not on the timeline yet.

    Returns all indexed scene descriptions and transcript for the entire video file.
    Use this to preview what a video contains before placing it on the timeline.

    Args:
        asset_id: The assetId from the library (get from get_library).
        format: "txt" for human-readable (default), "json" for structured data.
    """
    r = _get(f"/context/asset/{asset_id}?format={format}")
    if isinstance(r, str):
        return r
    return json.dumps(r, indent=2)


@tool
def search_video_scenes(query: str, top_k: int = 5) -> str:
    """Search all indexed library videos for scenes matching a natural language description.

    Uses semantic vector search (ChromaDB + sentence embeddings) to find the most relevant
    video segments. Returns ranked results with assetId, timestamp range, and relevance score.

    Examples:
        - "car crash on highway"
        - "person waving at camera"
        - "sunset over mountains"
        - "crowd cheering"

    Args:
        query: Natural language scene description to search for.
        top_k: Number of top results to return (default 5, max 20).
    """
    data = _get(f"/search/video?q={query}&top_k={top_k}")
    results = data.get("results", [])
    if not results:
        return f"No matching scenes found for: '{query}'"
    lines = [f"Scene search results for: '{query}'", ""]
    for i, hit in enumerate(results, 1):
        score = round(hit.get("score", 0) * 100)
        lines.append(f"{i}. [{score}% match] assetId={hit['assetId']}")
        lines.append(f" Time: {hit['start_sec']:.1f}s – {hit['end_sec']:.1f}s")
        lines.append(f"   {hit.get('text','')[:200]}")
        lines.append("")
    return "\n".join(lines)


@tool
def get_index_status(asset_id: str) -> str:
    """Check the VideoSemantic indexing status for a specific video asset.

    Returns one of: not_started, pending, running, done, error.
    The index must be 'done' before get_asset_context or search_video_scenes will work.

    Args:
        asset_id: The assetId to check.
    """
    data = _get(f"/library/index-status/{asset_id}")
    status = data.get("status", "unknown")
    chunks = data.get("chunks", 0)
    msg    = data.get("message", "")
    if status == "done":
        return f"Asset {asset_id[:8]}: indexed ✓ ({chunks} chunks ready for search)"
    elif status in ("pending", "running"):
        return f"Asset {asset_id[:8]}: indexing in progress... ({status})"
    elif status == "error":
        return f"Asset {asset_id[:8]}: indexing failed — {msg}"
    else:
        return f"Asset {asset_id[:8]}: not yet indexed. Drop the video into the library to start."


VIDEOSEMANTIC_TOOLS = [
    get_timeline_context,
    get_clip_context,
    get_asset_context,
    search_video_scenes,
    get_index_status,
]

ALL_TOOLS.extend(VIDEOSEMANTIC_TOOLS)


#   Rich per-clip description tools  

@tool
def describe_clip(clip_id: str) -> str:
    """Get a rich, type-specific description of any clip on the timeline.

    Unlike get_clip_context (which only handles video/image), this tool works
    for ALL clip types and returns the most relevant content for each:

    - **video**: indexed scene descriptions + Whisper transcript timeline,
      inPoint/outPoint, transcriptIndexed flag
    - **audio**: Whisper transcript segments, volume, mute state
    - **image**: AI vision description of the image
    - **text**: text string + full style properties (font, color, shadow, etc.)
    - **shape**: shape type + style (fill, stroke, dimensions)
    - **webcomp**: component name, runtimeParams, and the actual HTML/CSS/JS source
    - **comp**: nested composition track/clip summary
    - **svg**: SVG file path + SVG source (up to 4 KB)
    - **pen/path**: number of bezier control points

    Use this when you need to understand what a specific clip contains — especially
    before editing, styling, or rewriting it.

    Args:
        clip_id: The clipId of the clip (get from get_timeline_state).
    """
    try:
        return json.dumps(_get(f"/context/clip/{clip_id}/describe"), indent=2)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Clip '{clip_id}' not found on any timeline. Call get_timeline_state() to get valid clip IDs."
        return f"describe_clip error: {e}"


@tool
def describe_selected_clip() -> str:
    """Get a rich, type-specific description of the clip currently selected in the UI.

    Equivalent to calling describe_clip() on whichever clip the user has selected.
    Returns a 'nothing selected' message if the user hasn't clicked a clip yet.

    Returns the same rich payload as describe_clip — type-dispatched content that
    includes visual/audio context, text content, style properties, or source code
    depending on the clip type.
    """
    try:
        r = _get("/context/selected/describe")
        return json.dumps(r, indent=2)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return (
                "No clip is currently selected in the UI. "
                "Ask the user to click a clip, or use describe_clip(clip_id) directly."
            )
        return f"describe_selected_clip error: {e}"


CLIP_DESCRIBE_TOOLS = [describe_clip, describe_selected_clip]
ALL_TOOLS.extend(CLIP_DESCRIBE_TOOLS)


#   Scene-Aware Clip Management Tools  

@tool
def add_video_clip_by_scene(
    description: str,
    frame_on_timeline: int,
    track: int = -1,
    top_k: int = 1,
    duration_frames: int = 0,
) -> str:
    """
    Search indexed video scenes by natural language description and add the best-matching
    clip to the timeline at the specified frame position.
    Uses in/out points from ChromaDB so the clip plays the exact matching segment.

    Args:
        description: Natural language description of the scene (e.g. "woman in red dress dancing")
        frame_on_timeline: Frame position on the timeline where the clip should start
        track: Track index (-1 = auto-find a free track)
        top_k: Which result to use (1 = best match, 2 = second best, etc.)
        duration_frames: Override clip duration in frames (0 = use source segment length)
    """
    body: dict = {
        "description": description,
        "frameOnTimeline": frame_on_timeline,
        "track": track,
        "topK": top_k,
    }
    if duration_frames > 0:
        body["durationOverride"] = duration_frames
    result = _post("/scene/add-video-clip", body)
    return (
        f"Added VideoClip {result['clipId'][:8]} from '{result['filename']}' "
        f"[{result['inPointSec']:.1f}s\u2013{result['outPointSec']:.1f}s] "
        f"at frame {result['startFrame']} (score={result['score']:.0%})\n"
        f"Scene: {result.get('sceneText','')[:120]}"
    )


@tool
def add_image_clip_by_scene(
    description: str,
    frame_on_timeline: int,
    track: int = -1,
    top_k: int = 1,
    duration_frames: int = 150,
) -> str:
    """
    Search indexed images by natural language description and add the best-matching
    image asset as a clip on the timeline.

    Args:
        description: Natural language description of the image (e.g. "sunset over mountains")
        frame_on_timeline: Frame position on the timeline where the clip should start
        track: Track index (-1 = auto-find a free track)
        top_k: Which result to use (1 = best match, 2 = second best, etc.)
        duration_frames: Duration of the image clip in frames (default 150 = 5s @ 30fps)
    """
    result = _post("/scene/add-image-clip", {
        "description": description,
        "frameOnTimeline": frame_on_timeline,
        "track": track,
        "topK": top_k,
        "durationOverride": duration_frames,
    })
    return (
        f"Added ImageClip {result['clipId'][:8]} from '{result['filename']}' "
        f"at frame {result['startFrame']} (score={result['score']:.0%})\n"
        f"Description: {result.get('sceneText','')[:120]}"
    )


@tool
def get_clip_info(clip_id: str) -> str:
    """
    Get detailed information about a specific clip: asset filename, in/out points,
    track index, duration, and any indexed scene text.

    Args:
        clip_id: The clipId of the clip to inspect
    """
    result = _get(f"/scene/clip-info/{clip_id}")
    return json.dumps(result, indent=2)


@tool
def remove_clip(clip_id: str) -> str:
    """
    Remove a clip from the active timeline by its clipId.

    Args:
        clip_id: The clipId of the clip to remove
    """
    result = _delete(f"/scene/remove-clip/{clip_id}")
    return f"Removed clip {clip_id[:8]} from track {result.get('trackIndex', '?')}"


@tool
def list_timeline_clips() -> str:
    """
    List all clips on the active timeline with asset filenames, time positions,
    in/out points, and track indices.
    """
    result = _get("/scene/list-clips")
    return json.dumps(result, indent=2)


SCENE_CLIP_TOOLS = [
    add_video_clip_by_scene,
    add_image_clip_by_scene,
    get_clip_info,
    remove_clip,
    list_timeline_clips,
]

ALL_TOOLS.extend(SCENE_CLIP_TOOLS)


# Audio / Whisper tools

@tool
def generate_captions(
    clip_id: str,
    min_words: int = 2,
    language: str = "",
) -> str:
    """
    Automatically transcribe the audio in a video clip (using Whisper) and place
    caption TextClips on the timeline, time-synced to each speech segment.

    Captions appear on a new track directly above the source clip named
    'Captions - <filename>'. Default style: white bold text, black outline,
    centered, positioned in the lower third.

    Args:
        clip_id:   The clipId of the video clip to caption.
        min_words: Merge segments shorter than this word count into the previous
                   segment (avoids too-short flashing captions). Default: 2.
        language:  Force a language code (e.g. 'en', 'hi', 'fr').
                   Leave empty for auto-detection (default).
    """
    body = {"clipId": clip_id, "minWords": min_words}
    if language:
        body["language"] = language
    result = _post("/audio/generate-captions", body)
    msg = result.get("message", "")
    if msg:
        return msg
    count = result["captionCount"]
    track = result["trackName"]
    segs  = result.get("segments", [])
    preview = "\n".join(
        f"  [{s['startSec']:.1f}s] \"{s['text'][:60]}\""
        for s in segs[:5]
    )
    suffix = f"\n  ...and {count - 5} more" if count > 5 else ""
    return (
        f"Generated {count} caption clip(s) on track '{track}':\n"
        + preview + suffix
    )


@tool
def remove_silence(
    clip_id: str,
    min_silence_ms: int = 500,
    padding_ms: int = 80,
) -> str:
    """
    Remove silent parts from a video clip by splitting it into speech-only
    segments placed back-to-back on the timeline. The original clip is
    replaced -- gaps are closed so the content is more compact.

    Uses Whisper VAD (Voice Activity Detection) to detect speech regions.

    Args:
        clip_id:        The clipId of the VideoClip to process.
        min_silence_ms: Minimum gap duration (ms) to treat as silence and remove.
                        Smaller values = more aggressive trimming. Default: 500.
        padding_ms:     How many ms of audio to keep before/after each speech
                        window (prevents abrupt cut-ins). Default: 80.
    """
    result = _post("/audio/remove-silence", {
        "clipId":       clip_id,
        "minSilenceMs": min_silence_ms,
        "paddingMs":    padding_ms,
    })
    msg = result.get("message", "")
    if msg:
        return msg
    return (
        f"Removed {result['removedSilenceSec']:.2f}s of silence from clip.\n"
        f"Original: {result['originalDuration']:.2f}s -> "
        f"New: {result['newDuration']:.2f}s "
        f"({result['clipCount']} speech segment(s))"
    )


@tool
def get_transcript(clip_id: str, word_level: bool = False) -> str:
    """
    Return the raw Whisper transcript for a video clip without modifying
    the timeline. Useful for reviewing speech content before captioning.

    Args:
        clip_id:    The clipId of the video clip to transcribe.
        word_level: If True, include per-word timestamps in each segment.
    """
    result = _get_long(f"/audio/transcribe/{clip_id}?words={'true' if word_level else 'false'}")
    segs = result.get("segments", [])
    if not segs:
        return "No speech detected in clip."
    lines = [f"Transcript - {os.path.basename(result.get('filepath', clip_id))}:"]
    for s in segs:
        line = f"  [{s['start_s']:.1f}s-{s['end_s']:.1f}s] {s['text']}"
        lines.append(line)
        if word_level and s.get("words"):
            word_str = " | ".join(
                f"{w['word']}({w['start_s']:.2f})" for w in s["words"][:8]
            )
            lines.append(f"    words: {word_str}")
    return "\n".join(lines)


AUDIO_TOOLS = [generate_captions, remove_silence, get_transcript]
ALL_TOOLS.extend(AUDIO_TOOLS)


# Animation / keyframe tools

@tool
def get_clip_params(clip_id: str) -> str:
    """
    List all animatable parameters for a clip with their current values,
    valid ranges, and whether they are currently animated (have keyframes).

    Always call this first to discover what you can animate on a clip before
    calling animate_property.

    Args:
        clip_id: The clipId of any clip (text, shape, video, pen, etc.)
    """
    result = _get(f"/anim/{clip_id}/params")
    params = result.get("params", [])
    lines = [f"Clip {clip_id[:8]} ({result.get('clipType', '?')}) -- animatable params:"]
    for p in params:
        anim_flag = " [ANIMATED]" if p.get("animated") else ""
        lines.append(
            f"  {p['id']:<14} {p.get('label',''):<18} "
            f"val={p.get('default', '?')!s:<10} "
            f"range=[{p.get('min','?')}, {p.get('max','?')}]"
            f"{anim_flag}"
        )
    return "\n".join(lines)


@tool
def animate_property(
    clip_id: str,
    param: str,
    frame: int,
    value: float,
    easing: str = "ease_both",
    preset: str = "",
    handle_in_frames: float = -8.0,
    handle_in_value: float = 0.0,
    handle_out_frames: float = 8.0,
    handle_out_value: float = 0.0,
) -> str:
    """
    Add or update a keyframe on any animatable property of a clip.
    Call multiple times with different frames to build an animation.
    After adding 2+ keyframes, call apply_curve_preset() to shape the motion.

    Common params (use get_clip_params to see all for a clip):
      pos_x, pos_y -- position in pixels (0,0 = center of frame)
      scale_x, scale_y -- scale multiplier (1.0 = 100%)
      rotation -- degrees (-360 to 360)
      opacity -- 0.0 (invisible) to 1.0 (fully visible)
      anchor_x, anchor_y -- pivot/anchor point in pixels
      font_size -- (TextClip) font size in pixels
      fill_r/g/b/a -- RGBA fill colour channels 0.0 to 1.0
      shape_w, shape_h -- (ShapeClip) width/height in pixels
      stroke_w -- stroke width in pixels

    Easing options (ignored if preset is set):
      ease_both  -- slow in AND slow out (best for most motion, default)
      ease_in    -- slow start, fast end
      ease_out   -- fast start, slow end (good for entrances)
      linear     -- constant speed
      constant   -- instant jump at keyframe
      bezier     -- manual control via handle_* args

    PREFERRED: Use preset= instead of easing= for expressive motion:
      preset="bounce_out"   preset="elastic_out"   preset="cinematic"
      preset="snap"         preset="anticipate"     preset="fade_in"
      Call list_curve_presets() to see all 18 options.

    Args:
        clip_id: The clipId of the target clip.
        param: Parameter name (e.g. 'pos_x', 'opacity', 'font_size').
        frame: Timeline frame number to place this keyframe.
        value: Value at this keyframe.
        preset: Named curve preset — overrides easing and handle args when set.
        easing: Fallback interpolation type (used when preset is not set).
        handle_in_frames: Left bezier handle frame offset (bezier mode only).
        handle_in_value: Left bezier handle value offset.
        handle_out_frames: Right bezier handle frame offset.
        handle_out_value: Right bezier handle value offset.
    """
    # Resolve preset → easing + handles before sending to backend
    _hin_f, _hin_v, _hout_f, _hout_v = handle_in_frames, handle_in_value, handle_out_frames, handle_out_value
    _easing = easing
    if preset:
        from backend.animation.curve_presets import CURVE_PRESETS
        p = CURVE_PRESETS.get(preset)
        if p:
            _easing = p["interp"] if p["interp"] != "bezier" else "bezier"
             
            _hout_f = p["out_frame_frac"] * 10.0
            _hout_v = p["out_value_frac"]
            _hin_f  = p["in_frame_frac"] * 10.0
            _hin_v  = p["in_value_frac"]

    result = _post(f"/anim/{clip_id}/keyframe", {
        "param": param,
        "frame": frame,
        "value": value,
        "easing": _easing,
        "handle_in_frames": _hin_f,
        "handle_in_value": _hin_v,
        "handle_out_frames": _hout_f,
        "handle_out_value":  _hout_v,
    })
    total = result.get("totalKeyframes", "?")
    kf    = result.get("keyframe", {})
    note  = f" [preset={preset}]" if preset else ""
    return (
        f"Keyframe added: {param} = {value} @ frame {frame} "
        f"(easing={kf.get('easing', _easing)}, total keyframes={total}){note}"
    )


@tool
def remove_keyframe(clip_id: str, param: str, frame: int) -> str:
    """
    Remove a single keyframe from an animated property on a clip.

    Args:
        clip_id: The clipId.
        param: Parameter name (e.g. 'pos_x', 'opacity').
        frame: Timeline frame number of the keyframe to remove.
    """
    _delete(f"/anim/{clip_id}/keyframe/{param}/{frame}")
    return f"Removed keyframe at frame {frame} for param '{param}' on clip {clip_id[:8]}."


@tool
def clear_animation(clip_id: str, param: str) -> str:
    """
    Remove ALL keyframes from a property, making it static again.
    The property will stay at its last evaluated value.

    Args:
        clip_id: The clipId.
        param: Parameter name (e.g. 'pos_x', 'opacity').
    """
    result = _post(f"/anim/{clip_id}/clear/{param}", {})
    removed = result.get("keyframesRemoved", 0)
    return f"Cleared {removed} keyframe(s) from '{param}' on clip {clip_id[:8]}. Property is now static."


@tool
def get_keyframes(clip_id: str) -> str:
    """
    Return all animated properties and their full keyframe graph for a clip.
    Shows frame, value, easing type, and bezier handle data for each keyframe.

    Args:
        clip_id: The clipId.
    """
    result = _get(f"/anim/{clip_id}/keyframes")
    animated = result.get("animated", [])
    if not animated:
        return f"No animated properties on clip {clip_id[:8]}."
    lines = [f"Animated properties on clip {clip_id[:8]} ({result.get('clipType', '?')}):"]
    for prop in animated:
        lines.append(f"\n  [{prop['param']}]")
        for kf in prop["keyframes"]:
            lines.append(
                f"    frame={kf['frame']:4d}  val={kf['value']:.4f}  easing={kf['easing']}"
                + (f"  handles=[{kf['handle_in_frames']:.1f},{kf['handle_out_frames']:.1f}]"
                   if kf.get("easing") == "bezier" else "")
            )
    return "\n".join(lines)


@tool
def set_text_content(clip_id: str, text: str) -> str:
    """
    Set the text content of a TextClip.
    Use this to update what a text clip says without recreating it.

    Args:
        clip_id: The clipId of the TextClip.
        text: The new text to display.
    """
    _patch(f"/clips/text/{clip_id}", {"text": text})
    return f"Text clip {clip_id[:8]} content updated to: \"{text[:80]}\""


@tool
def list_curve_presets() -> str:
    """List all 18 named animation curve presets with descriptions.

    Call this when the user asks for animation style options or before using
    apply_curve_preset(). Presets work on ANY animatable parameter: position,
    scale, opacity, rotation, text, shapes — everything.

    Examples of most useful presets:
      ease_both -- smooth S-curve (default, works everywhere)
      ease_out -- snappy entrance (great for sliding in)
      bounce_out  -- bounces at end (position, scale pop-ins)
      elastic_out -- spring arrival (UI elements)
      anticipate  -- pulls back before moving (cartoon feel)
      cinematic -- film timing (camera moves)
      snap -- quick UI snap
      fade_in -- holds then rises (opacity)
    """
    from backend.animation.curve_presets import list_presets
    rows = [f"  {p['name']:<14} ({p['interp']:<9}) — {p['description']}" for p in list_presets()]
    return "Available curve presets:\n" + "\n".join(rows)


@tool
def apply_curve_preset(
    clip_id: str,
    param: str,
    preset: str,
    frame_from: int = -1,
    frame_to: int = -1,
) -> str:
    """Apply a named curve preset to keyframes on a clip property.

    Works on ALL consecutive keyframe pairs in the given range:
      (kf0→kf1), (kf1→kf2), (kf2→kf3) ...
    Odd count of keyframes: last keyframe gets no change (no right neighbour).

    Use this AFTER animate_property() to shape the motion without touching
    raw bezier handles. Works identically for position, opacity, text, shapes.

    Args:
        clip_id: The clipId.
        param: Parameter name (e.g. 'pos_x', 'opacity', 'scale_x').
        preset: Curve preset name. Call list_curve_presets() to see all 18.
        frame_from: First timeline frame of the range (-1 = from first keyframe).
        frame_to: Last timeline frame of the range  (-1 = to last keyframe).

    Examples:
        apply_curve_preset(id, 'pos_x', 'bounce_out') # all keyframes
        apply_curve_preset(id, 'opacity', 'fade_in', 0, 30) # frames 0-30
        apply_curve_preset(id, 'scale_x', 'elastic_out', 0, 60)  # frames 0-60
    """
    body: dict = {"param": param, "preset": preset}
    if frame_from >= 0:
        body["frame_from"] = frame_from
    if frame_to >= 0:
        body["frame_to"] = frame_to
    result = _post(f"/anim/{clip_id}/apply-preset", body)
    pairs = result.get("pairsApplied", 0)
    kfs   = result.get("keyframesInRange", 0)
    return (
        f"Applied preset '{preset}' to {pairs} segment(s) on '{param}' "
        f"({kfs} keyframes in range) — clip {clip_id[:8]}."
    )


@tool
def move_keyframe(
    clip_id: str,
    param: str,
    from_frame: int,
    to_frame: int,
    preset: str = "",
) -> str:
    """Move an existing keyframe to a new frame position.

    Auto-recalculates handles on the moved keyframe and its neighbours.
    Optionally re-applies a curve preset to the segments touching the moved keyframe.

    Args:
        clip_id: The clipId.
        param: Parameter name (e.g. 'pos_x', 'opacity').
        from_frame: Current timeline frame of the keyframe.
        to_frame: New timeline frame to move it to.
        preset: Optional curve preset to re-apply after moving.
    """
    body: dict = {"param": param, "from_frame": from_frame, "to_frame": to_frame,
                  "recompute_handles": True}
    if preset:
        body["preset"] = preset
    result = _post(f"/anim/{clip_id}/move-keyframe", body)
    applied = result.get("appliedPreset")
    note = f" + reapplied preset '{applied}'" if applied else ""
    return (
        f"Moved keyframe '{param}' from frame {from_frame} → {to_frame}{note} "
        f"on clip {clip_id[:8]}."
    )


ANIMATION_TOOLS = [
    get_clip_params,
    animate_property,
    remove_keyframe,
    clear_animation,
    get_keyframes,
    set_text_content,
    list_curve_presets,
    apply_curve_preset,
    move_keyframe,
]
ALL_TOOLS.extend(ANIMATION_TOOLS)


#   TTS Tools  

@tool
def list_kokoro_voices(lang: str = "") -> str:
    """List all available Kokoro local TTS voices, optionally filtered by language.

    Args:
        lang: Optional language filter. One of: 'en-us', 'en-gb', 'ja', 'ko',
              'zh', 'es', 'fr', 'hi', 'it', 'pt'. Leave empty to list all.

    Returns a JSON map of language → [voice_ids].
    Popular voices: af_heart (warm female), bf_emma (British), am_echo (male).
    """
    import json
    params = {}
    if lang:
        params["lang"] = lang
    # Call the voices endpoint
    data = _get("/media/tts-voices")
     
    try:
        from backend.tools.generators.tts_generator import KOKORO_VOICES
        if lang:
            filtered = {lang: KOKORO_VOICES.get(lang, [])}
            return json.dumps({"kokoro_voices": filtered, "gemini_voices": data.get("voices", [])}, indent=2)
        return json.dumps({"kokoro_voices": KOKORO_VOICES, "gemini_voices": data.get("voices", [])}, indent=2)
    except Exception:
        return json.dumps(data, indent=2)


@tool
def generate_tts(
    text: str,
    voice: str = "af_heart",
    speed: float = 1.0,
) -> str:
    """Generate speech audio from text using Kokoro local TTS (or Gemini if configured).

    The generated WAV file is automatically imported into the library so you can
    immediately use place_clip() to add it to the timeline.

    Args:
        text:  The text to speak. Can be multiple sentences.
        voice: Voice ID (default 'af_heart' — warm American female).
               Kokoro voices: af_heart, af_bella, af_nicole, am_echo, am_michael,
                              bf_emma, bf_alice, bm_george, bm_daniel + 40 more.
               Gemini voices: Kore, Zephyr, Puck, Charon, Fenrir, Aoede, etc.
               Call list_kokoro_voices() to browse all options.
        speed: Speech speed multiplier (Kokoro only). Range: 0.5–2.0, default 1.0.
               0.8 = slightly slower, 1.2 = slightly faster.

    Returns:
        A summary string with assetId, duration — ready for place_clip().

    Example workflow:
        result = generate_tts("Welcome to the video!", voice="af_heart", speed=1.0)
        # parse assetId from result, then:
        place_clip(assetId, track=1, start_frame=0, duration_frames=int(duration_s*30))
    """
    import json, time as _time

    # Fire async job  
    body = {"text": text, "voice": voice, "speed": speed}
    job_resp = _post_long("/jobs/tts-generate", body, timeout=15)
    job_id = job_resp.get("jobId", "")
    if not job_id:
        return "Error: TTS job did not start — check backend logs."

    # Poll until done (max 5 min)
    for _ in range(150):
        _time.sleep(2)
        status = _get(f"/jobs/{job_id}")
        st = status.get("status", "")
        if st == "done":
            asset_ids = status.get("assetIds", [])
            asset_id  = asset_ids[0] if asset_ids else ""
            msg       = status.get("message", "")
            # Parse duration from message "Ready — X.Xs | voice"
            dur = 0.0
            try:
                dur = float(msg.split("—")[1].split("s")[0].strip())
            except Exception:
                pass
            return (
                f"✓ TTS generated: voice={voice}, duration={dur:.1f}s\n"
                f"  assetId={asset_id}\n"
                f"  → Use place_clip(assetId='{asset_id}', track=1, start_frame=0, "
                f"duration_frames={int(dur * 30)}) to add to timeline."
            )
        if st == "error":
            err = status.get("error", "unknown error")
            return f"TTS generation failed: {err}"
    return f"TTS generation timed out (job {job_id})."


TTS_TOOLS = [list_kokoro_voices, generate_tts]
ALL_TOOLS.extend(TTS_TOOLS)


#   Indexing control  

@tool
def stop_indexing(asset_id: str) -> str:
    """Stop / cancel semantic indexing for a specific media asset.

    Fade automatically starts AI indexing (Vision + Whisper) when a video or image
    is downloaded or imported. On low-end systems, or for B-roll footage that doesn't
    need semantic search, you can stop the job using this tool.

    This is safe to call at any time:
    - If the job is RUNNING  → the worker stops at the next frame-extraction checkpoint
      (within a few seconds).
    - If the job is QUEUED   → it is discarded before it starts.
    - If no job exists → this is a no-op (idempotent).

    Args:
        asset_id: The assetId of the media whose indexing should be stopped.
                  Get this from list_library_assets() or the result of a download tool.

    Returns:
        Confirmation string.

    Example:
        # User says "stop indexing that B-roll clip"
        assets = list_library_assets()
        # find the right assetId, then:
        stop_indexing("abc123...")
    """
    result = _post(f"/library/cancel-index/{asset_id}", {})
    status = result.get("status", "unknown")
    return (
        f"✓ Indexing cancelled for asset {asset_id[:8]}…\n"
        f"  Status: {status}\n"
        f"  The worker will stop at the next frame checkpoint. "
        f"No semantic search data will be saved for this asset."
    )


INDEXING_TOOLS = [stop_indexing]
ALL_TOOLS.extend(INDEXING_TOOLS)
