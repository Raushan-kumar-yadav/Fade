 
from __future__ import annotations
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.state import engine, _library, _clipTrackMap

router = APIRouter(tags=["scene"])


# helpers  

def _active_timeline():
    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(400, "No active timeline")
    return tl


def _fps() -> float:
    return float(engine.project.fps) if engine.project else 30.0


def _sec_to_frames(sec: float) -> int:
    return int(round(sec * _fps()))


def _find_clip_in_timeline(clip_id: str):
    tl = _active_timeline()
    for ti, track in enumerate(tl.tracks):
        for clip in getattr(track, "clips", []):
            if clip.clipId == clip_id:
                return clip, track, ti
    raise HTTPException(404, f"Clip '{clip_id}' not found")


def _top_empty_track(start_frame: int, duration: int, prefer_index: int = -1):
    """Return a track that has room, or create a new VideoTrack."""
    from backend.timeline.tracks.videoTrack import VideoTrack
    tl = _active_timeline()
    end_frame = start_frame + duration

    if prefer_index >= 0 and prefer_index < len(tl.tracks):
        return tl.tracks[prefer_index]

    video_tracks = [t for t in tl.tracks if not getattr(t, "isAudio", lambda: False)()]
    for track in reversed(video_tracks):
        overlaps = any(
            not (c.startFrame >= end_frame or c.startFrame + c.duration <= start_frame)
            for c in getattr(track, "clips", [])
        )
        if not overlaps:
            return track

    new_track = VideoTrack(f"Video {len(video_tracks) + 1}")
    tl.addTrack(new_track)
    return new_track


# Request models  

class AddClipBySceneRequest(BaseModel):
    description: str          
    track: int = -1           
    frameOnTimeline: int = 0   
    topK: int = 1             
    durationOverride: int | None = None  


class RemoveClipRequest(BaseModel):
    clipId: str


#   Routes  

@router.get("/scene/search")
def sceneSearch(q: str, k: int = 8, type: str = "all"):
    """
    Semantic search over indexed video/image assets.
    type: 'all' | 'video' | 'image'
    Returns ranked hits with assetId, time range, score, and description.
    """
    from backend.ai.VideoSemantic.indexer import search_videos, search_images, search_all
    if type == "video":
        hits = search_videos(q, top_k=k)
    elif type == "image":
        hits = search_images(q, top_k=k)
    else:
        hits = search_all(q, top_k=k)

    # Enrich with filename from library
    for h in hits:
        asset = _library.get(h["assetId"])
        h["filename"] = os.path.basename(asset.filepath) if asset else "unknown"

    return {"query": q, "hits": hits}


@router.post("/scene/add-video-clip")
def addVideoClipByScene(req: AddClipBySceneRequest):
    """
    Search video scenes by natural language description.
    The top result's in/out points become the clip's mediaOffset + duration.
    Returns the created clip info.
    """
    from backend.ai.VideoSemantic.indexer import search_videos
    from backend.timeline.clips.videoClip import VideoClip
    from backend.history.commandStack import AddClipCommand
    from backend.events import notify

    hits = search_videos(req.description, top_k=max(req.topK, 5))
    if not hits:
        raise HTTPException(404, "No indexed video scenes match that description")

    hit = hits[min(req.topK - 1, len(hits) - 1)]
    asset_id = hit["assetId"]
    start_sec  = hit["start_sec"]
    end_sec = hit["end_sec"]
    asset = _library.get(asset_id)

    if not asset:
        raise HTTPException(404, f"Asset '{asset_id}' not in library")

    fps = _fps()
    media_offset  = _sec_to_frames(start_sec)
    clip_duration = req.durationOverride or _sec_to_frames(end_sec - start_sec)
    clip_duration = max(1, clip_duration)

    clip  = VideoClip(
        startFrame=req.frameOnTimeline,
        duration=clip_duration,
        assetId=asset_id,
        mediaOffset=media_offset,
    )
    if engine.scheduler:
        clip.setScheduler(engine.scheduler, fps)
        engine.scheduler.registerClip(clip.clipId, asset)

    track = _top_empty_track(req.frameOnTimeline, clip_duration, prefer_index=req.track)
    engine.commandStack.execute(AddClipCommand(track, clip))
    _clipTrackMap[clip.clipId] = engine.activeTimeline.tracks.index(track)

    notify("timeline")
    print(
        f"[SceneTools] Added VideoClip {clip.clipId[:8]} from {os.path.basename(asset.filepath)} "
        f"[{start_sec:.1f}s–{end_sec:.1f}s] → frame {req.frameOnTimeline} (score={hit['score']:.2f})",
        flush=True,
    )

    return {
        "clipId": clip.clipId,
        "assetId": asset_id,
        "filename": os.path.basename(asset.filepath),
        "startFrame": clip.startFrame,
        "duration": clip_duration,
        "mediaOffset": media_offset,
        "inPointSec": start_sec,
        "outPointSec": end_sec,
        "score": hit["score"],
        "sceneText": hit["text"],
        "trackIndex": engine.activeTimeline.tracks.index(track),
    }


