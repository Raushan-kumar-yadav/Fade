import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.state import engine, _clipTrackMap
from backend.timeline.tracks.videoTrack import VideoTrack
from backend.timeline.tracks.audioTrack import AudioTrack

router = APIRouter()


def _comp_clips_in_timeline(tl) -> list[str]:
    from backend.timeline.clips.compClip import CompClip
    return [clip.compId for track in tl.tracks for clip in track.clips if isinstance(clip, CompClip)]


def _has_cycle(start_id: str, target_id: str, visited: set | None = None) -> bool:
    if visited is None:
        visited = set()
    if start_id == target_id:
        return True
    if start_id in visited:
        return False
    visited.add(start_id)
    tl = engine.getTimeline(start_id)
    if tl is None:
        return False
    for child_id in _comp_clips_in_timeline(tl):
        if _has_cycle(child_id, target_id, visited):
            return True
    return False


def _ensure_comp_tracks(tl) -> None:
    if tl.tracks:
        return
    is_image = getattr(tl, "kind", "video") == "image"
    first_name = "Layer 1" if is_image else "Video 1"
    tl.tracks.append(VideoTrack(name=first_name))
    # Image comps are purely visual — no audio track
    if not is_image:
        tl.tracks.append(AudioTrack(name="Audio 1"))


def _active_timeline():
    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(400, "No active timeline")
    return tl


def _top_empty_track(startFrame: int, duration: int):
    tl = _active_timeline()
    endFrame = startFrame + duration
    video_tracks = [t for t in tl.tracks if not getattr(t, 'isAudio', lambda: False)()]
    for track in reversed(video_tracks):
        overlaps = any(
            not (clip.startFrame >= endFrame or clip.startFrame + clip.duration <= startFrame)
            for clip in getattr(track, 'clips', [])
        )
        if not overlaps:
            return track
    is_image = getattr(tl, "kind", "video") == "image"
    prefix = "Layer" if is_image else "Video"
    new_track = VideoTrack(f"{prefix} {len(video_tracks) + 1}")
    tl.addTrack(new_track)
    return new_track


class CreateCompRequest(BaseModel):
    name: str = "Composition"
    width: int = 1920
    height: int = 1080
    fps: float = 30.0
    totalFrames: int = 900
    kind: str = "video"
    isHidden: bool = False   # hides comp from library (e.g. PDF page comps)
    isDefault: bool = False  # marks as the workspace default comp


class CompRenameRequest(BaseModel):
    name: str


class AddCompClipRequest(BaseModel):
    compId: str
    trackIndex: int | None = None
    startFrame: int = 0
    duration: int = 90
    mediaOffset: int = 0


@router.get("/comps")
def listComps():
    if engine.project is None:
        return {"comps": []}

    # ── One-time retroactive migration ────────────────────────────────────────
    # 1. Collect all page_ids owned by PDF docs → those image comps must be hidden.
    pdf_page_ids: set[str] = set()
    for tl in engine.project.timelines:
        if getattr(tl, "kind", "video") == "pdf":
            for pid in getattr(tl, "page_ids", []):
                pdf_page_ids.add(pid)

    # 2. Apply isHidden to page comps; deduplicate isDefault per kind.
    seen_default: set[str] = set()
    for tl in engine.project.timelines:
        kind = getattr(tl, "kind", "video")
        # Hide PDF page comps
        if tl.timelineId in pdf_page_ids:
            tl.isHidden = True
        # Ensure only one isDefault per kind
        if getattr(tl, "isDefault", False):
            if kind in seen_default:
                tl.isDefault = False   # strip duplicate
            else:
                seen_default.add(kind)
    # ─────────────────────────────────────────────────────────────────────────

    root_id  = engine.project.timelines[0].timelineId if engine.project.timelines else ""
    proj_w   = engine.project.width
    proj_h   = engine.project.height
    proj_fps = engine.project.fps
    comps = []
    for tl in engine.project.timelines:
        comps.append({
            "compId": tl.timelineId,
            "name": tl.name,
            "kind": getattr(tl, "kind", "video"),
            "isRoot": tl.timelineId == root_id,
            "isHidden": getattr(tl, "isHidden", False),
            "isDefault": getattr(tl, "isDefault", False),
            "width": getattr(tl, "width", proj_w),
            "height": getattr(tl, "height", proj_h),
            "fps": getattr(tl, "fps", proj_fps),
            "totalFrames": getattr(tl, "totalFrames", 900),
            "trackCount": len(tl.tracks),
            "clipCount": sum(len(t.clips) for t in tl.tracks),
        })
    return {"comps": comps}



