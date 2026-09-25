import time
import traceback
from fastapi import APIRouter
from fastapi.responses import Response
from backend.state import engine, _library
from backend.serializers import _serialize_effects, _serialize_clip_type_fields

router = APIRouter()


def _build_comp_frame_descriptor(
    comp_id: str,
    inner_frame: int,
    fps: float,
    width: int,
    height: int,
    _depth: int = 0,
) -> dict | None:
    if _depth > 8:
        return None
    inner_tl = engine.getTimeline(comp_id)
    if inner_tl is None:
        return None

    c_width = getattr(inner_tl, "width",  width)
    c_height = getattr(inner_tl, "height", height)
    c_fps = getattr(inner_tl, "fps",    fps)

    inner_clips: list[dict] = []
    for inner_track in reversed(inner_tl.tracks):
        if getattr(inner_track, "isMuted", False):
            continue
        # Skip audio tracks 
        if getattr(inner_track, 'isAudio', lambda: False)():
            continue
        for inner_clip in inner_track.clips:
            if not inner_clip.overlaps(inner_frame):
                continue
            ic_type = getattr(inner_clip, "CLIP_TYPE", getattr(inner_clip, "clipType", "video"))
            # Skip pure-audio clips  
            if ic_type == "audio":
                continue
            ic_file = getattr(inner_clip, "filepath", "")
            if not ic_file:
                ic_aid = getattr(inner_clip, "assetId", "")
                ic_ast = _library.get(ic_aid)
                if ic_ast:
                    ic_file = getattr(ic_ast, "filepath", "")
            try:
                ic_sf = inner_clip.sourceFrame(inner_frame)
            except Exception:
                ic_sf = 0
            try:
                inner_clip.evaluateAll(inner_frame)
            except Exception:
                pass
            try:
                ic_op = float(inner_clip.transform.opacity.get())
            except Exception:
                ic_op = 1.0
            try:
                it = inner_clip.transform
                ipx, ipy = it.position.get()
                isx, isy = it.scale.get()
                irot = it.rotation.get()
                iax, iay = it.anchor.get()
                ic_xform = {
                    "x": float(ipx), "y": float(ipy),
                    "scaleX": float(isx), "scaleY": float(isy),
                    "rotation": float(irot),
                    "anchorX": float(iax), "anchorY": float(iay),
                }
            except Exception:
                ic_xform = {"x": 0, "y": 0, "scaleX": 1, "scaleY": 1,
                            "rotation": 0, "anchorX": 0, "anchorY": 0}
            try:
                bm = inner_clip.blendMode
                ic_bm = int(bm.get()) if hasattr(bm, "get") else int(bm) if bm else 0
            except Exception:
                ic_bm = 0

            ic_data: dict = {
                "clipId": inner_clip.clipId,
                "file": ic_file,
                "sourceFrame": ic_sf,
                "opacity": ic_op,
                "blendMode": ic_bm,
                "type": ic_type,
                "transform": ic_xform,
                "effects": _serialize_effects(inner_clip, inner_frame),
            }
            _serialize_clip_type_fields(
                inner_clip, ic_type, inner_frame, ic_data,
                fps=c_fps, width=c_width, height=c_height, _depth=_depth
            )
            if ic_type in ("video", "image") and ic_file:
                try:
                    from backend.renderer.bridge import schedRegisterVideo, schedRegisterImage, schedPrefetchAround
                    if ic_type == "video":
                        schedRegisterVideo(ic_file, ic_file)
                    else:
                        schedRegisterImage(ic_file, ic_file)
                    schedPrefetchAround(ic_file, int(ic_sf), 4)
                except Exception:
                    pass
            inner_clips.append(ic_data)

            if hasattr(inner_clip, "brush_strokes") and inner_clip.brush_strokes:
                for idx, stroke in enumerate(inner_clip.brush_strokes):
                    if ic_type == "image":
                        scale = min(1920.0 / c_width, 1080.0 / c_height)
                        offset_x = (1920.0 - c_width * scale) / 2.0
                        offset_y = (1080.0 - c_height * scale) / 2.0
                        pen_points = [
                            {
                                "x": float(pt['x']) * scale + offset_x,
                                "y": float(pt['y']) * scale + offset_y,
                                "inX": 0.0, "inY": 0.0,
                                "outX": 0.0, "outY": 0.0
                            }
                            for pt in stroke.points
                        ]
                        xform = {"x": 0.0, "y": 0.0, "scaleX": 1.0, "scaleY": 1.0, "rotation": 0.0, "anchorX": 0.0, "anchorY": 0.0}
                        stroke_width = float(stroke.size) * scale
                    else:
                        pen_points = [
                            {
                                "x": float(pt['x']),
                                "y": float(pt['y']),
                                "inX": 0.0, "inY": 0.0,
                                "outX": 0.0, "outY": 0.0
                            }
                            for pt in stroke.points
                        ]
                        xform = ic_xform
                        stroke_width = float(stroke.size)

                    brush_clip = {
                        "clipId": f"{inner_clip.clipId}_brush_{idx}",
                        "file": "",
                        "sourceFrame": ic_sf,
                        "opacity": ic_op,
                        "blendMode": ic_bm,
                        "type": "pen",
                        "transform": xform,
                        "effects": [],
                        "penStyle": {
                            "isClosed": False,
                            "points": pen_points,
                            "fillOpacity": 0.0,
                            "strokeColor": list(stroke.color),
                            "strokeWidth": stroke_width,
                            "shadowEnabled": False,
                        }
                    }
                    inner_clips.append(brush_clip)

    if inner_frame % 30 == 0 or _depth == 0:
        print(f"[CompFD depth={_depth}] comp={comp_id} inner_frame={inner_frame} "
              f"tracks={len(inner_tl.tracks)} clips_in_fd={len(inner_clips)}", flush=True)

    return {
        "frame": inner_frame,
        "fps": float(c_fps),
        "width": int(c_width),
        "height": int(c_height),
        "clips": inner_clips,
        "compId": comp_id,
    }