@router.post("/scene/add-image-clip")
def addImageClipByScene(req: AddClipBySceneRequest):
    """
    Search indexed images by natural language description and add an ImageClip.
    """
    from backend.ai.VideoSemantic.indexer import search_images
    from backend.timeline.clips.imageClip import ImageClip
    from backend.history.commandStack import AddClipCommand
    from backend.events import notify

    hits = search_images(req.description, top_k=max(req.topK, 5))
    if not hits:
        raise HTTPException(404, "No indexed images match that description")

    hit = hits[min(req.topK - 1, len(hits) - 1)]
    asset_id = hit["assetId"]
    asset = _library.get(asset_id)

    if not asset:
        raise HTTPException(404, f"Asset '{asset_id}' not in library")

    clip_duration = req.durationOverride or int(5 * _fps())  # default 5s

    clip = ImageClip(
        startFrame=req.frameOnTimeline,
        duration=clip_duration,
        assetId=asset_id,
        filepath=asset.filepath,
    )

    track = _top_empty_track(req.frameOnTimeline, clip_duration, prefer_index=req.track)
    engine.commandStack.execute(AddClipCommand(track, clip))
    _clipTrackMap[clip.clipId] = engine.activeTimeline.tracks.index(track)

    notify("timeline")
    print(
        f"[SceneTools] Added ImageClip {clip.clipId[:8]} from {os.path.basename(asset.filepath)} "
        f"→ frame {req.frameOnTimeline} (score={hit['score']:.2f})",
        flush=True,
    )

    return {
        "clipId": clip.clipId,
        "assetId": asset_id,
        "filename": os.path.basename(asset.filepath),
        "startFrame": clip.startFrame,
        "duration":   clip_duration,
        "score": hit["score"],
        "sceneText":  hit["text"],
        "trackIndex": engine.activeTimeline.tracks.index(track),
    }


@router.get("/scene/clip-info/{clipId}")
def getClipInfo(clipId: str):
    """
    Return detailed info about a clip: asset, in/out points, track, and
    any indexed scene text for that time range.
    """
    from backend.ai.VideoSemantic.indexer import search_videos

    clip, track, track_idx = _find_clip_in_timeline(clipId)
    asset   = _library.get(getattr(clip, "assetId", ""))
    fps = _fps()

    media_offset = getattr(clip, "mediaOffset", 0)
    in_point_sec = media_offset / fps
    out_point_sec = (media_offset + clip.duration) / fps

    # Try to fetch related scene text from ChromaDB
    scene_text = None
    if asset and hasattr(clip, "mediaOffset"):
        hits = search_videos(
            f"video asset {getattr(asset, 'filepath', '')}",
            top_k=20,
        )
        # Find chunks that overlap this clip's time window
        overlapping = [
            h for h in hits
            if h["assetId"] == getattr(clip, "assetId", "")
            and h["start_sec"] < out_point_sec
            and h["end_sec"] > in_point_sec
        ]
        if overlapping:
            scene_text = " | ".join(h["text"] for h in overlapping[:3])

    return {
        "clipId": clip.clipId,
        "type": getattr(clip, "CLIP_TYPE", "unknown"),
        "assetId": getattr(clip, "assetId", None),
        "filename": os.path.basename(asset.filepath) if asset else None,
        "filepath": asset.filepath if asset else None,
        "startFrame": clip.startFrame,
        "duration": clip.duration,
        "mediaOffset": media_offset,
        "inPointSec": round(in_point_sec, 3),
        "outPointSec": round(out_point_sec, 3),
        "trackIndex": track_idx,
        "trackName": getattr(track, "name", f"Track {track_idx}"),
        "sceneText": scene_text,
    }


@router.delete("/scene/remove-clip/{clipId}")
def removeClip(clipId: str):
    """Remove a clip from the timeline by clipId."""
    from backend.history.commandStack import RemoveClipCommand
    from backend.events import notify

    clip, track, track_idx = _find_clip_in_timeline(clipId)
    engine.commandStack.execute(RemoveClipCommand(track, clip))
    _clipTrackMap.pop(clipId, None)
    notify("timeline")
    print(f"[SceneTools] Removed clip {clipId[:8]} from track {track_idx}", flush=True)
    return {"removed": True, "clipId": clipId, "trackIndex": track_idx}


@router.get("/scene/list-clips")
def listClips():
    """
    List all clips on the active timeline with asset info and time positions.
    """
    tl  = _active_timeline()
    fps = _fps()
    clips_out = []

    for ti, track in enumerate(tl.tracks):
        for clip in getattr(track, "clips", []):
            asset    = _library.get(getattr(clip, "assetId", ""))
            offset   = getattr(clip, "mediaOffset", 0)
            clips_out.append({
                "clipId": clip.clipId,
                "type": getattr(clip, "CLIP_TYPE", "unknown"),
                "assetId": getattr(clip, "assetId", None),
                "filename": os.path.basename(asset.filepath) if asset else None,
                "startFrame": clip.startFrame,
                "startSec": round(clip.startFrame / fps, 3),
                "duration": clip.duration,
                "durationSec": round(clip.duration / fps, 3),
                "inPointSec": round(offset / fps, 3),
                "outPointSec": round((offset + clip.duration) / fps, 3),
                "trackIndex": ti,
                "trackName": getattr(track, "name", f"Track {ti}"),
            })

    clips_out.sort(key=lambda c: (c["trackIndex"], c["startFrame"]))
    return {"fps": fps, "clips": clips_out, "total": len(clips_out)}