@router.post("/comps")
def createComp(req: CreateCompRequest):
    if engine.project is None:
        raise HTTPException(400, "No active project")

    # If caller wants a default comp, return an existing one for that kind
    # instead of creating a duplicate.
    if req.isDefault and engine.project is not None:
        for tl in engine.project.timelines:
            if getattr(tl, "kind", "video") == req.kind and getattr(tl, "isDefault", False):
                return {
                    "compId": tl.timelineId, "name": tl.name,
                    "kind": tl.kind,
                    "isHidden": getattr(tl, "isHidden", False),
                    "isDefault": True,
                    "width": getattr(tl, "width", req.width),
                    "height": getattr(tl, "height", req.height),
                    "fps": getattr(tl, "fps", req.fps),
                    "totalFrames": getattr(tl, "totalFrames", req.totalFrames),
                    "isRoot": False, "trackCount": len(tl.tracks),
                    "clipCount": sum(len(t.clips) for t in tl.tracks),
                }

    comp = engine.createComposition(name=req.name, width=req.width, height=req.height,
                                    fps=req.fps, total_frames=req.totalFrames)
    comp.kind = req.kind
    comp.isHidden = req.isHidden
    comp.isDefault = req.isDefault
    from backend.events import notify; notify("comps")
    return {
        "compId": comp.timelineId, "name": comp.name,
        "kind": comp.kind,
        "isHidden": comp.isHidden,
        "isDefault": comp.isDefault,
        "width": getattr(comp, "width", req.width),
        "height": getattr(comp, "height", req.height),
        "fps": getattr(comp, "fps", req.fps),
        "totalFrames": getattr(comp, "totalFrames", req.totalFrames),
        "isRoot": False, "trackCount": 0, "clipCount": 0,
    }


@router.delete("/comps/{compId}")
def deleteComp(compId: str):
    ok = engine.deleteComposition(compId)
    if not ok:
        raise HTTPException(404, f"Composition {compId!r} not found or is root")
    from backend.events import notify; notify("comps")
    return {"status": "ok"}


@router.patch("/comps/{compId}/rename")
def renameCompRoute(compId: str, req: CompRenameRequest):
    tl = engine.getTimeline(compId)
    if tl is None:
        raise HTTPException(404, f"Composition {compId!r} not found")
    name = req.name.strip()
    if not name:
        raise HTTPException(400, "Name cannot be empty")
    tl.name = name
    from backend.events import notify; notify("comps")
    return {"compId": compId, "name": name}


