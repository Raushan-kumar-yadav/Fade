from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.state import engine

router = APIRouter()


class EffectAddRequest(BaseModel):
    effectType: str


class EffectPatchRequest(BaseModel):
    enabled: bool | None = None
    params:  dict | None = None


def _find_clip(clipId: str):
    tl = engine.activeTimeline
    if tl is None:
        raise HTTPException(400, "No active timeline")
    for track in tl.tracks:
        for clip in track.clips:
            if clip.clipId == clipId:
                return clip, track
    if engine.project:
        for timeline in engine.project.timelines:
            for track in timeline.tracks:
                for clip in track.clips:
                    if clip.clipId == clipId:
                        return clip, track
    raise HTTPException(404, f"Clip {clipId!r} not found")


def _effect_to_dict(e) -> dict:
    from backend.timeline.effects.skslEffect import SkslEffect
    base = {
        "effectId": e.effectId, "name": e.name, "enabled": e.enabled,
        "type": getattr(e, "typeId", None) or e.toDict().get("type", "unknown"),
    }
    if isinstance(e, SkslEffect):
        params = {}
        for p in e._manifest.get("params", []):
            pid = p["id"]
            val = e._values.get(pid, p.get("default", 0.0))
            params[pid] = {
                "value": val, "min": p.get("min", 0.0), "max": p.get("max", 1.0),
                "type": p.get("type", "FloatSlider"), "displayName": p.get("displayName", pid),
            }
        base["params"] = params
        base["paramTypes"] = "typed"
    else:
        raw = e.params()
        base["params"] = {
            k: {"value": v[0], "min": v[1], "max": v[2],
                "type": "FloatSlider", "displayName": k.replace("_", " ").title()}
            for k, v in raw.items()
        }
        base["paramTypes"] = "typed"
    return base


@router.get("/effects/catalog")
def effectsCatalog():
    from backend.timeline.effects.effects import EFFECT_META
    return {"effects": EFFECT_META}


@router.post("/clips/{clipId}/effects")
def addEffect(clipId: str, req: EffectAddRequest):
    from backend.timeline.effects.effects import EFFECT_REGISTRY
    clip, _ = _find_clip(clipId)
    etype = req.effectType
    if etype.startswith("sksl:"):
        try:
            from backend.timeline.effects.skslEffect import _make_sksl
            eff = _make_sksl(etype[len("sksl:"):])
        except Exception as e:
            raise HTTPException(400, f"SkSL effect error: {e}")
    else:
        cls = EFFECT_REGISTRY.get(etype)
        if cls is None:
            raise HTTPException(400, f"Unknown effect type: {etype!r}")
        eff = cls()
    clip.effects.append(eff)
    return {"effectId": eff.effectId, "name": eff.name, "type": etype, "params": eff.params()}


@router.get("/clips/{clipId}/effects")
def listEffects(clipId: str):
    clip, _ = _find_clip(clipId)
    return {"effects": [_effect_to_dict(e) for e in clip.effects]}


@router.patch("/clips/{clipId}/effects/{effectId}")
def patchEffect(clipId: str, effectId: str, req: EffectPatchRequest):
    clip, _ = _find_clip(clipId)
    eff = next((e for e in clip.effects if e.effectId == effectId), None)
    if eff is None:
        raise HTTPException(404, "Effect not found")
    if req.enabled is not None:
        eff.enabled = req.enabled
    if req.params:
        from backend.timeline.effects.skslEffect import SkslEffect
        for k, v in req.params.items():
            if isinstance(eff, SkslEffect):
                eff._resolveVecParam(k, v) or eff.setParam(k, v)
            else:
                eff.setParam(k, float(v))
    return _effect_to_dict(eff)


@router.delete("/clips/{clipId}/effects/{effectId}")
def removeEffect(clipId: str, effectId: str):
    clip, _ = _find_clip(clipId)
    before = len(clip.effects)
    clip.effects = [e for e in clip.effects if e.effectId != effectId]
    if len(clip.effects) == before:
        raise HTTPException(404, "Effect not found")
    return {"status": "ok"}
