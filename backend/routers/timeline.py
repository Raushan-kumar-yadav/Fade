import uuid
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.state import engine, _library, _clipTrackMap
from backend.worker.worker_bus import bus as _worker_bus
from backend.timeline.tracks.videoTrack import VideoTrack
from backend.timeline.tracks.audioTrack import AudioTrack
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


@router.post("/timeline/add-clip")
def addClip(req: AddClipRequest):
    tl = engine.activeTimeline
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

    else:
        clip = VideoClip(startFrame=req.startFrame, duration=req.duration, assetId=req.assetId)
        if engine.scheduler:
            clip.setScheduler(engine.scheduler, engine.project.fps if engine.project else 30.0)
            engine.scheduler.registerClip(clip.clipId, asset)
        clip_type = "video"

    

    from backend.history.commandStack import AddClipCommand
    engine.commandStack.execute(AddClipCommand(track, clip))
    _clipTrackMap[clip.clipId] = req.trackIndex

    has_audio = getattr(asset, 'hasAudio', False) and clip_type != 'webcomp'
    if has_audio:
        try:
            _worker_bus.submit_waveform(req.assetId, asset.filepath)
        except Exception as _e:
            print(f"[addClip] waveform submit error: {_e}", flush=True)

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
    dstIdx   = max(0, min(len(tl.tracks) - 1, req.trackIndex))
    oldStart = clip.startFrame
    newStart = max(0, req.startFrame)
    engine.commandStack.execute(
        MoveClipCommand(clip, tl.tracks[srcIdx], tl.tracks[dstIdx], oldStart, newStart)
    )
    _clipTrackMap[req.clipId] = dstIdx
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
            return {
                "leftClipId": clip.clipId, "rightClipId": right.clipId if right else None,
                "splitFrame": req.frame, "trackId": track.trackId,
            }
    raise HTTPException(404, f"Clip {req.clipId!r} not found")


@router.post("/history/undo")
def undoAction():
    desc = engine.commandStack.undo()
    return {"undone": desc, "canUndo": engine.commandStack.canUndo, "canRedo": engine.commandStack.canRedo}


@router.post("/history/redo")
def redoAction():
    desc = engine.commandStack.redo()
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

def _create_blank_webcomp(folder: str, name: str) -> None:
    """Create minimal blank WebComp files in the given folder."""
    with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as f:
        f.write(f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<link rel="stylesheet" href="style.css">
</head><body>
<div id="scene">
  <h1 class="title">{name}</h1>
</div>
<script src="script.js"></script>
</body></html>""")

    with open(os.path.join(folder, "style.css"), "w", encoding="utf-8") as f:
        f.write("""* { margin: 0; padding: 0; box-sizing: border-box; }
body { width: 1920px; height: 1080px; overflow: hidden; background: transparent; }
#scene { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; }
.title { font-family: 'Inter', sans-serif; font-size: 72px; color: white; }
""")

    with open(os.path.join(folder, "script.js"), "w", encoding="utf-8") as f:
        f.write("""// Fade WebComp
// Globals: window.FADE_FRAME, window.FADE_TIME, window.FADE_FPS, window.FADE_PARAMS
window.addEventListener('fade:frame', (e) => {
  const { frame, time } = e.detail;
  // Animate here based on frame/time
});
window.addEventListener('fade:params', (e) => {
  const params = e.detail;
  // React to param changes here
});
""")


@router.post("/timeline/webcomp/create")
async def createWebcomp(body: dict):
    """Create a new WebComp asset (folder on disk with HTML/CSS/JS)."""
    from pathlib import Path
    from backend.media.asset.webCompAsset import WebCompAsset
    import shutil

    name = body.get("name", "Untitled WebComp")
    template = body.get("template", "blank")
    project_dir = engine.project.filePath or ""
    project_root = os.path.dirname(project_dir) if project_dir else str(Path.home() / ".fade")

    safe_name = name.lower().replace(" ", "-").replace("/", "-")
    folder = os.path.join(project_root, "webcomps", safe_name)
    os.makedirs(folder, exist_ok=True)

    # Copy template if it exists
    template_dir = os.path.join(os.path.dirname(__file__), "..", "..", "templates", "webcomps", template)
    if os.path.isdir(template_dir):
        shutil.copytree(template_dir, folder, dirs_exist_ok=True)
    else:
        _create_blank_webcomp(folder, name)

    proj = engine.project
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
            "id":            entry,
            "name":          meta.get("name",          entry.replace("-", " ").title()),
            "description":   meta.get("description",   ""),
            "width":         meta.get("width",          1920),
            "height":        meta.get("height",         1080),
            "fps":           meta.get("fps",            30),
            "durationFrames":meta.get("durationFrames", 150),
            "params":        meta.get("params",         []),
        })
    return {"templates": results}



@router.post("/timeline/webcomp/read-file")
async def readWebcompFile(webcompId: str = "", filename: str = ""):
    """Read a file from a WebComp folder."""
    asset = _library.get(webcompId)
    if not asset or not hasattr(asset, "folderPath"):
        raise HTTPException(404, "WebComp not found")
    filepath = os.path.join(asset.folderPath, filename)
    if not os.path.isfile(filepath):
        raise HTTPException(404, f"File not found: {filename}")
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    return {"content": content, "filename": filename}


@router.post("/timeline/webcomp/write-file")
async def writeWebcompFile(body: dict):
    """Write a file to a WebComp folder."""
    webcomp_id = body.get("webcompId", "")
    filename = body.get("filename", "")
    content = body.get("content", "")
    asset = _library.get(webcomp_id)
    if not asset or not hasattr(asset, "folderPath"):
        raise HTTPException(404, "WebComp not found")
    filepath = os.path.join(asset.folderPath, filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return {"ok": True, "filename": filename}


@router.get("/timeline/webcomp/list")
async def listWebcomps():
    """List all WebComp assets in the library."""
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
    sx, sy = t.scale.get()    if hasattr(t.scale,    'get') else (getattr(t, 'scaleX', 1.0), getattr(t, 'scaleY', 1.0))
    rot    = t.rotation.get() if hasattr(t.rotation,  'get') else getattr(t, 'rotation', 0.0)
    op     = t.opacity.get()  if hasattr(t.opacity,   'get') else getattr(t, 'opacity', 1.0)
    ax, ay = t.anchor.get()   if hasattr(t.anchor,    'get') else (getattr(t, 'anchorX', 0.0), getattr(t, 'anchorY', 0.0))

    return {
        "webcompId":    clip.webcompId,
        "mediaOffset":  getattr(clip, "mediaOffset", 0),
        "runtimeParams": getattr(clip, "_runtimeParams", {}),
        "meta":         meta,
        "params":       params_schema,
        "transform": {
            "x":       tx,       "y":       ty,
            "scaleX":  sx,       "scaleY":  sy,
            "rotation": rot,
            "anchorX": ax,       "anchorY": ay,
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
    if "x"        in body or "y"       in body:
        t.position.setBase(float(body.get("x", cur_pos[0])), float(body.get("y", cur_pos[1])))
    if "scaleX"   in body or "scaleY"  in body:
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
    return {"ok": True}