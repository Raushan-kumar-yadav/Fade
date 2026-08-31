import uuid
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.state import engine, _library, _clipTrackMap
from backend.worker.worker_bus import bus as _worker_bus
from backend.timeline.tracks.videoTrack import VideoTrack
from backend.timeline.clips.videoClip import VideoClip
from backend.timeline.clips.audioClip import AudioClip
from backend.history.commandStack import (
    MoveClipCommand, TrimClipCommand, SplitClipCommand,
    RemoveClipCommand,
)

router = APIRouter()


class AddClipRequest(BaseModel):
    assetId: str
    trackIndex: int
    startFrame: int
    duration: int
    mediaOffset: int = 0        
    compId: str | None = None  


class MoveClipRequest(BaseModel):
    clipId: str
    startFrame: int
    trackIndex: int


class TrimClipRequest(BaseModel):
    clipId: str
    side: str
    frameDelta: int


class SplitClipRequest(BaseModel):
    clipId: str
    frame: int


class AddTrackRequest(BaseModel):
    type: str = "video"   # "video" | "audio"
    name: str = ""


@router.post("/timeline/add-track")
def addTrack(req: AddTrackRequest):
    tl = engine.activeTimeline
    if tl is None:
        from fastapi import HTTPException
        raise HTTPException(400, "No active timeline")
    if req.type == "audio":
        from backend.timeline.tracks.audioTrack import AudioTrack
        name = req.name or f"Audio {len(tl.tracks) + 1}"
        track = AudioTrack(name=name)
    else:
        name = req.name or f"Video {len(tl.tracks) + 1}"
        track = VideoTrack(name=name)
    tl.addTrack(track)
    from backend.events import notify; notify("timeline")
    return {"trackId": track.trackId, "name": track.name, "type": req.type}



