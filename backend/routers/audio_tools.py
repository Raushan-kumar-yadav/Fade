 
from __future__ import annotations
import os
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.state import engine, _library, _clipTrackMap

router = APIRouter(tags=["audio-tools"])


#   helpers  

def _active_tl():
    tl = engine.activeTimeline if engine else None
    if tl is None:
        raise HTTPException(400, "No active timeline")
    return tl


def _fps() -> float:
    return float(engine.project.fps) if engine and engine.project else 30.0


def _sec_to_frames(sec: float) -> int:
    return max(1, int(round(sec * _fps())))


def _find_clip(clip_id: str):
    """Return (clip, track, track_index) or raise 404."""
    tl = _active_tl()
    for ti, track in enumerate(tl.tracks):
        for clip in getattr(track, "clips", []):
            if clip.clipId == clip_id:
                return clip, track, ti
    raise HTTPException(404, f"Clip '{clip_id}' not found")


def _resolve_filepath(clip) -> str:
    """Get the media filepath for any clip type."""
    fp = getattr(clip, "filepath", "")
    if not fp:
        asset = _library.get(getattr(clip, "assetId", ""))
        if asset:
            fp = getattr(asset, "filepath", "")
    if not fp:
        raise HTTPException(400, f"Clip '{clip.clipId}' has no resolvable media filepath")
    if not os.path.isfile(fp):
        raise HTTPException(400, f"Media file not found: {fp}")
    return fp


def _index_transcript(asset_id: str, segments: list[dict]) -> int:
     
    if not asset_id or not segments:
        return 0
    try:
        from backend.ai.VideoSemantic.indexer import index_video, is_asset_indexed
        if is_asset_indexed(asset_id):
            print(f"[AudioTools] ChromaDB: asset {asset_id[:8]} already indexed — skipping", flush=True)
            return 0
        chunks = [
            {
                "start_sec": s["start_s"],
                "end_sec":   s["end_s"],
                "text":      s["text"],
            }
            for s in segments
            if s.get("text", "").strip()
        ]
        count = index_video(asset_id, chunks)
        print(f"[AudioTools] ChromaDB: indexed {count} transcript chunks for {asset_id[:8]}", flush=True)
        return count
    except Exception as exc:
        # Non-fatal  
        print(f"[AudioTools] ChromaDB index failed (non-fatal): {exc}", flush=True)
        return 0


def _find_or_create_caption_track(tl, above_track_index: int, label: str):
    """
    Find an existing track named `label`, or create a new VideoTrack
    inserted directly above `above_track_index`.
    """
    from backend.timeline.tracks.videoTrack import VideoTrack
    for track in tl.tracks:
        if getattr(track, "name", "") == label:
            return track
    new_track = VideoTrack(label)
    # Insert above the source track (lower index = rendered on top in UI)
    insert_at = max(0, above_track_index)
    tl.tracks.insert(insert_at, new_track)
    return new_track


def _top_empty_track_for(tl, start_frame: int, duration: int, prefer_track=None):
    """Return prefer_track if it has room, else find/create a free track."""
    from backend.timeline.tracks.videoTrack import VideoTrack
    end_frame = start_frame + duration

    if prefer_track is not None:
        overlaps = any(
            not (c.startFrame >= end_frame or c.startFrame + c.duration <= start_frame)
            for c in getattr(prefer_track, "clips", [])
        )
        if not overlaps:
            return prefer_track

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


#   Request models  

class GenerateCaptionsRequest(BaseModel):
    clipId: str
    minWords: int = 2          
    language: str | None = None
    # Caption style overrides 
    style: dict = {}


class RemoveSilenceRequest(BaseModel):
    clipId: str
    minSilenceMs: int = 500    
    paddingMs: int = 80       
    language: str | None = None


#   Caption default style  

_CAPTION_STYLE_DEFAULTS = {
    "fontFamily": "Arial",
    "fontSize": 54.0,
    "bold": True,
    "alignment": "center",
    "color": [1.0, 1.0, 1.0, 1.0],        # white
    "strokeColor": [0.0, 0.0, 0.0, 1.0],         # black outline
    "strokeWidth": 2.5,
    "shadowEnabled":  True,
    "shadowColor": [0.0, 0.0, 0.0, 0.7],
    "shadowOffsetX": 2.0,
    "shadowOffsetY":  2.0,
    "shadowBlur": 4.0,
    "bgEnabled": False,
    "maxWidth": 1600.0,
    "lineHeight": 1.2,
}


def _build_caption_style(overrides: dict):
    from backend.timeline.clips.textClip import TextStyle
    merged = {**_CAPTION_STYLE_DEFAULTS, **overrides}
    return TextStyle.fromDict(merged)


#   Route: generate captions  