_frame_cache_project: tuple = (None, 30.0, 1920, 1080) 


def _get_frame_data(frame: int) -> dict:
    global _frame_cache_project
    tl = engine.activeTimeline if engine else None
    if tl is None:
        return {"frame": frame, "fps": 30.0, "width": 1920, "height": 1080, "clips": []}

    proj = engine.project
    # Cache fps/width/height  
    if proj is not _frame_cache_project[0]:
        _frame_cache_project = (
            proj,
            float(proj.fps) if proj else 30.0,
            int(proj.width) if proj else 1920,
            int(proj.height) if proj else 1080,
        )
    _, fps, width, height = _frame_cache_project

    clips_out = []
    for track in reversed(tl.tracks):
        if getattr(track, "isMuted", False):
            continue
        # Skip audio tracks  
        if getattr(track, 'isAudio', lambda: False)():
            continue
        for clip in track.clips:
            if not clip.overlaps(frame):
                continue
            clip_id   = getattr(clip, "clipId", "")
            clip_type = getattr(clip, "CLIP_TYPE", getattr(clip, "clipType", "video"))
            # Skip pure-audio clips 
            if clip_type == "audio":
                continue
            filepath  = getattr(clip, "filepath", "")
            if not filepath:
                asset_id = getattr(clip, "assetId", "")
                asset    = _library.get(asset_id)
                if asset:
                    filepath = getattr(asset, "filepath", "")
            try:
                source_frame = clip.sourceFrame(frame)
            except Exception:
                source_frame = 0
            
            try:
                clip.evaluateAll(frame)
            except Exception:
                pass
            try:
                opacity = float(clip.transform.opacity.get())
            except Exception:
                opacity = 1.0
            try:
                blend_mode = int(clip.blendMode.get())
            except Exception:
                bm = getattr(clip, "blendMode", 0)
                blend_mode = int(bm.get()) if hasattr(bm, "get") else int(bm) if bm else 0
            t = clip.transform
            try:
                px, py = t.position.get()
                sx, sy = t.scale.get()
                rot = t.rotation.get()
                ax, ay = t.anchor.get()
                transform_dict = {
                    "x": float(px), "y": float(py),
                    "scaleX": float(sx), "scaleY": float(sy),
                    "rotation": float(rot),
                    "anchorX": float(ax), "anchorY": float(ay),
                }
            except Exception:
                transform_dict = {"x": 0, "y": 0, "scaleX": 1, "scaleY": 1,
                                  "rotation": 0, "anchorX": 0.0, "anchorY": 0.0}

            clip_data: dict = {
                "clipId": clip_id,
                "file": filepath,
                "sourceFrame": source_frame,

                "opacity": opacity,
                "blendMode": blend_mode,
                "type": clip_type,
                "transform": transform_dict,
                "effects": _serialize_effects(clip, frame),
            }
            _serialize_clip_type_fields(clip, clip_type, frame, clip_data,
                                        fps=fps, width=width, height=height, _depth=0)

            raw_masks = getattr(clip, "masks", [])
            if raw_masks:
                masks_out = []
                lf = frame - clip.startFrame
                for m in raw_masks:
                    if hasattr(m, "evaluateAll"):
                        m.evaluateAll(lf)
                    pts = m.maskPath.getFlatList() if hasattr(m, "maskPath") else []
                    masks_out.append({
                        "maskId": m.maskId,
                        "shape": m.shape,
                        "mode": m.mode,
                        "inverted":  m.inverted,
                        "feather": float(m.feather.get()) if hasattr(m.feather, "get") else float(m.feather),
                        "opacity": float(m.opacity.get()) if hasattr(m.opacity, "get") else float(m.opacity),
                        "expansion": float(m.expansion.get()) if hasattr(m.expansion, "get") else 0.0,
                        "size": float(m.size.get()) if hasattr(m.size, "get") else 100.0,
                        "posX": float(m.position.x.get()) if hasattr(m, "position") else 0.0,
                        "posY": float(m.position.y.get()) if hasattr(m, "position") else 0.0,
                        "rotation": float(m.rotation.get()) if hasattr(m, "rotation") and hasattr(m.rotation, "get") else 0.0,
                        "points": pts,
                    })
                clip_data["masks"] = masks_out

            clips_out.append(clip_data)

            try:
                if hasattr(clip, "brush_strokes") and clip.brush_strokes:
                    for idx, stroke in enumerate(clip.brush_strokes):
                        if clip_type == "image":
                            scale = min(1920.0 / width, 1080.0 / height)
                            offset_x = (1920.0 - width * scale) / 2.0
                            offset_y = (1080.0 - height * scale) / 2.0
                            pen_points = [
                                {
                                    "x": float(pt['x']) * scale + offset_x,
                                    "y": float(pt['y']) * scale + offset_y,
                                    "inX": 0.0, "inY": 0.0,
                                    "outX": 0.0, "outY": 0.0
                                }
                                for pt in stroke.points
                            ]
                            xform = {"x": 0.0, "y": 0.0, "scaleX": 1.0, "scaleY": 1.0, "rotation": 0.0, "anchorX": 0.0, "anchorY": 0.0}
                            stroke_width = float(stroke.size) * scale
                        else:
                            pen_points = [
                                {
                                    "x": float(pt['x']),
                                    "y": float(pt['y']),
                                    "inX": 0.0, "inY": 0.0,
                                    "outX": 0.0, "outY": 0.0
                                }
                                for pt in stroke.points
                            ]
                            xform = transform_dict
                            stroke_width = float(stroke.size)

                        brush_clip = {
                            "clipId": f"{clip_id}_brush_{idx}",
                            "file": "",
                            "sourceFrame": source_frame,
                            "opacity": opacity,
                            "blendMode": blend_mode,
                            "type": "pen",
                            "transform": xform,
                            "effects": [],
                            "penStyle": {
                                "isClosed": False,
                                "points": pen_points,
                                "fillOpacity": 0.0,
                                "strokeColor": list(stroke.color),
                                "strokeWidth": stroke_width,
                                "shadowEnabled": False,
                            }
                        }
                        clips_out.append(brush_clip)
            except Exception as e:
                print(f"[BrushSerialize] ERROR for clip {clip_id}: {e}", flush=True)

    transition_desc = None
    result = tl.getTransitionAt(frame)
    if result is not None:
        tr, prog, clipA, clipB = result

        def _build_clip_desc(clip):
            ctype = getattr(clip, "CLIP_TYPE", getattr(clip, "clipType", "video"))
            fpath = getattr(clip, "filepath", "")
            if not fpath:
                 
                wid = getattr(clip, "webcompId", "")
                if wid:
                    fpath = f"webcomp://{wid}"
                else:
                    aid = getattr(clip, "assetId", "")
                    ast = _library.get(aid)
                    if ast:
                        fpath = getattr(ast, "filepath", "")
            try: sf = clip.sourceFrame(frame)
            except Exception: sf = 0
            try: clip.evaluateAll(frame)
            except Exception: pass
            try: op = float(clip.transform.opacity.get())
            except Exception: op = 1.0
            return {
                "clipId": clip.clipId, "file": fpath, "type": ctype,
                "sourceFrame": sf, "opacity": op, "blendMode": 0,
                "transform": {"x":0,"y":0,"scaleX":1,"scaleY":1,"rotation":0,"anchorX":0,"anchorY":0},
                "effects": _serialize_effects(clip, frame),
            }

        ids_in_out = {c["clipId"] for c in clips_out}
        if clipA.clipId not in ids_in_out:
            clips_out.append(_build_clip_desc(clipA))
        if clipB.clipId not in ids_in_out:
            clips_out.append(_build_clip_desc(clipB))

        uniforms = [{"id": "progress", "values": [prog]}]
        for pid, pdef in tr.params().items():
            uniforms.append({"id": pid, "values": [float(pdef["value"])]})
        uniforms.append({"id": "resolution", "values": [float(width), float(height)]})
        transition_desc = {
            "typeId": tr.typeId, "transId": tr.transId,
            "clipA_id": clipA.clipId, "clipB_id": clipB.clipId,
            "progress": prog, "uniforms": uniforms,
        }

    result_dict: dict = {"frame": frame, "fps": fps, "width": width, "height": height, "clips": clips_out}
    if transition_desc:
        result_dict["transition"] = transition_desc

    comp_only = (len(clips_out) == 1 and clips_out[0].get("type") == "comp")
    if comp_only:
        result_dict["clips"] = clips_out + [{
            "clipId": "__sentinel__", "file": "", "sourceFrame": 0,
            "opacity": 0.0, "blendMode": 0, "type": "solid",
            "transform": {"x": 0, "y": 0, "scaleX": 1, "scaleY": 1, "rotation": 0, "anchorX": 0, "anchorY": 0},
            "effects": [], "color": {"r": 0.0, "g": 0.0, "b": 0.0, "a": 0.0},
        }]
    return result_dict


