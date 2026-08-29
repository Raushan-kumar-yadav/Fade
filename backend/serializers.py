from backend.engine.engine import Engine
from backend.media.asset.mediaAsset import MediaAsset


def _serialize_effects(clip, frame: int) -> list:
    out = []
    for eff in getattr(clip, "effects", []):
        try:
            if not getattr(eff, "enabled", True):
                continue
            type_id = getattr(eff, "typeId", None) or getattr(eff, "effectType", None)
            if not type_id:
                continue
            if hasattr(eff, "getUniformValues") and callable(eff.getUniformValues):
                uniforms_dict = eff.getUniformValues(frame) or {}
            elif hasattr(eff, "uniforms"):
                uniforms_dict = eff.uniforms or {}
            else:
                uniforms_dict = {}
            uniforms_list = []
            for k, v in uniforms_dict.items():
                if isinstance(v, list):
                    uniforms_list.append({"id": k, "values": [float(x) for x in v]})
                else:
                    uniforms_list.append({"id": k, "values": [float(v)]})
            out.append({"typeId": type_id, "uniforms": uniforms_list})
        except Exception as _e:
            print(f"[effects] serialization error for {type(eff).__name__}: {_e}")
    return out


def _serialize_clip_type_fields(
    clip,
    clip_type: str,
    frame: int,
    data: dict,
    fps: float = 30.0,
    width: int = 1920,
    height: int = 1080,
    _depth: int = 0,
) -> None:
    if clip_type == "solid":
        c = getattr(clip, "color", [0.5, 0.5, 0.5, 1.0])
        data["color"] = {"r": c[0], "g": c[1], "b": c[2], "a": c[3]}

    elif clip_type == "text":
        style = getattr(clip, "style", None)
        if style is not None:
            data["textStyle"] = {
                "text": getattr(style, "text", "New Text"),
                "fontFamily": getattr(style, "fontFamily", "Arial"),
                "fontSize": float(getattr(style, "fontSize", 48.0)),
                "bold": bool(getattr(style, "bold", False)),
                "italic": bool(getattr(style, "italic", False)),
                "alignment": getattr(style, "alignment", "left"),
                "lineHeight": float(getattr(style, "lineHeight", 1.2)),
                "letterSpacing": float(getattr(style, "letterSpacing", 0.0)),
                "allCaps": bool(getattr(style, "allCaps", False)),
                "color": list(getattr(style, "color", [1, 1, 1, 1])),
                "strokeColor": list(getattr(style, "strokeColor", [0, 0, 0, 1])),
                "strokeWidth": float(getattr(style, "strokeWidth", 0.0)),
                "shadowEnabled": bool(getattr(style, "shadowEnabled", False)),
                "shadowColor": list(getattr(style, "shadowColor", [0, 0, 0, 0.6])),
                "shadowOffsetX": float(getattr(style, "shadowOffsetX", 4.0)),
                "shadowOffsetY": float(getattr(style, "shadowOffsetY", 4.0)),
                "shadowBlur": float(getattr(style, "shadowBlur", 6.0)),
                "bgEnabled": bool(getattr(style, "bgEnabled", False)),
                "bgColor": list(getattr(style, "bgColor", [0, 0, 0, 0.5])),
                "bgPaddingX": float(getattr(style, "bgPaddingX", 20.0)),
                "bgPaddingY": float(getattr(style, "bgPaddingY", 10.0)),
                "bgCornerRadius": float(getattr(style, "bgCornerRadius", 0.0)),
                "animator": dict(getattr(style, "animator", {})),
            }

    elif clip_type == "shape":
        style = getattr(clip, "style", None)
        if style is not None:
            data["shapeStyle"] = {
                "shapeType": getattr(style, "shapeType", "rect"),
                "width": float(getattr(style, "width", 200.0)),
                "height": float(getattr(style, "height", 120.0)),
                "cornerRadius": float(getattr(style, "cornerRadius", 0.0)),
                "radiusX": float(getattr(style, "radiusX", 100.0)),
                "radiusY": float(getattr(style, "radiusY", 80.0)),
                "outerRadius": float(getattr(style, "outerRadius", 100.0)),
                "innerRadius": float(getattr(style, "innerRadius", 40.0)),
                "numPoints": int(getattr(style, "numPoints", 5)),
                "numSides": int(getattr(style, "numSides", 6)),
                "polygonRadius": float(getattr(style, "polygonRadius", 100.0)),
                "x1": float(getattr(style, "x1", -100.0)),
                "y1": float(getattr(style, "y1", 0.0)),
                "x2": float(getattr(style, "x2", 100.0)),
                "y2": float(getattr(style, "y2", 0.0)),
                "arcStartAngle": float(getattr(style, "arcStartAngle", 0.0)),
                "arcSweepAngle": float(getattr(style, "arcSweepAngle", 180.0)),
                "arcRadius": float(getattr(style, "arcRadius", 100.0)),
                "fillColor": list(getattr(style, "fillColor", [0.4, 0.4, 1.0, 1.0])),
                "fillOpacity": float(getattr(style, "fillOpacity", 1.0)),
                "strokeColor": list(getattr(style, "strokeColor", [1.0, 1.0, 1.0, 1.0])),
                "strokeWidth": float(getattr(style, "strokeWidth", 0.0)),
                "shadowEnabled": bool(getattr(style, "shadowEnabled", False)),
                "shadowColor": list(getattr(style, "shadowColor", [0, 0, 0, 0.75])),
                "shadowAngle": float(getattr(style, "shadowAngle", 135.0)),
                "shadowDistance": float(getattr(style, "shadowDistance", 10.0)),
                "shadowBlur": float(getattr(style, "shadowBlur", 5.0)),
            }

    elif clip_type == "pen":
        style  = getattr(clip, "style", None)
        points = getattr(clip, "points", [])
        data["penStyle"] = {
            "isClosed": bool(getattr(clip, "isClosed", False)),
            "points": [
                {
                    "x": float(getattr(p, "x", 0.0)),
                    "y": float(getattr(p, "y", 0.0)),
                    "inX": float(getattr(p, "inX", 0.0)),
                    "inY": float(getattr(p, "inY", 0.0)),
                    "outX": float(getattr(p, "outX", 0.0)),
                    "outY": float(getattr(p, "outY", 0.0)),
                }
                for p in points
            ],
            "fillColor": list(getattr(style, "fillColor", [0.4, 0.4, 1.0, 1.0])) if style else [0.4, 0.4, 1.0, 1.0],
            "fillOpacity": float(getattr(style, "fillOpacity", 1.0)) if style else 1.0,
            "strokeColor": list(getattr(style, "strokeColor", [1.0, 1.0, 1.0, 1.0])) if style else [1.0, 1.0, 1.0, 1.0],
            "strokeWidth": float(getattr(style, "strokeWidth", 2.0)) if style else 2.0,
            "shadowEnabled": bool(getattr(style, "shadowEnabled", False)) if style else False,
            "shadowColor": list(getattr(style, "shadowColor", [0, 0, 0, 0.75])) if style else [0, 0, 0, 0.75],
            "shadowAngle": float(getattr(style, "shadowAngle", 135.0)) if style else 135.0,
            "shadowDistance": float(getattr(style, "shadowDistance", 10.0)) if style else 10.0,
            "shadowBlur": float(getattr(style, "shadowBlur", 5.0)) if style else 5.0,
        }

    elif clip_type == "svg":
        data["file"] = getattr(clip, "filepath", data.get("file", ""))
        data["svgStyle"] = {
            "displayW": float(getattr(clip, "displayW", 0.0)),
            "displayH": float(getattr(clip, "displayH", 0.0)),
            "tintEnabled": bool(getattr(clip, "tintEnabled", False)),
            "tintColor": list(getattr(clip, "tintColor", [1.0, 1.0, 1.0, 1.0])),
        }

    elif clip_type == "comp":
        from backend.routers.render import _build_comp_frame_descriptor
        comp_id = getattr(clip, "compId", "")
        media_offset = getattr(clip, "mediaOffset", 0)
        inner_frame_nested = (frame - clip.startFrame) + media_offset
        if comp_id and _depth <= 7:
            data["compId"] = comp_id
            fd = _build_comp_frame_descriptor(
                comp_id, inner_frame_nested, fps, width, height, _depth + 1
            )
            if fd is not None:
                data["compFrameDescriptor"] = fd

    elif clip_type == "webcomp":
        webcomp_id = getattr(clip, "webcompId", "")
        data["webcompId"] = webcomp_id
        if webcomp_id:
            data["file"] = f"webcomp://{webcomp_id}"
        data["runtimeParams"] = getattr(clip, "_runtimeParams", {})