@router.post("/comps/{compId}/activate")
def activateComp(compId: str):
    if engine.project is None:
        raise HTTPException(400, "No active project")
    if compId == "root":
        engine.setActiveComp(None)
        root = engine.project.timelines[0] if engine.project.timelines else None
        # Restore project-level dimensions
        if engine.compositor and engine.project:
            engine.compositor.resize(int(engine.project.width), int(engine.project.height))
        from backend.routers.render import _bust_frame_cache
        _bust_frame_cache()
        from backend.events import notify
        notify("comp-resized", {
            "compId": root.timelineId if root else None,
            "width": int(engine.project.width),
            "height": int(engine.project.height),
            "fps": float(getattr(root, 'fps', engine.project.fps) if root else engine.project.fps),
        })
        return {"activeCompId": root.timelineId if root else None,
                "width": int(engine.project.width), "height": int(engine.project.height),
                "fps": float(getattr(root, 'fps', engine.project.fps) if root else engine.project.fps)}
    tl = engine.getTimeline(compId)
    if tl is None:
        raise HTTPException(404, f"Composition {compId!r} not found")
    engine.setActiveComp(compId)
     
    comp_w = int(getattr(tl, "width",  engine.project.width  if engine.project else 1920))
    comp_h = int(getattr(tl, "height", engine.project.height if engine.project else 1080))
    if engine.compositor:
        engine.compositor.resize(comp_w, comp_h)
     
    # Rename "Video N" tracks to "Layer N" for image comps (migration for old comps)
    if getattr(tl, "kind", "video") == "image":
        import re as _re
        video_tracks = [t for t in tl.tracks if not getattr(t, "_is_audio", False)]
        for idx, track in enumerate(video_tracks, start=1):
            if _re.fullmatch(r"Video\s+\d+", track.name):
                track.name = f"Layer {idx}"
        from backend.events import notify as _n; _n("timeline")

    from backend.routers.render import _bust_frame_cache
    _bust_frame_cache()
    from backend.events import notify
    comp_fps = float(getattr(tl, 'fps', 30))
    notify("comp-resized", {"compId": compId, "width": comp_w, "height": comp_h, "fps": comp_fps})
    return {"activeCompId": compId, "width": comp_w, "height": comp_h, "fps": comp_fps}


@router.post("/comps/{compId}/ensure-tracks")
def ensureCompTracks(compId: str):
    tl = engine.getTimeline(compId)
    if tl is None:
        raise HTTPException(404, f"Composition {compId!r} not found")
    _ensure_comp_tracks(tl)
    return {"trackCount": len(tl.tracks)}


@router.get("/comps/{compId}/state")
def getCompState(compId: str):
    tl = engine.getTimeline(compId)
    if tl is None:
        raise HTTPException(404, f"Composition {compId!r} not found")
    _ensure_comp_tracks(tl)
    comp_fps   = getattr(tl, "fps", engine.project.fps if engine.project else 30.0)
    comp_total = getattr(tl, "totalFrames", None) or max(
        (max((c.startFrame + c.duration for c in t.clips), default=0) for t in tl.tracks),
        default=900
    )
    tracks_out = []
    for track in tl.tracks:
        clips_out = []
        for clip in track.clips:
            clips_out.append({
                "clipId": getattr(clip, "clipId", ""),
                "type": getattr(clip, "CLIP_TYPE", getattr(clip, "clipType", "video")),
                "name": getattr(clip, "name", getattr(clip, "compId", getattr(clip, "assetId", "Clip"))),
                "startFrame": getattr(clip, "startFrame", 0),
                "duration": getattr(clip, "duration", 90),
                "assetId": getattr(clip, "assetId", None),
                "compId": getattr(clip, "compId", None),
            })
        tracks_out.append({
            "trackId": track.trackId, "name": track.name,
            "type": getattr(track, "TRACK_TYPE", "video"),
            "muted": track.muted,
            "solo": getattr(track, "solo", False),
            "locked": track.locked,
            "clips": clips_out,
        })
    return {"timelineId": tl.timelineId, "name": tl.name,
            "tracks": tracks_out, "totalFrames": comp_total, "fps": comp_fps}


@router.post("/clips/comp")
def addCompClip(req: AddCompClipRequest):
    from backend.timeline.clips.compClip import CompClip
    if engine.project is None:
        raise HTTPException(400, "No active project")
    tl = _active_timeline()
    if req.compId == tl.timelineId:
        raise HTTPException(400, "Cannot add a composition inside itself")
    if _has_cycle(req.compId, tl.timelineId):
        raise HTTPException(400, f"Cycle detected")
    track = _top_empty_track(req.startFrame, req.duration)
    if req.trackIndex is not None and 0 <= req.trackIndex < len(tl.tracks):
        track = tl.tracks[req.trackIndex]
    clip = CompClip(clipId=str(uuid.uuid4()), startFrame=req.startFrame,
                    duration=req.duration, compId=req.compId, mediaOffset=req.mediaOffset)
    track.addClip(clip)
    _clipTrackMap[clip.clipId] = tl.tracks.index(track)
    from backend.events import notify; notify("timeline")
    return clip.toDict()



