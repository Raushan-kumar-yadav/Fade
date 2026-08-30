 
from __future__ import annotations
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException

from backend.state import engine, _library

router = APIRouter(prefix="/context", tags=["context"])

_FPS_DEFAULT = 30.0
_SEMANTIC_INTERVAL = 2.0   # seconds  


#   helpers  

def _get_chroma_chunks(asset_id: str) -> list[dict]:
     
    try:
        from backend.ai.VideoSemantic.indexer import _col
        result = _col.get(where={"assetId": asset_id}, include=["documents", "metadatas"])
        chunks = []
        for doc, meta in zip(result["documents"], result["metadatas"]):
            chunks.append({
                "start_sec": meta.get("start_sec", 0),
                "end_sec":   meta.get("end_sec",   0),
                "text":      doc,
            })
        chunks.sort(key=lambda c: c["start_sec"])
        return chunks
    except Exception:
        return []


def _get_transcript(asset_id: str, filepath: str) -> list[dict]:
     
    try:
        import httpx, os
        port = int(os.environ.get("BACKEND_PORT", 8000))
        r = httpx.post(
            f"http://127.0.0.1:{port}/ai/transcribe",
            json={"assetId": asset_id, "model": "small", "create_text_clips": False},
            timeout=300,
        )
        if r.status_code == 200:
            segs = r.json().get("segments", [])
            return [{"start": s["start"], "end": s["end"], "text": s["text"].strip()} for s in segs]
    except Exception:
        pass
    return []


def _build_asset_context(asset_id: str, filepath: str, inbound_sec: float = 0.0, outbound_sec: float | None = None) -> dict:
     
    chunks = _get_chroma_chunks(asset_id)
    transcript = _get_transcript(asset_id, filepath)

    # Clip to range if provided
    if outbound_sec is not None:
        chunks     = [c for c in chunks if c["start_sec"] < outbound_sec and c["end_sec"]   > inbound_sec]
        transcript = [t for t in transcript if t["start"] < outbound_sec and t["end"]       > inbound_sec]

    # Build second-by-second timeline 
    all_seconds: set[float] = set()
    for c in chunks:
        all_seconds.add(c["start_sec"])
    for t in transcript:
        all_seconds.add(round(t["start"], 1))

    timeline: list[dict] = []
    for sec in sorted(all_seconds):
        scene_text  = " | ".join(c["text"] for c in chunks     if c["start_sec"] <= sec < c["end_sec"])
        speech_text = " | ".join(t["text"] for t in transcript if t["start"]     <= sec < t["end"])
        if scene_text or speech_text:
            entry: dict = {"time_sec": sec}
            if scene_text:  entry["scene"]  = scene_text
            if speech_text: entry["speech"] = speech_text
            timeline.append(entry)

    return {
        "assetId": asset_id,
        "filepath": filepath,
        "inbound_sec":  inbound_sec,
        "outbound_sec": outbound_sec,
        "semantic_chunks": len(chunks),
        "transcript_segments": len(transcript),
        "indexed": len(chunks) > 0,
        "timeline": timeline,
    }


def _iter_video_clips(tl) -> list[dict]:
    """Walk all tracks and return all video clips with their metadata."""
    clips_info = []
    fps = float(getattr(tl, "fps", _FPS_DEFAULT))
    for track in getattr(tl, "tracks", []):
        for clip in getattr(track, "clips", []):
            clip_type = getattr(clip, "type", "") or getattr(clip, "clipType", "")
            if clip_type not in ("video", "image"):
                continue
            asset_id = getattr(clip, "assetId", "") or getattr(clip, "asset_id", "")
            start_f = int(getattr(clip, "startFrame", 0))
            end_f = int(getattr(clip, "endFrame", 0))
            in_pt = int(getattr(clip, "inPoint", 0))
            out_pt = int(getattr(clip, "outPoint",   end_f - start_f))
            clip_id = getattr(clip, "clipId",  "") or getattr(clip, "id", "")
            filepath  = ""
            asset = _library.get(asset_id)
            if asset:
                filepath = getattr(asset, "filepath", "")
            clips_info.append({
                "clipId": clip_id,
                "assetId": asset_id,
                "filepath": filepath,
                "track": getattr(track, "name", ""),
                "startFrame": start_f,
                "endFrame": end_f,
                "inPoint": in_pt,
                "outPoint": out_pt,
                "startSec": round(start_f / fps, 3),
                "endSec": round(end_f   / fps, 3),
                "inPointSec":   round(in_pt   / fps, 3),
                "outPointSec":  round(out_pt  / fps, 3),
                "fps": fps,
            })
    return clips_info