@router.get("/render/frame/{frame}")
def getRenderFrame(frame: int):
    _t0 = time.perf_counter()
    tl = engine.activeTimeline if engine else None
    if tl is None:
        return {"frame": frame, "fps": 30.0, "width": 1920, "height": 1080, "clips": []}
    result = _get_frame_data(frame)
    print(f"[FRAME] << frame={frame} | clips={len(result['clips'])} | dt={1000*(time.perf_counter()-_t0):.1f}ms", flush=True)
    return result


@router.get("/frame/{frame}")
def getFrame(frame: int):
    png = engine.renderFramePng(frame)
    return Response(content=png, media_type="image/png")


@router.get("/thumbnail/{frame}")
def getThumbnail(frame: int, w: int = 320, h: int = 180):
    png = engine.renderThumbnail(frame, w, h)
    return Response(content=png, media_type="image/png")


from pydantic import BaseModel
from fastapi import HTTPException


class ScaleRequest(BaseModel):
    scale: float


class FormatRequest(BaseModel):
    format: str


@router.post("/preview/scale")
def setPreviewScale(req: ScaleRequest):
    clamped = max(0.125, min(1.0, req.scale))
    engine.setPreviewScale(clamped)
    return {"scale": clamped}


@router.get("/preview/scale")
def getPreviewScale():
    return {"scale": engine.getPreviewScale()}


@router.post("/preview/format")
def setPreviewFormat(req: FormatRequest):
    if req.format not in ('jpeg', 'png'):
        raise HTTPException(400, "format must be 'jpeg' or 'png'")
    engine.setPreviewFormat(req.format)
    return {"format": req.format}


@router.get("/preview/format")
def getPreviewFormat():
    return {"format": engine.getPreviewFormat()}


@router.get("/perf")
def perfStats():
    return engine.perfStats()
