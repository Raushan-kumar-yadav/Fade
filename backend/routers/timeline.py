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

    elif clip_type == "webcomp":
        from backend.timeline.clips.webComp import WebCompClip
        clip = WebCompClip(
            startFrame=body.get("startFrame", 0),
            duration=body.get("duration", 150),
            webcompId=body.get("webcompId", ""),
            mediaOffset=body.get("mediaOffset", 0),
        )

    else:
        clip = VideoClip(startFrame=req.startFrame, duration=req.duration, assetId=req.assetId)
        if engine.scheduler:
            clip.setScheduler(engine.scheduler, engine.project.fps if engine.project else 30.0)
            engine.scheduler.registerClip(clip.clipId, asset)
        clip_type = "video"

    

    from backend.history.commandStack import AddClipCommand
    engine.commandStack.execute(AddClipCommand(track, clip))
    _clipTrackMap[clip.clipId] = req.trackIndex

    if asset.hasAudio:
        try:
            _worker_bus.submit_waveform(req.assetId, asset.filepath)
        except Exception as _e:
            print(f"[addClip] waveform submit error: {_e}", flush=True)

    return {
        "clipId": clip.clipId, "trackId": track.trackId,
        "startFrame": clip.startFrame, "duration": clip.duration,
        "assetId": req.assetId, "type": clip_type, "hasAudio": asset.hasAudio,
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

@router.post("/webcomp/create")
async def createWebcomp(body:dict):
    from backend.media.asset.webCompAsset import webCompAsset
    import shutil

    name = body.get("name","Untitled webCompo")
    template = body.get("template" , "bland")
    project_dir = engine.project.filePath or ""
    project_root = os.path.dirname(project_dir) if project_dir else str(path.home() / ".fade") 

    safe_name = name.lower().replace(" ","-")
    folder = os.path.join(project_root , "webComps" , safe_name)
    os.makedirs(folder , exist_ok=True)

        # Create folder
    safe_name = name.lower().replace(" ", "-")
    folder = os.path.join(project_root, "webcomps", safe_name)
    os.makedirs(folder, exist_ok=True)
    
    # Copy template
    template_dir = os.path.join(os.path.dirname(__file__), "..", "..", "templates", "webcomps", template)
    if os.path.isdir(template_dir):
        shutil.copytree(template_dir, folder, dirs_exist_ok=True)
    else:
        # Create blank files
        _create_blank_webcomp(folder, name)
    
    asset = WebCompAsset(name=name, folderPath=folder)
    asset.saveMeta()
    _library.add(asset)
    
    return {"assetId": asset.assetId, "folderPath": folder, "name": name}


    def _create_blank_webcomp(folder: str, name: str):

         
        with open(os.path.join(folder, "index.html"), "w") as f:
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

        with open(os.path.join(folder, "style.css"), "w") as f:
                    f.write("""* { margin: 0; padding: 0; box-sizing: border-box; }
            body { width: 1920px; height: 1080px; overflow: hidden; background: transparent; }
            #scene { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; }
            .title { font-family: 'Inter', sans-serif; font-size: 72px; color: white; }
            """)

            
        with open(os.path.join(folder, "script.js"), "w") as f:
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