class AddLayerRequest(BaseModel):
    name:str = "Layer"
    element:dict | None = None


class UpdateLayerRequest(BaseModel):
    name:str | None = None
    visible : bool | None = None
    locked : bool | None = None 
    opacity : float | None = None
    blendMode : str | None = None
    z_index : int | None = None
    element : dict | None = None


class ReorderLayerRequest(BaseModel):
    layerIds : list[str]


@router.get("/comps/{compId}/layers")
def getLayers(compId : str):
    from backend.timeline.tracks.imageLayer import imageLayer
    tl = engine.getTimeline(compId)
    if tl is None:
        raise HTTPException(404,f"comp {CompId!r} not found")

    if getattr(tl ,  "kind","video") != "image":
        raise HTTPException(400, "Not an image compositor")

    layers = sorted([t for t in tl.tracks if isinstance(t , imageLayer)],
    key=lambda l : l.z_index , reverse=True
    )
    return {"layers":[l.toDict() for l in layers]}

@router.post("/comp/{compId}/layers")
def addLayer(compId:str , req:AddLayerRequest):
    from backend.timeline.tracks.imageLayer import imageLayer
    t1 = engine.getTimeline(compId)
    if t1 is None:
        raise HTTPException(404,f"Comp {compId!r} not found ") 
    
    if getattr(t1 , "kind" , "video") != "image":
        raise HTTPException(400 , "not an image composition")

    lyr = imageLayer(name=req.name)
    lyr.zIndex = len(t1.tracks)
    lyr.element = req.element
    t1.tracks(lyr)
    from backend.events import notify ; notify("timeline")
    return lyr.toDict()

@router.patch('/comps/{compId}/layers/{layerId}')
def updateLayer(compId:str , layerId:str , req:UpdateLayerRequest):
    from backend.timeline.tracks.imageLayer import imageLayer 
    t1 = engine.getTimeline(compId)

    if t1 is None:
        raise HTTPException(404 , f"comp {compId!r} not found")
    
    lyr = next((t for t in t1.tracks if isinstance(t , imageLayer) and (t.trackId == layerId)) , None )

    if lyr is None:
        raise HTTPException(404 , f"Layer {layerId!r} not found ")

    if req.name is not None: lyr.name = req.name
    if req.visible is not None: lyr.visible = req.visible
    if req.locked is not None: lyr.locked = req.locked
    if req.opacity is not None: lyr.opacity = req.opacity
    if req.blendMode is not None: lyr.blendMode = req.blendMode
    if req.z_index is not None: lyr.z_index = req.z_index
    if req.element is not None: lyr.element = req.element
    from backend.events import notify; notify("timeline")
    return lyr.toDict()


class MoveLayerRequest(BaseModel):
    fromIndex: int
    toIndex: int


@router.post("/comps/{compId}/layers/move")
def moveLayer(compId: str, req: MoveLayerRequest):
    """Reorder image comp layers by swapping two track positions."""
    from backend.timeline.tracks.imageLayer import imageLayer
    tl = engine.getTimeline(compId)
    if tl is None:
        raise HTTPException(404, f"comp {compId!r} not found")
    if getattr(tl, "kind", "video") != "image":
        raise HTTPException(400, "Not an image compositor")

    tracks = tl.tracks
    n = len(tracks)
    src = max(0, min(n - 1, req.fromIndex))
    dst = max(0, min(n - 1, req.toIndex))
    if src == dst:
        return {"status": "ok"}

 
    layer = tracks.pop(src)
    tracks.insert(dst, layer)

    from backend.events import notify; notify("timeline")
    return {"status": "ok", "fromIndex": src, "toIndex": dst}


 
class CreatePdfDocRequest(BaseModel):
    name: str = "Untitled Document"
    width: int = 1920
    height: int = 1080


class ReorderPagesRequest(BaseModel):
    page_ids: list[str]   


