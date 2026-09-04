 
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
                "asset_type": meta.get("asset_type", "video"),
            })
        chunks.sort(key=lambda c: c["start_sec"])
        return chunks
    except Exception:
        return []


def _get_image_description(asset_id: str) -> str:
    """Fetch the stored image description from the image_assets ChromaDB collection."""
    try:
        from backend.ai.VideoSemantic.indexer import _img_col
        result = _img_col.get(where={"assetId": asset_id}, include=["documents"])
        if result["documents"]:
            return result["documents"][0]
    except Exception:
        pass
    return ""


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
                "inPointSec": round(in_pt   / fps, 3),
                "outPointSec": round(out_pt  / fps, 3),
                "fps": fps,
            })
    return clips_info


def _read_file_safe(path: str, max_bytes: int = 8192) -> str:
    """Read a text file, truncating to max_bytes. Returns '' on error."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(max_bytes)
            if len(content) == max_bytes:
                content += "\nâ€¦ [truncated]"
            return content
    except Exception:
        return ""


def _build_clip_description(clip_obj, fps: float = 30.0) -> dict:
     
    from backend.state import _library as _lib

    clip_type = (
        getattr(clip_obj, "CLIP_TYPE", None)
        or getattr(clip_obj, "clipType", None)
        or getattr(clip_obj, "type", "unknown")
    )
    clip_id = getattr(clip_obj, "clipId", "")
    start_f = int(getattr(clip_obj, "startFrame", 0))
    duration_f = int(getattr(clip_obj, "duration", 0))
    start_sec = round(start_f / fps, 3)
    end_sec = round((start_f + duration_f) / fps, 3)

    base = {
        "clipType": clip_type,
        "clipId": clip_id,
        "startFrame": start_f,
        "duration": duration_f,
        "startSec": start_sec,
        "endSec": end_sec,
    }

    if clip_type == "video":
        asset_id = getattr(clip_obj, "assetId", "")
        in_pt_f = int(getattr(clip_obj, "inPoint",  0))
        out_pt_f = int(getattr(clip_obj, "outPoint", duration_f))
        in_sec = round(in_pt_f  / fps, 3)
        out_sec = round(out_pt_f / fps, 3)
        asset = _lib.get(asset_id)
        filepath = getattr(asset, "filepath", "") if asset else ""

        chunks = _get_chroma_chunks(asset_id)
        # Filter  
        if chunks:
            chunks = [c for c in chunks if c["start_sec"] < out_sec and c["end_sec"] > in_sec]

        # Split into vision 
        timeline = []
        for c in chunks:
            entry = {"time_sec": c["start_sec"]}
            txt = c["text"]
            if txt.startswith("Visual:") or " | Speech:" in txt:
                 
                parts = txt.split(" | Speech:")
                entry["scene"] = parts[0].replace("Visual:", "").strip()
                if len(parts) > 1:
                    entry["speech"] = parts[1].strip()
            elif txt.startswith("Speech:"):
                entry["speech"] = txt[7:].strip()
            else:
                entry["scene"] = txt
            timeline.append(entry)

        from backend.worker.transcript_status import is_done as _ts_done
        return {
            **base,
            "assetId": asset_id,
            "filepath": filepath,
            "inPointSec": in_sec,
            "outPointSec": out_sec,
            "transcriptIndexed": _ts_done(asset_id),
            "indexed": len(chunks) > 0,
            "timeline": timeline,
        }

 
    if clip_type == "audio":
        asset_id = getattr(clip_obj, "assetId", "")
        asset = _lib.get(asset_id)
        filepath = getattr(asset, "filepath", "") if asset else ""
        volume = getattr(clip_obj, "volume", 1.0)
        mute = getattr(clip_obj, "mute",   False)

        chunks = _get_chroma_chunks(asset_id)
        transcript = [
            {
                "start_sec": c["start_sec"],
                "end_sec": c["end_sec"],
                "text": c["text"].replace("Speech:", "").strip(),
            }
            for c in chunks
            if c.get("asset_type") == "audio" or c["text"].startswith("Speech:")
        ]

        from backend.worker.transcript_status import is_done as _ts_done
        return {
            **base,
            "assetId": asset_id,
            "filepath": filepath,
            "volume": volume,
            "mute": mute,
            "transcriptIndexed": _ts_done(asset_id),
            "transcript": transcript,
        }

    if clip_type == "image":
        asset_id = getattr(clip_obj, "assetId", "")
        asset = _lib.get(asset_id)
        filepath = getattr(asset, "filepath", "") if asset else ""
        description = _get_image_description(asset_id)
        return {
            **base,
            "assetId": asset_id,
            "filepath": filepath,
            "description": description or "(not yet indexed â€” run vision indexing first)",
            "indexed": bool(description),
        }

    if clip_type == "text":
        style = getattr(clip_obj, "style", None)
        if style:
            style_dict = style.toDict() if hasattr(style, "toDict") else vars(style)
        else:
            style_dict = {}
        return {
            **base,
            "text":  style_dict.get("text", ""),
            "style": {
                k: v for k, v in style_dict.items()
                if k not in ("text",)
            },
        }

    if clip_type in ("shape", "rectangle", "ellipse", "line", "triangle"):
        style = getattr(clip_obj, "style", None)
        style_dict = style.toDict() if (style and hasattr(style, "toDict")) else {}
        return {
            **base,
            "clipType": "shape",
            "shapeType": getattr(clip_obj, "clipType", clip_type),
            "style": style_dict,
        }

    if clip_type == "webcomp":
        webcomp_id = getattr(clip_obj, "webcompId", "")
        asset = _lib.get(webcomp_id)
        folder = getattr(asset, "folderPath", "") if asset else ""
        name = getattr(asset, "name", webcomp_id) if asset else webcomp_id
        runtime_params = getattr(clip_obj, "_runtimeParams", {})

        html = _read_file_safe(os.path.join(folder, "index.html")) if folder else ""
        css  = _read_file_safe(os.path.join(folder, "index.css"))  if folder else ""
        js   = _read_file_safe(os.path.join(folder, "index.js"))   if folder else ""
         
        if not css  and folder: css  = _read_file_safe(os.path.join(folder, "style.css"))
        if not js   and folder: js = _read_file_safe(os.path.join(folder, "script.js"))

        return {
            **base,
            "webcompId": webcomp_id,
            "name": name,
            "folderPath": folder,
            "runtimeParams": runtime_params,
            "html": html,
            "css": css,
            "js": js,
        }

    if clip_type in ("comp", "composition"):
        comp_id = getattr(clip_obj, "compId", "")
        # Find the nested timeline
        nested_tl = None
        if engine.project:
            for tl in engine.project.timelines:
                if getattr(tl, "compId", None) == comp_id or getattr(tl, "id", None) == comp_id:
                    nested_tl = tl
                    break
        nested_summary = []
        if nested_tl:
            nested_fps = float(getattr(nested_tl, "fps", fps))
            for track in getattr(nested_tl, "tracks", []):
                track_info = {
                    "trackName": getattr(track, "name", ""),
                    "clips": [
                        {
                            "clipId": getattr(c, "clipId", ""),
                            "type": getattr(c, "CLIP_TYPE", getattr(c, "clipType", "unknown")),
                            "startFrame": getattr(c, "startFrame", 0),
                            "duration": getattr(c, "duration", 0),
                            "name": getattr(c, "name", ""),
                        }
                        for c in getattr(track, "clips", [])
                    ],
                }
                nested_summary.append(track_info)
        return {
            **base,
            "compId": comp_id,
            "nestedTracks": nested_summary,
        }

 
    if clip_type == "svg":
        filepath = getattr(clip_obj, "filepath", "")
        svg_content = _read_file_safe(filepath, max_bytes=4096) if filepath else ""
        return {
            **base,
            "filepath": filepath,
            "svgPreview": svg_content,
        }

       
    if clip_type in ("pen", "path"):
        path_prop = getattr(clip_obj, "path", None)
        points_count = 0
        if path_prop:
            try:
                points_count = len(path_prop.vertices) if hasattr(path_prop, "vertices") else 0
            except Exception:
                pass
        return {
            **base,
            "pointsCount": points_count,
        }

     
    return {**base, "note": f"No detailed description available for clip type '{clip_type}'."}


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
            lines.append(f"  Timeline: {r['startSec']:.1f}s â€“ {r['endSec']:.1f}s  |  Track: {r['track']}")
            lines.append(f"  Source:   {r['inPointSec']:.1f}s â€“ {r['outPointSec']:.1f}s")
            if not r["context"]["indexed"]:
                lines.append("  [not yet indexed â€” run indexing first]")
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
            f"Timeline position: {clip['startSec']:.1f}s â€“ {clip['endSec']:.1f}s",
            f"Source range: {clip['inPointSec']:.1f}s â€“ {clip['outPointSec']:.1f}s",
            f"Indexed: {ctx['indexed']} ({ctx['semantic_chunks']} chunks, {ctx['transcript_segments']} transcript segments)",
            "",
        ]
        if not ctx["indexed"]:
            lines.append("[Not yet indexed â€” drop this video into the library to start indexing]")
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


 
@router.get("/clip/{clip_id}/describe")
def describe_clip(clip_id: str):
     
    if not engine.project:
        raise HTTPException(404, "No project loaded")

    clip_obj = None
    fps = _FPS_DEFAULT
    for tl in engine.project.timelines:
        tl_fps = float(getattr(tl, "fps", _FPS_DEFAULT))
        for track in tl.tracks:
            for c in track.clips:
                if c.clipId == clip_id:
                    clip_obj = c
                    fps = tl_fps
                    break
            if clip_obj:
                break
        if clip_obj:
            break

    if not clip_obj:
        raise HTTPException(404, f"Clip '{clip_id}' not found in any timeline")

    return _build_clip_description(clip_obj, fps=fps)


@router.get("/selected/describe")
def describe_selected_clip():
     
    import backend.state as _state
    clip_id = getattr(_state, "_selected_clip_id", None)
    if not clip_id:
        raise HTTPException(404, "No clip currently selected")

     
    return describe_clip(clip_id)