@router.post("/timeline/add-clip")
def addClip(req: AddClipRequest):
     
    if req.compId:
        tl = engine.getTimeline(req.compId)
        if tl is None:
            raise HTTPException(404, f"Comp timeline {req.compId!r} not found")
    else:
        tl = engine.rootTimeline
        if tl is None:
            raise HTTPException(400, "No active timeline")
    asset = _library.get(req.assetId)
    if asset is None:
        raise HTTPException(404, f"Asset {req.assetId!r} not in library")
    if req.trackIndex >= len(tl.tracks):
        raise HTTPException(400, f"Track index {req.trackIndex} out of range")
    track = tl.tracks[req.trackIndex]

    from backend.media.asset.baseAsset import MediaType
    if asset.mediaType == MediaType.image:
        from backend.timeline.clips.imageClip import ImageClip
        clip = ImageClip(startFrame=req.startFrame, duration=req.duration,
                         assetId=req.assetId, filepath=asset.filepath)
        clip_type = "image"

    elif asset.mediaType == MediaType.webcomp:
        from backend.timeline.clips.webComp import WebCompClip
        clip = WebCompClip(
            startFrame=req.startFrame,
            duration=req.duration,
            webcompId=req.assetId,
            mediaOffset=0,
        )
        clip_type = "webcomp"

    elif asset.mediaType == MediaType.audio:
         
        fps = float(engine.project.fps) if engine.project else 30.0
        actual_dur = req.duration
        try:
            import av as _av
            _c = _av.open(asset.filepath)
            dur_us = _c.duration  # microseconds, or None
            _audio_st = next((s for s in _c.streams if s.type == 'audio'), None)
            if _audio_st and _audio_st.duration is not None and _audio_st.time_base:
                dur_secs = float(_audio_st.duration * _audio_st.time_base)
            elif dur_us:
                dur_secs = dur_us / 1_000_000.0
            else:
                dur_secs = 0.0
            _c.close()
            if dur_secs > 0:
                actual_dur = max(1, int(round(dur_secs * fps)))
                print(f"[addClip] audio duration: {dur_secs:.2f}s → {actual_dur} frames @{fps}fps", flush=True)
        except Exception as _e:
            print(f"[addClip] could not probe audio duration: {_e}", flush=True)
        clip = AudioClip(startFrame=req.startFrame, duration=actual_dur,
                         assetId=req.assetId, mediaOffset=req.mediaOffset)
        clip_type = "audio"

    else:
         
        _AUDIO_EXTS = {".wav", ".mp3", ".aac", ".flac", ".ogg", ".m4a"}
        import os as _os
        if _os.path.splitext(asset.filepath)[1].lower() in _AUDIO_EXTS:
            fps = float(engine.project.fps) if engine.project else 30.0
            actual_dur = req.duration
            try:
                import av as _av
                _c = _av.open(asset.filepath)
                dur_us = _c.duration
                _audio_st = next((s for s in _c.streams if s.type == "audio"), None)
                if _audio_st and _audio_st.duration is not None and _audio_st.time_base:
                    dur_secs = float(_audio_st.duration * _audio_st.time_base)
                elif dur_us:
                    dur_secs = dur_us / 1_000_000.0
                else:
                    dur_secs = 0.0
                _c.close()
                if dur_secs > 0:
                    actual_dur = max(1, int(round(dur_secs * fps)))
            except Exception:
                pass
            clip = AudioClip(startFrame=req.startFrame, duration=actual_dur,
                             assetId=req.assetId, mediaOffset=req.mediaOffset)
            clip_type = "audio"
            print(f"[addClip] Treated audio-extension file as AudioClip: {asset.filepath}", flush=True)
        else:
            clip = VideoClip(startFrame=req.startFrame, duration=req.duration,
                             assetId=req.assetId, mediaOffset=req.mediaOffset)
            if engine.scheduler:
                clip.setScheduler(engine.scheduler, engine.project.fps if engine.project else 30.0)
                engine.scheduler.registerClip(clip.clipId, asset)
            clip_type = "video"
    from backend.history.commandStack import AddClipCommand
    engine.commandStack.execute(AddClipCommand(track, clip))
    _clipTrackMap[clip.clipId] = tl.tracks.index(track)

    # Submit waveform for any clip  
    has_audio = clip_type == 'audio' or (getattr(asset, 'hasAudio', False) and clip_type not in ('webcomp',))
    if has_audio:
        try:
            _worker_bus.submit_waveform(req.assetId, asset.filepath)
        except Exception as _e:
            print(f"[addClip] waveform submit error: {_e}", flush=True)

     
    if clip_type == "audio":
        try:
            import pathlib as _pl
            _AUDIO_EXTS = {".wav", ".mp3", ".aac", ".flac", ".ogg", ".m4a"}
            if _pl.Path(asset.filepath).suffix.lower() in _AUDIO_EXTS:
                from backend.ai.VideoSemantic.indexer import get_db_path as _get_db
                _worker_bus.submit_transcribe_audio(req.assetId, asset.filepath, db_path=_get_db())
        except Exception as _e:
            print(f"[addClip] audio transcript submit error (non-fatal): {_e}", flush=True)

    from backend.events import notify
    notify("timeline")   
    if clip_type == "audio":
         
        notify("render")
    return {
        "clipId": clip.clipId, "trackId": track.trackId,
        "startFrame": clip.startFrame, "duration": clip.duration,
        "assetId": req.assetId, "type": clip_type, "hasAudio": has_audio,
    }



class AddSvgClipRequest(BaseModel):
    filepath: str
    trackIndex: int
    startFrame: int
    duration: int
    displayW: float = 0.0
    displayH: float = 0.0