@router.post("/audio/generate-captions")
def generateCaptions(req: GenerateCaptionsRequest):
     
    from backend.ai.whisper_tool import transcribe
    from backend.timeline.clips.textClip import TextClip
    from backend.history.commandStack import AddClipCommand
    from backend.events import notify

    clip, source_track, source_track_idx = _find_clip(req.clipId)
    filepath = _resolve_filepath(clip)
    fps = _fps()
    tl = _active_tl()
    fname = os.path.basename(filepath)

    # Register transcription 
    asset_id = getattr(clip, "assetId", "")
    _job_id: str | None = None
    try:
        from backend.routers.jobs import register_asset_job as _rj
        _job_id = _rj("transcription", asset_id,
                       f"Transcribing: {fname}",
                       message="Running Whisper…")
    except Exception:
        pass

    #   Transcribe  
    print(f"[AudioTools] Generating captions for clip {req.clipId[:8]} → {fname}", flush=True)
    try:
        segments = transcribe(filepath, language=req.language)
    finally:
        # Always complete the job  
        try:
            from backend.routers.jobs import complete_asset_job as _cj
            _cj(asset_id, "transcription", job_id=_job_id)
        except Exception:
            pass

    if not segments:
        return {"captionCount": 0, "segments": [], "message": "No speech detected in clip."}

    # Save to ChromaDB  
    indexed = _index_transcript(asset_id, segments)

    #   Merge segments shorter than minWords 
    merged: list[dict] = []
    buf: dict | None = None
    for seg in segments:
        word_count = len(seg["text"].split())
        if buf is None:
            buf = dict(seg)
        elif word_count < req.minWords:
            # absorb into previous
            buf["end_s"] = seg["end_s"]
            buf["text"] += " " + seg["text"]
        else:
            merged.append(buf)
            buf = dict(seg)
    if buf:
        merged.append(buf)

    # Build caption style  
    style = _build_caption_style(req.style)

    # Find/create caption track above source  
    asset = _library.get(getattr(clip, "assetId", ""))
    fname = os.path.basename(filepath) if filepath else "clip"
    caption_track_name = f"Captions – {fname}"
    caption_track = _find_or_create_caption_track(tl, source_track_idx, caption_track_name)

    # Place TextClips  
    created = []
     
    clip_offset_sec = getattr(clip, "mediaOffset", 0) / fps

    for seg in merged:
        # Convert file-relative timestamps 
        seg_start_in_file = seg["start_s"]
        seg_end_in_file = seg["end_s"]

        # Skip segments outside 
        clip_in_sec = clip_offset_sec
        clip_out_sec = clip_offset_sec + (clip.duration / fps)
        if seg_end_in_file <= clip_in_sec or seg_start_in_file >= clip_out_sec:
            continue

        # Clamp to clip boundary
        seg_start_in_file = max(seg_start_in_file, clip_in_sec)
        seg_end_in_file = min(seg_end_in_file,   clip_out_sec)

        # Timeline position
        tl_start = clip.startFrame + _sec_to_frames(seg_start_in_file - clip_in_sec)
        tl_dur = max(1, _sec_to_frames(seg_end_in_file - seg_start_in_file))

        caption = TextClip(
            clipId=str(uuid.uuid4()),
            startFrame=tl_start,
            duration=tl_dur,
            style=style,
        )
        caption.style.text = seg["text"]

        # Position at bottom-center of frame
        try:
            caption.transform.position.setBaseValue((0.0, 420.0))  
        except Exception:
            pass

        tl.commandStack.execute(AddClipCommand(caption_track, caption)) if hasattr(tl, "commandStack") \
            else engine.commandStack.execute(AddClipCommand(caption_track, caption))

        created.append({
            "clipId": caption.clipId,
            "text": seg["text"],
            "startFrame": tl_start,
            "duration": tl_dur,
            "startSec": round(tl_start / fps, 3),
        })

    notify("timeline")
    print(f"[AudioTools] Created {len(created)} caption clips on track '{caption_track_name}'", flush=True)

    return {
        "captionCount": len(created),
        "trackName": caption_track_name,
        "segments": created,
    }


#   Route 

