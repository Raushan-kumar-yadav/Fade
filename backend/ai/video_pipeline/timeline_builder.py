"""
backend/ai/video_pipeline/timeline_builder.py
Builds the Fade timeline from a ScenePlan + resolved asset map.
Calls Fade's existing REST API endpoints.
"""
from __future__ import annotations
import httpx
from typing import Callable

from backend.ai.video_pipeline.schema import ScenePlan, Scene, EffectConfig


_TIMEOUT = httpx.Timeout(30.0)


def _post(base: str, path: str, body: dict) -> dict:
    with httpx.Client(timeout=_TIMEOUT) as client:
        r = client.post(f"{base}{path}", json=body)
        r.raise_for_status()
        return r.json()


def _place_broll(base: str, scene: Scene, asset_id: str) -> str | None:
    """Place a b-roll clip on track 0. Returns clipId or None."""
    duration = scene.broll.toFrame - scene.broll.fromFrame
    try:
        result = _post(base, "/timeline/add-clip", {
            "assetId": asset_id,
            "trackIndex": scene.broll.track,
            "startFrame": scene.broll.fromFrame,
            "duration": duration,
        })
        clip_id = result.get("clipId")
        print(f"[TimelineBuilder] Scene {scene.id} broll clip → {clip_id}", flush=True)
        return clip_id
    except Exception as e:
        print(f"[TimelineBuilder] Scene {scene.id} broll failed: {e}", flush=True)
        return None


def _place_title(base: str, scene: Scene) -> str | None:
    """Place a title text clip on track 1. Returns clipId or None."""
    cfg = scene.title
    duration = cfg.toFrame - cfg.fromFrame
    try:
        result = _post(base, "/clips/text", {
            "trackIndex": cfg.track,
            "startFrame": cfg.fromFrame,
            "duration": duration,
            "text": cfg.textContent,
            "fontSize": cfg.fontSize,
            "bold": cfg.bold,
            "color": cfg.color,
            "dropShadow": cfg.dropShadow,
            "backgroundEnabled": cfg.backgroundEnabled,
            "backgroundColor": cfg.backgroundColor,
        })
        clip_id = result.get("clipId")
        print(f"[TimelineBuilder] Scene {scene.id} title clip  → {clip_id}", flush=True)
        return clip_id
    except Exception as e:
        print(f"[TimelineBuilder] Scene {scene.id} title failed: {e}", flush=True)
        return None


def _place_lower_third(base: str, scene: Scene) -> str | None:
    """Place a lower-third text clip on track 2. Returns clipId or None."""
    if not scene.lowerThird:
        return None
    lt = scene.lowerThird
    duration = lt.toFrame - lt.fromFrame
    try:
        result = _post(base, "/clips/text", {
            "trackIndex": lt.track,
            "startFrame": lt.fromFrame,
            "duration": duration,
            "text": lt.textContent,
            "fontSize": lt.fontSize,
            "color": lt.color,
            "backgroundEnabled": lt.backgroundEnabled,
            "backgroundColor": lt.backgroundColor,
        })
        clip_id = result.get("clipId")
        print(f"[TimelineBuilder] Scene {scene.id} lower-third → {clip_id}", flush=True)
        return clip_id
    except Exception as e:
        print(f"[TimelineBuilder] Scene {scene.id} lower-third failed: {e}", flush=True)
        return None


def _apply_effects(base: str, clip_id: str, effects: list[EffectConfig], scene_start: int) -> None:
    """Apply effects to a clip. Converts relative frames to absolute."""
    for fx in effects:
        try:
            _post(base, f"/clips/{clip_id}/effects", {
                "effectName": fx.name,
                "params": fx.params,
            })
            print(f"[TimelineBuilder] Applied {fx.name} to clip {clip_id}", flush=True)
        except Exception as e:
            print(f"[TimelineBuilder] Effect {fx.name} failed: {e}", flush=True)


def build_timeline(
    plan: ScenePlan,
    asset_map: dict[int, str],
    port: int = 8000,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """
    Iterates scenes and calls Fade REST endpoints to build the full timeline.

    Returns summary dict: {placed_clips, failed_scenes}
    """
    base = f"http://127.0.0.1:{port}"
    placed = 0
    failed = []

    for scene in plan.scenes:
        if progress_cb:
            progress_cb(f"Building scene {scene.id}/{plan.totalScenes}: {scene.headline[:50]}")

        # 1. Place b-roll (video or image)
        broll_clip_id = None
        asset_id = asset_map.get(scene.id)
        if asset_id:
            broll_clip_id = _place_broll(base, scene, asset_id)

        # 2. Apply effects to b-roll
        if broll_clip_id and scene.broll.effects:
            _apply_effects(base, broll_clip_id, scene.broll.effects, scene.fromFrame)

        # 3. Place title
        title_clip_id = _place_title(base, scene)

        # 4. Place lower-third
        _place_lower_third(base, scene)

        if title_clip_id:
            placed += 1
        else:
            failed.append(scene.id)

    if progress_cb:
        progress_cb(f"Timeline built: {placed}/{plan.totalScenes} scenes placed")

    return {"placed_clips": placed, "failed_scenes": failed}