@router.post("/timeline/add-svg-clip")
def addSvgClip(req: AddSvgClipRequest):
    from backend.timeline.clips.svgClip import SvgClip
    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(400, "No active timeline")
    if not os.path.exists(req.filepath):
        raise HTTPException(404, f"SVG file not found: {req.filepath}")
    if req.trackIndex >= len(tl.tracks):
        raise HTTPException(400, f"Track index {req.trackIndex} out of range")
    track = tl.tracks[req.trackIndex]
    clip = SvgClip(filepath=req.filepath, startFrame=req.startFrame,
                   duration=req.duration, displayW=req.displayW, displayH=req.displayH)
    from backend.history.commandStack import AddClipCommand
    engine.commandStack.execute(AddClipCommand(track, clip))
    _clipTrackMap[clip.clipId] = req.trackIndex
    from backend.events import notify; notify("timeline")
    return {"clipId": clip.clipId, "trackId": track.trackId,
            "startFrame": clip.startFrame, "duration": clip.duration,
            "filepath": clip.filepath, "type": "svg"}


@router.post("/timeline/move-clip")
def moveClip(req: MoveClipRequest):
    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(400, "No active timeline")
    clip = None
    srcIdx = None
    for i, track in enumerate(tl.tracks):
        c = track.getClip(req.clipId)
        if c:
            clip = c
            srcIdx = i
            track.removeClip(req.clipId)
            break
    if clip is None:
        raise HTTPException(404, f"Clip {req.clipId!r} not found")
    dstIdx = max(0, min(len(tl.tracks) - 1, req.trackIndex))
    oldStart = clip.startFrame
    newStart = max(0, req.startFrame)
    engine.commandStack.execute(
        MoveClipCommand(clip, tl.tracks[srcIdx], tl.tracks[dstIdx], oldStart, newStart)
    )
    _clipTrackMap[req.clipId] = dstIdx
    from backend.events import notify; notify("timeline")
    return {"status": "ok"}


@router.delete("/timeline/clips/{clipId}")
def deleteClip(clipId: str):
    timelines = engine.project.timelines if engine.project else []
    if not timelines and engine.activeTimeline:
        timelines = [engine.activeTimeline]
    for tl in timelines:
        for track in tl.tracks:
            clip = track.getClip(clipId)
            if clip:
                engine.commandStack.execute(RemoveClipCommand(track, clip))
                if engine.scheduler:
                    engine.scheduler.unregisterClip(clipId)
                _clipTrackMap.pop(clipId, None)
                from backend.events import notify; notify("timeline")
                return {"status": "ok"}
    raise HTTPException(404, f"Clip {clipId!r} not found")


@router.post("/timeline/trim-clip")
def trimClip(req: TrimClipRequest):
    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(400, "No active timeline")
    for track in tl.tracks:
        clip = track.getClip(req.clipId)
        if clip:
            engine.commandStack.execute(TrimClipCommand(clip, req.side, req.frameDelta))
            track.clips.sort(key=lambda c: c.startFrame)
            from backend.events import notify; notify("timeline")
            return {"clipId": clip.clipId, "startFrame": clip.startFrame, "duration": clip.duration}
    raise HTTPException(404, f"Clip {req.clipId!r} not found")


@router.post("/timeline/split-clip")
def splitClip(req: SplitClipRequest):
    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(400, "No active timeline")
    fps = engine.project.fps if engine.project else 30.0
    for track in tl.tracks:
        clip = track.getClip(req.clipId)
        if clip:
            asset = _library.get(clip.assetId) if clip.assetId else None
            cmd = SplitClipCommand(track, clip, req.frame,
                                   scheduler=engine.scheduler, asset=asset, fps=fps)
            try:
                engine.commandStack.execute(cmd)
            except ValueError as e:
                raise HTTPException(400, str(e))
            right = cmd._rightClip
            trackIndex = tl.tracks.index(track)
            _clipTrackMap[clip.clipId] = trackIndex
            if right:
                _clipTrackMap[right.clipId] = trackIndex
            from backend.events import notify; notify("timeline")
            return {
                "leftClipId": clip.clipId, "rightClipId": right.clipId if right else None,
                "splitFrame": req.frame, "trackId": track.trackId,
            }
    raise HTTPException(404, f"Clip {req.clipId!r} not found")