@router.post("/audio/remove-silence")
def removeSilence(req: RemoveSilenceRequest):
     
    from backend.ai.whisper_tool import get_speech_segments
    from backend.timeline.clips.videoClip import VideoClip
    from backend.history.commandStack import AddClipCommand, RemoveClipCommand
    from backend.events import notify

    clip, source_track, source_track_idx = _find_clip(req.clipId)
    filepath = _resolve_filepath(clip)
    fps = _fps()
    tl = _active_tl()

    clip_type = getattr(clip, "CLIP_TYPE", "video")
    if clip_type not in ("video",):
        raise HTTPException(400, f"remove_silence only works on VideoClips (got '{clip_type}')")

    print(f"[AudioTools] remove-silence for clip {req.clipId[:8]} → {os.path.basename(filepath)}", flush=True)

    # Get speech windows via VAD  
    speech_segs = get_speech_segments(
        filepath,
        min_silence_ms=req.minSilenceMs,
    )

    if not speech_segs:
        return {
            "message": "No speech detected — clip unchanged.",
            "clipCount": 0,
            "removedSilenceSec": 0.0,
        }

    pad_sec = req.paddingMs / 1000.0

    # clip's own media range  
    clip_offset_sec = getattr(clip, "mediaOffset", 0) / fps
    clip_duration_sec  = clip.duration / fps
    clip_in_sec = clip_offset_sec
    clip_out_sec = clip_offset_sec + clip_duration_sec

    #   Build trimmed segments 
    trimmed: list[dict] = []
    for seg in speech_segs:
        seg_in  = max(seg["start_s"] - pad_sec, clip_in_sec)
        seg_out = min(seg["end_s"] + pad_sec, clip_out_sec)
        if seg_out <= seg_in:
            continue
        trimmed.append({"in_sec": seg_in, "out_sec": seg_out})

    if not trimmed:
        return {
            "message": "Speech segments fall outside the clip range — clip unchanged.",
            "clipCount": 0,
        }

    # Remove original clip 
    engine.commandStack.execute(RemoveClipCommand(source_track, clip))
    _clipTrackMap.pop(req.clipId, None)

    # Place trimmed clips  
    cursor = clip.startFrame
    new_clips = []
    asset_id = getattr(clip, "assetId", "")

    for seg in trimmed:
        dur_frames = max(1, _sec_to_frames(seg["out_sec"] - seg["in_sec"]))
        offset_frames = _sec_to_frames(seg["in_sec"])

        new_clip = VideoClip(
            clipId=str(uuid.uuid4()),
            startFrame=cursor,
            duration=dur_frames,
            assetId=asset_id,
            mediaOffset=offset_frames,
        )
        # Re-attach scheduler  
        if engine.scheduler:
            asset = _library.get(asset_id)
            new_clip.setScheduler(engine.scheduler, fps)
            if asset:
                engine.scheduler.registerClip(new_clip.clipId, asset)

        engine.commandStack.execute(AddClipCommand(source_track, new_clip))
        _clipTrackMap[new_clip.clipId] = source_track_idx

        new_clips.append({
            "clipId": new_clip.clipId,
            "startFrame": cursor,
            "duration": dur_frames,
            "mediaIn": seg["in_sec"],
            "mediaOut": seg["out_sec"],
        })
        cursor += dur_frames

    new_duration_sec = (cursor - clip.startFrame) / fps
    removed_sec = round(clip_duration_sec - new_duration_sec, 3)

    notify("timeline")
    print(
        f"[AudioTools] Removed {removed_sec:.2f}s of silence → "
        f"{len(new_clips)} clips, new duration {new_duration_sec:.2f}s",
        flush=True,
    )

    return {
        "originalDuration":  round(clip_duration_sec, 3),
        "newDuration": round(new_duration_sec, 3),
        "removedSilenceSec": removed_sec,
        "clipCount": len(new_clips),
        "clips": new_clips,
    }


#   Route: raw transcription  

@router.get("/audio/transcribe/{clipId}")
def transcribeClip(clipId: str, words: bool = False, language: str | None = None):
    """Return transcript for a clip.

    Strategy (fastest first):
    1. If ChromaDB already has segments for this asset → return them immediately
       (background worker already ran Whisper; no need to do it again).
    2. Otherwise run Whisper synchronously and store the result in ChromaDB.
    """
    from backend.ai.whisper_tool import transcribe, transcribe_with_words
    from backend.ai.VideoSemantic.indexer import is_asset_indexed, get_segments_for_asset

    clip, _, _ = _find_clip(clipId)
    filepath = _resolve_filepath(clip)
    asset_id = getattr(clip, "assetId", "")

    # Check storage first
    if asset_id and is_asset_indexed(asset_id):
        cached = get_segments_for_asset(asset_id)
        if cached:
            print(f"[AudioTools] Serving cached transcript for {asset_id[:8]} ({len(cached)} segments)", flush=True)
             
            return {
                "clipId": clipId,
                "filepath": filepath,
                "segments": cached,
                "wordLevel": False,
                "chromaIndexed": len(cached),
                "source": "cache",
            }

    #   Slow path: run Whisper  
    print(f"[AudioTools] Running Whisper for {asset_id[:8] if asset_id else clipId}…", flush=True)
    if words:
        segments = transcribe_with_words(filepath, language=language or None)
    else:
        segments = transcribe(filepath, language=language or None)

    # Save to ChromaDB  
    indexed = _index_transcript(asset_id, segments)

    return {
        "clipId": clipId,
        "filepath": filepath,
        "segments": segments,
        "wordLevel": words,
        "chromaIndexed": indexed,
        "source": "whisper",
    }