#   endpoints  

@router.get("/timeline")
def get_timeline_context(format: str = "json"):
     
    tl = engine.activeTimeline
    if not tl:
        raise HTTPException(404, "No active timeline")

    fps = float(getattr(tl, "fps", _FPS_DEFAULT))
    clips = _iter_video_clips(tl)
    results  = []

    for clip in clips:
        if not clip["assetId"] or not clip["filepath"]:
            continue
        ctx = _build_asset_context(
            asset_id = clip["assetId"],
            filepath = clip["filepath"],
            inbound_sec  = clip["inPointSec"],
            outbound_sec = clip["outPointSec"],
        )
        results.append({**clip, "context": ctx})

    if format == "txt":
        lines = ["=== TIMELINE CONTEXT ===", f"FPS: {fps}", ""]
        for r in results:
            lines.append(f"CLIP: {r['clipId']} | {r['filepath']}")
            lines.append(f"  Timeline: {r['startSec']:.1f}s – {r['endSec']:.1f}s  |  Track: {r['track']}")
            lines.append(f"  Source:   {r['inPointSec']:.1f}s – {r['outPointSec']:.1f}s")
            if not r["context"]["indexed"]:
                lines.append("  [not yet indexed — run indexing first]")
            else:
                for entry in r["context"]["timeline"]:
                    ts = f"  [{entry['time_sec']:.1f}s]"
                    if "scene"  in entry: lines.append(f"{ts} SCENE:  {entry['scene']}")
                    if "speech" in entry: lines.append(f"{ts} SPEECH: {entry['speech']}")
            lines.append("")
        return "\n".join(lines)

    return {"fps": fps, "clips": results}


@router.get("/clip/{clip_id}")
def get_clip_context(clip_id: str, format: str = "json"):
     
    tl = engine.activeTimeline
    if not tl:
        raise HTTPException(404, "No active timeline")

    clips = _iter_video_clips(tl)
    clip  = next((c for c in clips if c["clipId"] == clip_id), None)
    if not clip:
        raise HTTPException(404, f"Clip '{clip_id}' not found on timeline")

    if not clip["filepath"]:
        raise HTTPException(422, f"Clip '{clip_id}' has no filepath (asset may be missing)")

    ctx = _build_asset_context(
        asset_id = clip["assetId"],
        filepath = clip["filepath"],
        inbound_sec = clip["inPointSec"],
        outbound_sec = clip["outPointSec"],
    )

    if format == "txt":
        lines = [
            f"CLIP: {clip_id}",
            f"File: {clip['filepath']}",
            f"Timeline position: {clip['startSec']:.1f}s – {clip['endSec']:.1f}s",
            f"Source range: {clip['inPointSec']:.1f}s – {clip['outPointSec']:.1f}s",
            f"Indexed: {ctx['indexed']} ({ctx['semantic_chunks']} chunks, {ctx['transcript_segments']} transcript segments)",
            "",
        ]
        if not ctx["indexed"]:
            lines.append("[Not yet indexed — drop this video into the library to start indexing]")
        else:
            for entry in ctx["timeline"]:
                ts = f"[{entry['time_sec']:.1f}s]"
                if "scene"  in entry: lines.append(f"{ts} SCENE:  {entry['scene']}")
                if "speech" in entry: lines.append(f"{ts} SPEECH: {entry['speech']}")
        return "\n".join(lines)

    return {**clip, "context": ctx}


@router.get("/asset/{asset_id}")
def get_asset_context(asset_id: str, format: str = "json"):
     
    asset = _library.get(asset_id)
    if not asset:
        raise HTTPException(404, f"Asset '{asset_id}' not in library")

    filepath = getattr(asset, "filepath", "")
    ctx = _build_asset_context(asset_id=asset_id, filepath=filepath)

    if format == "txt":
        lines = [
            f"ASSET: {asset_id}",
            f"File: {filepath}",
            f"Indexed: {ctx['indexed']} ({ctx['semantic_chunks']} chunks, {ctx['transcript_segments']} transcript segments)",
            "",
        ]
        if not ctx["indexed"]:
            lines.append("[Not yet indexed]")
        else:
            for entry in ctx["timeline"]:
                ts = f"[{entry['time_sec']:.1f}s]"
                if "scene"  in entry: lines.append(f"{ts} SCENE:  {entry['scene']}")
                if "speech" in entry: lines.append(f"{ts} SPEECH: {entry['speech']}")
        return "\n".join(lines)

    return ctx