@router.post("/history/undo")
def undoAction():
    desc = engine.commandStack.undo()
    from backend.events import notify; notify("timeline")
    return {"undone": desc, "canUndo": engine.commandStack.canUndo, "canRedo": engine.commandStack.canRedo}


@router.post("/history/redo")
def redoAction():
    desc = engine.commandStack.redo()
    from backend.events import notify; notify("timeline")
    return {"redone": desc, "canUndo": engine.commandStack.canUndo, "canRedo": engine.commandStack.canRedo}


@router.get("/history/state")
def historyState():
    return {
        "canUndo": engine.commandStack.canUndo,
        "canRedo": engine.commandStack.canRedo,
        "undoLabel": engine.commandStack.undoDescription,
        "redoLabel": engine.commandStack.redoDescription,
    }


@router.post("/timeline/track/{trackId}/mute")
def muteTrack(trackId: str):
    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(400, "No active timeline")
    track = tl.getTrack(trackId)
    if track is None:
        raise HTTPException(404, f"Track {trackId!r} not found")
    track.muted = not track.muted
    return {"trackId": trackId, "muted": track.muted}


@router.post("/timeline/track/{trackId}/solo")
def soloTrack(trackId: str):
    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(400, "No active timeline")
    track = tl.getTrack(trackId)
    if track is None:
        raise HTTPException(404, f"Track {trackId!r} not found")
    target = not getattr(track, 'solo', False)
    for t in tl.tracks:
        t.solo = False
    track.solo = target
    return {"trackId": trackId, "solo": track.solo}


@router.post("/timeline/track/{trackId}/lock")
def lockTrack(trackId: str):
    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(400, "No active timeline")
    track = tl.getTrack(trackId)
    if track is None:
        raise HTTPException(404, f"Track {trackId!r} not found")
    track.locked = not track.locked
    return {"trackId": trackId, "locked": track.locked}


@router.delete("/timeline/track/{trackId}")
def deleteTrack(trackId: str):
    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(400, "No active timeline")
    track = tl.getTrack(trackId)
    if track is None:
        raise HTTPException(404, f"Track {trackId!r} not found")
    tl.removeTrack(trackId)
    from backend.events import notify; notify("timeline")
    return {"removed": trackId}


@router.delete("/timeline/track-by-index/{index}")
def deleteTrackByIndex(index: int):
    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(400, "No active timeline")
    if index < 0 or index >= len(tl.tracks):
        raise HTTPException(
            400,
            f"Track index {index} out of range "
            f"(timeline has {len(tl.tracks)} track(s), indices 0–{len(tl.tracks)-1})"
        )
    removed_id = tl.tracks[index].trackId
    tl.removeTrack(removed_id)
    from backend.events import notify; notify("timeline")
    return {"removed": removed_id, "index": index}


@router.get("/timeline/state")
def timelineState():
    tl  = engine.activeTimeline
    prj = engine.project
    fps = prj.fps if prj else 30.0
    totalFrames = getattr(tl, "totalFrames", None) or (prj.totalFrame if prj else 1800)
    if tl is None:
        return {"tracks": [], "totalFrames": totalFrames, "fps": fps}
    data = tl.toDict()
    data["totalFrames"] = totalFrames
    data["fps"] = getattr(tl, "fps", fps)
    return data

def _runtime_script_tag() -> str:
     
    port = int(os.environ.get("BACKEND_PORT", 8000))
    return f'<script src="http://127.0.0.1:{port}/runtime/fade-react.js"></script>'


