 
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

#   playback  

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
def add_text_clip(track_index: int, start_frame: int, duration: int,
                  text: str, font_size: float = 48.0) -> str:
    """Add a text / subtitle clip to the timeline.
    Args:
        track_index: Track to place the text clip on (0-based).
        start_frame: When the text appears (timeline frame).
        duration: How many frames the text stays visible.
        text: The text content to display.
        font_size: Font size in points (default 48).
    """
    result = _post("/clips/text", {
        "trackIndex": track_index,
        "startFrame": start_frame,
        "duration": duration,
        "text": text,
        "fontSize": font_size,
    })
    return f"Added text clip '{text}' at frame {start_frame} (clipId={result.get('clipId')})."

# transitions  

@tool
def get_transitions_catalog() -> str:
    """Return all available transition types."""
    data = _get("/transitions/catalog")
    return json.dumps(data, indent=2)

@tool
def add_transition(clip_a_id: str, clip_b_id: str,
                   type_id: str = "fade", duration_frames: int = 15) -> str:
    """Add a transition between two consecutive clips.
    Args:
        clip_a_id: The clipId of the first (outgoing) clip.
        clip_b_id: The clipId of the second (incoming) clip.
        type_id: Transition type, e.g. 'fade', 'dissolve', 'wipe_left'.
                 Use get_transitions_catalog() to see valid types.
        duration_frames: Length of the transition overlap in frames.
    """
    result = _post("/transitions", {
        "typeId": type_id,
        "duration": duration_frames,
        "clipA_id": clip_a_id,
        "clipB_id": clip_b_id,
    })
    return f"Added '{type_id}' transition between {clip_a_id} and {clip_b_id}."

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
def place_clip(asset_id: str, track_index: int, start_frame: int, duration: int) -> str:
    """Place a media asset onto the timeline as a clip.
    Args:
        asset_id: The assetId of the media (get this from download_videos or get_library).
        track_index: The track index to place it on (0-based).
        start_frame: Timeline frame where the clip starts.
        duration: Duration of the clip in frames.
    """
    result = _post("/timeline/add-clip", {
        "assetId": asset_id,
        "trackIndex": track_index,
        "startFrame": start_frame,
        "duration": duration
    })
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
    undo,
    redo,
    mute_track,
    download_videos,
    download_images,
    generate_image,
    place_clip,
]
