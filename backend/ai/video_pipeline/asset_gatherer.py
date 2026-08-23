"""
backend/ai/video_pipeline/asset_gatherer.py
Gathers all media assets for a ScenePlan in parallel:
  - video scenes  → POST /media/download-search  (yt-dlp)
  - image scenes  → POST /media/generate-image   (Gemini Imagen)
  - none  scenes  → skipped

Returns a mapping: {scene_id: assetId}
"""
from __future__ import annotations
import asyncio
import httpx
from typing import Callable

from backend.ai.video_pipeline.schema import ScenePlan, Scene


_TIMEOUT = httpx.Timeout(180.0)  # image gen can be slow


async def _download_video(scene: Scene, port: int) -> tuple[int, str | None]:
    """Download a YouTube video for a scene. Returns (scene_id, assetId | None)."""
    base = f"http://127.0.0.1:{port}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(f"{base}/media/download-search", json={
                "query": scene.broll.searchQuery,
                "numVideos": 1,
            })
            resp.raise_for_status()
            assets = resp.json().get("assets", [])
            if assets:
                asset_id = assets[0]["assetId"]
                print(f"[AssetGatherer] Scene {scene.id} video → {assets[0]['filename']}", flush=True)
                return scene.id, asset_id
    except Exception as e:
        print(f"[AssetGatherer] Scene {scene.id} video failed: {e}", flush=True)
    return scene.id, None


async def _generate_image(scene: Scene, port: int) -> tuple[int, str | None]:
    """Generate an AI image for a scene. Returns (scene_id, assetId | None)."""
    base = f"http://127.0.0.1:{port}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(f"{base}/media/generate-image", json={
                "prompt": scene.broll.generatePrompt,
                "numImages": 1,
            })
            resp.raise_for_status()
            assets = resp.json().get("assets", [])
            if assets:
                asset_id = assets[0]["assetId"]
                print(f"[AssetGatherer] Scene {scene.id} image → {assets[0]['filename']}", flush=True)
                return scene.id, asset_id
    except Exception as e:
        print(f"[AssetGatherer] Scene {scene.id} image failed: {e}", flush=True)
    return scene.id, None


async def gather_assets(
    plan: ScenePlan,
    port: int = 8000,
    progress_cb: Callable[[str], None] | None = None,
) -> dict[int, str]:
    """
    Downloads/generates all assets in the plan concurrently.
    Returns {scene_id: assetId} for scenes that succeeded.
    """
    if progress_cb:
        progress_cb(f"Gathering assets for {plan.totalScenes} scenes (parallel)…")

    tasks = []
    for scene in plan.scenes:
        btype = scene.broll.type
        if btype == "video":
            tasks.append(_download_video(scene, port))
        elif btype == "image":
            tasks.append(_generate_image(scene, port))
        else:
            tasks.append(asyncio.coroutine(lambda s=scene: (s.id, None))())

    results = await asyncio.gather(*tasks, return_exceptions=True)

    asset_map: dict[int, str] = {}
    for result in results:
        if isinstance(result, Exception):
            print(f"[AssetGatherer] Exception: {result}", flush=True)
            continue
        scene_id, asset_id = result
        if asset_id:
            asset_map[scene_id] = asset_id

    if progress_cb:
        progress_cb(f"Assets ready: {len(asset_map)}/{plan.totalScenes} scenes have media")

    return asset_map