def _build_index_html(name: str, css_file: bool = True, html_body: str = "") -> str:
     
    runtime_tag = _runtime_script_tag()
    css_link = '<link rel="stylesheet" href="style.css">' if css_file else ''
    inner = html_body.strip() if html_body.strip() else '<!-- DOM built by script.js -->'
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
{css_link}
{runtime_tag}
</head>
<body>
<div id="scene">
{inner}
</div>
<script src="script.js"></script>
</body>
</html>"""


def _patch_runtime_in_html(content: str) -> str:
    """Fix runtime script references in a template's index.html.

    Replaces ANY src pointing to fade-react.js with the canonical HTTP URL:
      http://127.0.0.1:PORT/runtime/fade-react.js

    Also strips unpkg/jsdelivr CDN scripts and Google Fonts links.
    """
    import re
    port = int(os.environ.get("BACKEND_PORT", 8000))
    correct_url = f"http://127.0.0.1:{port}/runtime/fade-react.js"

    # Replace ANY src pointing to fade-react.js  
    content = re.sub(
        r'src=["\'][^"\']*/fade-react\.js["\']',
        f'src="{correct_url}"',
        content,
    )
    # Strip unpkg / jsdelivr CDN <script> tags entirely
    content = re.sub(
        r'<script[^>]+src=["\']https?://(?:unpkg|cdn\.jsdelivr|cdnjs)[^>]+></script>',
        '',
        content,
        flags=re.IGNORECASE,
    )
    # Strip Google Fonts / preconnect link tags
    content = re.sub(r'<link[^>]+https://fonts\.googleapis[^>]+>', '', content)
    content = re.sub(r'<link[^>]+https://fonts\.gstatic[^>]+>', '', content)
    content = re.sub(r'<link[^>]*preconnect[^>]*href=["\']https?://[^>]+>', '', content)
    return content


def _create_blank_webcomp(folder: str, name: str) -> None:
    """Create minimal blank WebComp files in the given folder."""
    with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as f:
        f.write(_build_index_html(name))

    with open(os.path.join(folder, "style.css"), "w", encoding="utf-8") as f:
        f.write("""* { margin: 0; padding: 0; box-sizing: border-box; }
body { width: 1920px; height: 1080px; overflow: hidden; background: transparent; }
#scene { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; }
.title { font-family: system-ui, sans-serif; font-size: 72px; color: white; }
""")

    with open(os.path.join(folder, "script.js"), "w", encoding="utf-8") as f:
        f.write("""// Fade WebComp — write your animation logic here.