def _make_image_comp(name: str, width: int, height: int, hidden: bool = True):
    """Create a new image composition (PDF page) and return it."""
    comp = engine.createComposition(name=name, width=width, height=height, fps=30, total_frames=1)
    comp.kind = "image"
    comp.isHidden = hidden   
    comp.isDefault = False
    return comp


def _get_pdf_doc(doc_id: str):
    tl = engine.getTimeline(doc_id)
    if tl is None:
        raise HTTPException(404, f"PDF document {doc_id!r} not found")
    if getattr(tl, "kind", "video") != "pdf":
        raise HTTPException(400, f"{doc_id!r} is not a PDF document")
    return tl



@router.get("/comps/{compId}/pdf-pages")
def getCompPdfPages(compId: str):
    """Return ordered page list for a PDF comp — used by Electron export:capture-pdf."""
    tl = engine.getTimeline(compId)
    if tl is None:
        raise HTTPException(404, f"Comp {compId!r} not found")
    if getattr(tl, "kind", "video") != "pdf":
        raise HTTPException(400, f"Comp {compId!r} is not a PDF comp")
    doc_w = int(getattr(tl, "width",  1920))
    doc_h = int(getattr(tl, "height", 1080))
    page_ids = getattr(tl, "page_ids", [])
    pages = []
    for pid in page_ids:
        page_tl = engine.getTimeline(pid)
        if page_tl is None:
            continue
        pw = int(getattr(page_tl, "width",  doc_w))
        ph = int(getattr(page_tl, "height", doc_h))
        if pw != doc_w or ph != doc_h:
            page_tl.width  = doc_w
            page_tl.height = doc_h
            pw, ph = doc_w, doc_h
        pages.append({"compId": pid, "width": pw, "height": ph,
                      "name": getattr(page_tl, "name", f"Page {len(pages)+1}")})
    return {"compId": compId, "pages": pages}


@router.post("/pdf-docs")
def createPdfDoc(req: CreatePdfDocRequest):
    """Create a new PDF document with one blank first page.
    If a default PDF doc already exists, return it instead of creating a duplicate."""
    if engine.project is None:
        raise HTTPException(400, "No active project")

 
    for tl in engine.project.timelines:
        if getattr(tl, "kind", "video") == "pdf":
            return {
                "docId": tl.timelineId,
                "name": tl.name,
                "kind": "pdf",
                "isDefault": getattr(tl, "isDefault", False),
                "pageIds": list(getattr(tl, "page_ids", [])),
            }

    # No PDF doc exists yet — create one.
    doc = engine.createComposition(
        name=req.name, width=req.width, height=req.height, fps=30, total_frames=1
    )
    doc.kind = "pdf"
    doc.isDefault = True   # first PDF doc is always the default
    doc.isHidden = False
    doc.page_ids = []

    # Create first page as a hidden image comp
    page = _make_image_comp(f"{req.name} — Page 1", req.width, req.height, hidden=True)
    doc.page_ids.append(page.timelineId)

    from backend.events import notify; notify("comps")
    return {
        "docId": doc.timelineId,
        "name": doc.name,
        "kind": "pdf",
        "isDefault": True,
        "pageIds": doc.page_ids,
    }


@router.get("/pdf-docs")
def listPdfDocs():
    """List all PDF documents in the project."""
    if engine.project is None:
        return {"docs": []}
    docs = []
    for tl in engine.project.timelines:
        if getattr(tl, "kind", "video") == "pdf":
            docs.append({
                "docId": tl.timelineId,
                "name": tl.name,
                "kind": "pdf",
                "isDefault": getattr(tl, "isDefault", False),
                "pageCount": len(getattr(tl, "page_ids", [])),
                "pageIds": list(getattr(tl, "page_ids", [])),
            })
    return {"docs": docs}


