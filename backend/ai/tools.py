 
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

def _post(path: str, body: dict | None = None) -> dict:
    r = httpx.post(f"{_base()}{path}", json=body or {}, timeout=30)
    r.raise_for_status()
    return r.json()

def _delete(path: str) -> dict:
    r = httpx.delete(f"{_base()}{path}", timeout=10)
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

# text clips  

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
        comp_id: Optional compId if adding to a nested composition.
    """
    if comp_id:
        _post(f"/comps/{comp_id}/activate")
    
    result = _post("/clips/text", {
        "trackIndex": track_index,
        "startFrame": start_frame,
        "duration": duration,
        "text": text,
        "fontFamily": font,
    })
    
    if comp_id:
        _post("/comps/root/activate")
        
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
            # Only add if clips actually touch or overlap
            gap = b["startFrame"] - (a["startFrame"] + a["duration"])
            if gap > 90:          # more than 3s gap — skip
                skipped += 1
                continue
            try:
                _post("/transitions", {
                    "typeId":   type_id,
                    "duration": duration_frames,
                    "clipA_id": a["id"],
                    "clipB_id": b["id"],
                })
                added += 1
            except Exception as exc:
                errors.append(f"track{ti}/{a['id'][:8]}: {exc}")

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

# downloader

@tool
def download_videos(query: str, num_videos: int = 2) -> str:
    """Search YouTube and download videos into the project media library.
    
    Args:
        query: Search query string, e.g. 'cinematic sunset 4k'.
        num_videos: Number of top results to download (default 2, max 5).
    
    Returns JSON with imported assetIds and duration in frames so you can
    immediately use place_clip() to add them to the timeline.
    """
    num_videos = max(1, min(num_videos, 5))
    result = _post("/media/download-search", {
        "query": query,
        "numVideos": num_videos
    })
    return json.dumps(result, indent=2)

@tool
def download_images(query: str, num_images: int = 2) -> str:
    """Search DuckDuckGo and download images into the project media library.
    
    Args:
        query: Search query string, e.g. 'cyberpunk city'.
        num_images: Number of top results to download (default 2, max 10).
    
    Returns JSON with imported assetIds so you can immediately use place_clip()
    to add them to the timeline.
    """
    num_images = max(1, min(num_images, 10))
    result = _post("/media/download-images", {
        "query": query,
        "numImages": num_images
    })
    return json.dumps(result, indent=2)

@tool
def place_clip(
    asset_id: str, 
    track_index: int, 
    start_frame: int, 
    duration: int,
    comp_id: str | None = None
) -> str:
    """Place a media asset onto the timeline as a clip.
    Args:
        asset_id: The assetId of the media (get this from download_videos or get_library).
        track_index: The track index to place it on (0-based).
        start_frame: Timeline frame where the clip starts.
        duration: Duration of the clip in frames.
        comp_id: Optional compId if adding to a nested composition instead of main timeline.
    """
    if comp_id:
        _post(f"/comps/{comp_id}/activate")
        
    result = _post("/timeline/add-clip", {
        "assetId": asset_id,
        "trackIndex": track_index,
        "startFrame": start_frame,
        "duration": duration
    })
    
    if comp_id:
        _post("/comps/root/activate")
        
    return f"Placed asset {asset_id} on track {track_index} at frame {start_frame} with clipId {result.get('clipId')}."

@tool
def generate_image(prompt: str, num_images: int = 1) -> str:
    """Generate AI image(s) from a text prompt using the Gemini Imagen model.

    Args:
        prompt:     Detailed description of the image to create.
                    Example: 'a cinematic sunset over mountains, photorealistic 4k'
        num_images: Number of images to generate (1–4, default 1).

    Returns JSON with assetIds so you can immediately place them on the timeline
    using place_clip().
    """
    result = _post("/media/generate-image", {
        "prompt": prompt,
        "numImages": num_images,
    })
    return json.dumps(result, indent=2)

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
    """Add a media clip (video or image) from the library into a nested composition.

    This activates the comp, adds the clip, then returns to root automatically.

    Args:
        comp_id: The compId of the target composition.
        asset_id: The assetId of the media to add (get from get_library()).
        track_index: Which track inside the comp to add to (0 = first).
        start_frame: Frame inside the comp where the clip starts.
        duration: Duration in frames.
    """
    # Activate comp  
    _post(f"/comps/{comp_id}/activate")
    result = _post("/timeline/add-clip", {
        "assetId": asset_id,
        "trackIndex": track_index,
        "startFrame": start_frame,
        "duration": duration,
    })
    _post("/comps/root/activate")
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
        comp_id: Optional compId if adding to a nested composition.
    """
    if comp_id:
        _post(f"/comps/{comp_id}/activate")
        
    result = _post("/clips/shape", {
        "trackIndex": track_index,
        "startFrame": start_frame,
        "duration": duration,
        "shapeType": "rectangle",
        "fillR": r, "fillG": g, "fillB": b, "fillA": a,
        "strokeA": 0.0,
        "width": 1920, "height": 1080,
    })
    
    if comp_id:
        _post("/comps/root/activate")
        
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
        comp_id: Optional compId if adding to a nested composition.
    """
    if comp_id:
        _post(f"/comps/{comp_id}/activate")
        
    result = _post("/clips/shape", {
        "trackIndex": track_index,
        "startFrame": start_frame,
        "duration": duration,
        "shapeType": shape_type,
        "fillR": fill_r, "fillG": fill_g, "fillB": fill_b, "fillA": fill_a,
        "strokeA": 0.0,
        "width": width, "height": height,
    })
    
    if comp_id:
        _post("/comps/root/activate")
        
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
    download_videos,
    download_images,
    generate_image,
    search_news,
    create_news_video,
    get_selected_clip,
    list_effects_catalog,
    apply_effect_to_clip,
    patch_clip_effect,
    place_clip,
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
    html: str = "",
    css: str = "",
    js: str = "",
    template: str = "blank",
    duration_seconds: float = 5.0,
) -> str:
    """Create a WebComp — an animated HTML/CSS/JS scene rendered as video pixels on the timeline.

    The page receives these globals each frame (Electron injects them):
      window.FADE_FRAME  — current frame number (int, 0-indexed)
      window.FADE_TIME   — current time in seconds (float)
      window.FADE_FPS    — project FPS
      window.FADE_WIDTH  — canvas width in pixels
      window.FADE_HEIGHT — canvas height in pixels
      window.FADE_PARAMS — runtime params from the inspector panel (object)

    Listen for frame updates:
      window.addEventListener('fade:frame', (e) => {
        const { frame, time } = e.detail;
        // update animation here
      });

    Args:
        name: Human-readable name
        html: Full index.html (overrides template if provided)
        css: style.css content (overrides template)
        js: script.js content (overrides template)
        template: Starter template — "blank" | "lower-third" | "neon-headline" | "kinetic-title"
        duration_seconds: Default clip duration when placed on timeline
    """
    body: dict = {"name": name, "template": template}
    result = _post("/timeline/webcomp/create", body)
    asset_id = result.get("assetId", "")
    folder = result.get("folderPath", "")

    if html:
        _post("/timeline/webcomp/write-file", {"webcompId": asset_id, "filename": "index.html", "content": html})
    if css:
        _post("/timeline/webcomp/write-file", {"webcompId": asset_id, "filename": "style.css", "content": css})
    if js:
        _post("/timeline/webcomp/write-file", {"webcompId": asset_id, "filename": "script.js", "content": js})

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

    Common files: index.html, style.css, script.js, webcomp.json
    After editing, call reload_webcomp() to see changes in the preview immediately.

    Args:
        webcomp_id: The assetId of the WebComp
        filename: File to write (e.g. "script.js")
        content: Full file content to write
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


#   Register all WebComp tools with the LangGraph agent  

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