// Globals injected each frame:
//   window.FADE_FRAME  — current frame index (int)
//   window.FADE_TIME   — current time in seconds (float)
//   window.FADE_FPS    — project fps
//   window.FADE_PARAMS — runtime params from the inspector (object)
window.addEventListener('fade:frame', (e) => {
  const { frame, time } = e.detail;
  // TODO: animate
});
window.addEventListener('fade:params', (e) => {
  const params = e.detail;
  // TODO: react to inspector param changes
});
""")



@router.post("/timeline/webcomp/create")
async def createWebcomp(body: dict):
     
    from pathlib import Path
    from backend.media.asset.webCompAsset import WebCompAsset
    import shutil

    name = body.get("name", "Untitled WebComp")
    template  = body.get("template", "blank")
    js_code = body.get("js", "")       # agent animation logic   
    css_code = body.get("css", "")      # agent styles           
    html_body = body.get("html_body", "") # inner DOM snippet only   
    project_dir  = engine.project.filePath or ""
    project_root = os.path.dirname(project_dir) if project_dir else str(Path.home() / ".fade")

    safe_name = name.lower().replace(" ", "-").replace("/", "-")
    webcomps_root = os.path.join(project_root, "webcomps")
    folder = os.path.join(webcomps_root, safe_name)
    os.makedirs(folder, exist_ok=True)

    # Always sync _runtime next to webcomps 
    templates_base = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "templates", "webcomps")
    )
    runtime_src = os.path.join(templates_base, "_runtime")
    if os.path.isdir(runtime_src):
        shutil.copytree(runtime_src, os.path.join(webcomps_root, "_runtime"), dirs_exist_ok=True)

    # Copy template (or blank)
    template_dir = os.path.join(templates_base, template)
    if os.path.isdir(template_dir):
        shutil.copytree(template_dir, folder, dirs_exist_ok=True)
    else:
        _create_blank_webcomp(folder, name)

 
    index_path = os.path.join(folder, "index.html")
    template_was_copied = os.path.isdir(template_dir)

    if template_was_copied and not html_body:
        # Template has its own DOM structure  
        with open(index_path, "r", encoding="utf-8") as f:
            existing = f.read()
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(_patch_runtime_in_html(existing))
    else:
        # Blank comp or agent supplied html_body  
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(_build_index_html(name, html_body=html_body))

    # Write agent-supplied  
    if js_code:
        with open(os.path.join(folder, "script.js"), "w", encoding="utf-8") as f:
            f.write(js_code)
    if css_code:
        with open(os.path.join(folder, "style.css"), "w", encoding="utf-8") as f:
            f.write(css_code)

    proj  = engine.project
    asset = WebCompAsset(
        name=name,
        folderPath=folder,
        width=proj.width if proj else 1920,
        height=proj.height if proj else 1080,
        fps=proj.fps if proj else 30.0,
    )
    asset._loadMeta()
    asset.saveMeta()
    _library[asset.assetId] = asset

    from backend.events import notify; notify("webcomps")
    return {
        "assetId": asset.assetId,
        "name": asset.name,
        "folderPath": folder,
        "width": asset.width,
        "height": asset.height,
        "fps": asset.fps,
        "durationFrames": asset.durationFrames,
    }


@router.get("/timeline/webcomp/templates")
async def listWebcompTemplates():
    """Scan templates/webcomps directory and return available templates."""
    import json as _json
    templates_dir = os.path.join(os.path.dirname(__file__), "..", "..", "templates", "webcomps")
    templates_dir = os.path.normpath(templates_dir)
    results = []
    if not os.path.isdir(templates_dir):
        return {"templates": results}
    for entry in sorted(os.listdir(templates_dir)):
        folder = os.path.join(templates_dir, entry)
        if not os.path.isdir(folder):
            continue
        meta_path = os.path.join(folder, "webcomp.json")
        if not os.path.isfile(meta_path):
            continue
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = _json.load(f)
        except Exception:
            meta = {}
        results.append({
            "id": entry,
            "name": meta.get("name", entry.replace("-", " ").title()),
            "description":   meta.get("description",   ""),
            "width": meta.get("width", 1920),
            "height": meta.get("height", 1080),
            "fps": meta.get("fps", 30),
            "durationFrames":meta.get("durationFrames", 150),
            "params": meta.get("params", []),
        })
    return {"templates": results}



@router.post("/timeline/webcomp/read-file")
async def readWebcompFile(body: dict):
     
    webcomp_id = body.get("webcompId", "")
    filename   = body.get("filename", "")
    asset = _library.get(webcomp_id)
    if not asset or not hasattr(asset, "folderPath"):
        raise HTTPException(404, f"WebComp {webcomp_id!r} not found")
    filepath = os.path.join(asset.folderPath, filename)
    if not os.path.isfile(filepath):
        raise HTTPException(404, f"File not found in WebComp: {filename}")
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    return {"content": content, "filename": filename}


@router.post("/timeline/webcomp/write-file")
async def writeWebcompFile(body: dict):
    
    webcomp_id = body.get("webcompId", "")
    filename = body.get("filename", "")
    content = body.get("content", "")
    asset = _library.get(webcomp_id)
    if not asset or not hasattr(asset, "folderPath"):
        raise HTTPException(404, "WebComp not found")
    # Auto-patch index.html  
    if filename == "index.html":
        content = _patch_runtime_in_html(content)
    filepath = os.path.join(asset.folderPath, filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    from backend.events import notify; notify("webcomps")
    return {"ok": True, "filename": filename}


@router.get("/timeline/webcomp/list")
async def listWebcomps():
     
    from backend.media.asset.baseAsset import MediaType
    result = []
    for asset_id, asset in _library.items():
        if getattr(asset, "mediaType", None) == MediaType.webcomp:
            result.append({
                "assetId": asset.assetId,
                "name": asset.name,
                "folderPath": getattr(asset, "folderPath", ""),
                "width": getattr(asset, "width", 1920),
                "height": getattr(asset, "height", 1080),
                "fps": getattr(asset, "fps", 30.0),
                "durationFrames": getattr(asset, "durationFrames", 150),
            })
    return {"webcomps": result}


@router.get("/timeline/webcomp/clip-info")
async def getWebcompClipInfo(clipId: str = ""):
    """Return WebComp clip info + meta + param schema for the inspector panel."""
    import json
    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(400, "No active timeline")

    # Find clip across all tracks
    clip = None
    for track in tl.tracks:
        for c in track.clips:
            if c.clipId == clipId:
                clip = c
                break
        if clip:
            break

    if clip is None:
        raise HTTPException(404, f"Clip {clipId!r} not found")

    if not hasattr(clip, "webcompId"):
        raise HTTPException(400, "Clip is not a WebComp")

    asset = _library.get(clip.webcompId)
    meta = None
    params_schema = []

    if asset:
        meta = {
            "assetId": asset.assetId,
            "name": asset.name,
            "folderPath": getattr(asset, "folderPath", ""),
            "width": getattr(asset, "width", 1920),
            "height": getattr(asset, "height", 1080),
            "fps": getattr(asset, "fps", 30.0),
            "durationFrames": getattr(asset, "durationFrames", 150),
        }
        # Read param schema from webcomp.json
        folder = getattr(asset, "folderPath", "")
        webcomp_json = os.path.join(folder, "webcomp.json")
        if os.path.isfile(webcomp_json):
            try:
                with open(webcomp_json, "r", encoding="utf-8") as f:
                    wc_data = json.load(f)
                params_schema = wc_data.get("params", [])
            except Exception:
                params_schema = []

    # Read current transform values
    t = clip.transform
    tx, ty = t.position.get() if hasattr(t.position, 'get') else (getattr(t, 'x', 0.0), getattr(t, 'y', 0.0))
    sx, sy = t.scale.get() if hasattr(t.scale, 'get') else (getattr(t, 'scaleX', 1.0), getattr(t, 'scaleY', 1.0))
    rot = t.rotation.get() if hasattr(t.rotation,  'get') else getattr(t, 'rotation', 0.0)
    op = t.opacity.get() if hasattr(t.opacity, 'get') else getattr(t, 'opacity', 1.0)
    ax, ay = t.anchor.get() if hasattr(t.anchor, 'get') else (getattr(t, 'anchorX', 0.0), getattr(t, 'anchorY', 0.0))

    return {
        "webcompId":    clip.webcompId,
        "mediaOffset":  getattr(clip, "mediaOffset", 0),
        "runtimeParams": getattr(clip, "_runtimeParams", {}),
        "meta": meta,
        "params": params_schema,
        "transform": {
            "x": tx, "y": ty,
            "scaleX":  sx, "scaleY":  sy,
            "rotation": rot,
            "anchorX": ax, "anchorY": ay,
        },
        "opacity": op,
    }


@router.post("/timeline/webcomp/runtime-params")
async def setWebcompRuntimeParams(body: dict):
    """Update runtime params on a WebComp clip."""
    clip_id = body.get("clipId", "")
    params = body.get("params", {})
    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(400, "No active timeline")
    clip = None
    for track in tl.tracks:
        for c in track.clips:
            if c.clipId == clip_id:
                clip = c
                break
        if clip:
            break
    if clip is None:
        raise HTTPException(404, f"Clip {clip_id!r} not found")
    if not hasattr(clip, "_runtimeParams"):
        raise HTTPException(400, "Clip is not a WebComp")
    clip._runtimeParams.update(params)
    from backend.events import notify; notify("timeline")
    return {"ok": True, "runtimeParams": clip._runtimeParams}


def _find_clip(clip_id: str):
    tl = engine.activeTimeline
    if tl is None:
        return None
    for track in tl.tracks:
        for c in track.clips:
            if c.clipId == clip_id:
                return c
    return None


@router.post("/timeline/webcomp/transform")
async def setWebcompTransform(body: dict):
    """Update position / scale / rotation / anchor on a WebComp clip."""
    clip = _find_clip(body.get("clipId", ""))
    if clip is None:
        raise HTTPException(404, "Clip not found")
    t = clip.transform
    cur_pos = t.position.get()
    cur_scale = t.scale.get()
    cur_anchor = t.anchor.get()
    if "x" in body or "y"       in body:
        t.position.setBase(float(body.get("x", cur_pos[0])), float(body.get("y", cur_pos[1])))
    if "scaleX" in body or "scaleY"  in body:
        t.scale.setBase(float(body.get("scaleX", cur_scale[0])), float(body.get("scaleY", cur_scale[1])))
    if "rotation" in body:
        t.rotation.setBaseValue(float(body["rotation"]))
    if "anchorX"  in body or "anchorY" in body:
        t.anchor.setBase(float(body.get("anchorX", cur_anchor[0])), float(body.get("anchorY", cur_anchor[1])))
    return {"ok": True}


@router.post("/timeline/webcomp/opacity")
async def setWebcompOpacity(body: dict):
    """Update opacity on a WebComp clip."""
    clip = _find_clip(body.get("clipId", ""))
    if clip is None:
        raise HTTPException(404, "Clip not found")
    clip.transform.opacity.setBaseValue(float(body.get("opacity", 1.0)))
    return {"ok": True}


@router.delete("/timeline/webcomp/{webcomp_id}")
async def deleteWebcomp(webcomp_id: str):
    """Remove a WebComp asset from the library."""
    if webcomp_id not in _library:
        raise HTTPException(404, f"WebComp {webcomp_id!r} not found")
    del _library[webcomp_id]
    from backend.events import notify; notify("webcomps")
    return {"ok": True}


@router.post("/timeline/webcomp/reload")
async def reloadWebcomp(body: dict):
    """Force-reload a WebComp's Electron BrowserWindow and clear its frame cache."""
    webcomp_id = body.get("webcompId", "")
    if not webcomp_id or webcomp_id not in _library:
        raise HTTPException(404, f"WebComp {webcomp_id!r} not found")
   
    if engine:
        try:
            engine.reloadWebComp(webcomp_id)
        except Exception:
            pass   
    return {"ok": True, "webcompId": webcomp_id}