@router.get("/pdf-docs/{docId}/pages")
def getPdfPages(docId: str):
    """Get ordered list of pages for a PDF document."""
    doc = _get_pdf_doc(docId)
    doc_w = int(getattr(doc, "width",  1920))
    doc_h = int(getattr(doc, "height", 1080))

    pages = []
    for idx, comp_id in enumerate(doc.page_ids):
        comp = engine.getTimeline(comp_id)
        if comp is not None:
        
            if int(getattr(comp, "width", 0)) != doc_w or int(getattr(comp, "height", 0)) != doc_h:
                comp.width  = doc_w
                comp.height = doc_h
                print(f"[AutoRepair] Page {comp.name} resized to {doc_w}x{doc_h}", flush=True)
        pages.append({
            "index": idx,
            "pageId": comp_id,
            "compId": comp_id,
            "name": comp.name if comp else f"Page {idx + 1}",
            "width": doc_w,
            "height": doc_h,
            "exists": comp is not None,
        })
    return {"docId": docId, "pages": pages}


@router.post("/pdf-docs/{docId}/pages")
def addPdfPage(docId: str):
    """Add a new blank page to the PDF document."""
    if engine.project is None:
        raise HTTPException(400, "No active project")
    doc = _get_pdf_doc(docId)
    page_num = len(doc.page_ids) + 1
    doc_name = doc.name
    # Inherit parent PDF doc's dimensions so every page matches the doc canvas size
    doc_w = int(getattr(doc, "width",  1920))
    doc_h = int(getattr(doc, "height", 1080))
    page = _make_image_comp(f"{doc_name} \u2014 Page {page_num}", doc_w, doc_h)
    doc.page_ids.append(page.timelineId)
    from backend.events import notify; notify("comps")
    return {
        "index": len(doc.page_ids) - 1,
        "pageId": page.timelineId,
        "compId": page.timelineId,
        "name": page.name,
    }



@router.delete("/pdf-docs/{docId}/pages/{pageId}")
def deletePdfPage(docId: str, pageId: str):
    """Delete a page from the PDF document (also deletes the imageComp)."""
    if engine.project is None:
        raise HTTPException(400, "No active project")
    doc = _get_pdf_doc(docId)
    if pageId not in doc.page_ids:
        raise HTTPException(404, f"Page {pageId!r} not in document {docId!r}")
    if len(doc.page_ids) <= 1:
        raise HTTPException(400, "Cannot delete the last page")
    doc.page_ids.remove(pageId)
    engine.deleteComposition(pageId)
    from backend.events import notify; notify("comps")
    return {"status": "ok", "docId": docId, "deletedPageId": pageId}


@router.post("/pdf-docs/{docId}/pages/reorder")
def reorderPdfPages(docId: str, req: ReorderPagesRequest):
    """Reorder pages by providing the new complete ordered list of compIds."""
    doc = _get_pdf_doc(docId)
    if set(req.page_ids) != set(doc.page_ids):
        raise HTTPException(400, "page_ids must contain the same pages, just reordered")
    doc.page_ids = list(req.page_ids)
    from backend.events import notify; notify("comps")
    return {"status": "ok", "pageIds": doc.page_ids}


@router.post("/pdf-docs-repair-sizes")
def repairPdfPageSizes():
    """Fix any PDF page comps whose width/height does not match their parent doc."""
    if engine.project is None:
        raise HTTPException(400, "No active project")
    fixed = []
    for tl in engine.project.timelines:
        if getattr(tl, "kind", "video") != "pdf":
            continue
        doc_w = int(getattr(tl, "width",  1920))
        doc_h = int(getattr(tl, "height", 1080))
        for pid in getattr(tl, "page_ids", []):
            page = engine.getTimeline(pid)
            if page is None:
                continue
            page_w = int(getattr(page, "width",  1920))
            page_h = int(getattr(page, "height", 1080))
            if page_w != doc_w or page_h != doc_h:
                page.width  = doc_w
                page.height = doc_h
                fixed.append({"pageId": pid, "newWidth": doc_w, "newHeight": doc_h})
                print(f"[RepairPageSizes] {page.name}: {page_w}x{page_h} -> {doc_w}x{doc_h}", flush=True)
    from backend.events import notify; notify("comps")
    return {"fixed": fixed, "count": len(fixed)}