@router.post("/timeline/webcomp/update-meta")
async def updateWebcompMeta(body: dict):
    """Update name/dimensions/fps/durationFrames on a WebComp asset."""
    webcomp_id = body.get("webcompId", "")
    if not webcomp_id or webcomp_id not in _library:
        raise HTTPException(404, f"WebComp {webcomp_id!r} not found")

    asset = _library[webcomp_id]

    if body.get("name"): asset.name = body["name"]
    if body.get("width"): asset.width = int(body["width"])
    if body.get("height"): asset.height = int(body["height"])
    if body.get("fps"): asset.fps = float(body["fps"])
    if body.get("durationFrames"): asset.durationFrames = int(body["durationFrames"])

    # Persist to webcomp.json on disk
    folder = getattr(asset, "folderPath", "")
    if folder:
        import json as _json
        wc_json_path = os.path.join(folder, "webcomp.json")
        meta: dict = {}
        if os.path.isfile(wc_json_path):
            try:
                with open(wc_json_path, "r", encoding="utf-8") as f:
                    meta = _json.load(f)
            except Exception:
                meta = {}
        meta["name"] = asset.name
        meta["width"] = getattr(asset, "width", 1920)
        meta["height"] = getattr(asset, "height", 1080)
        meta["fps"] = getattr(asset, "fps", 30)
        meta["durationFrames"] = getattr(asset, "durationFrames", 150)
        try:
            with open(wc_json_path, "w", encoding="utf-8") as f:
                _json.dump(meta, f, indent=2)
        except Exception:
            pass

    return {"ok": True, "webcompId": webcomp_id, "name": asset.name}