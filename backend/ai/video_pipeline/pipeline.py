 
from __future__ import annotations
import asyncio
from typing import TypedDict, Callable, Any

from langgraph.graph import StateGraph, END

from backend.ai.video_pipeline.schema import ScenePlan
from backend.ai.video_pipeline.news_search import NewsItem, search_news
from backend.ai.video_pipeline.scene_planner import plan_scenes
from backend.ai.video_pipeline.asset_gatherer import gather_assets
from backend.ai.video_pipeline.timeline_builder import build_timeline

 
#   Pipeline State  

class PipelineState(TypedDict, total=False):
    # inputs
    query: str
    scene_duration: int          # frames per scene
    fps: float
    port: int

    # outputs from each node
    news_items: list[NewsItem]
    scene_plan: ScenePlan
    asset_map: dict[int, str]    
    build_result: dict
    summary: str

    # progress channel  
    progress: list[str]


#   Node helpers  

def _push(state: PipelineState, msg: str) -> None:
    state.setdefault("progress", []).append(msg)
    print(f"[Pipeline] {msg}", flush=True)


#   Nodes  

def node_search_news(state: PipelineState) -> PipelineState:
    _push(state, "stage:news_search — Searching for news…")
    items = search_news(state["query"], max_results=state.get("scene_duration", 10))
    # Cap to 10 stories
    items = items[:10]
    _push(state, f"stage:news_search — Found {len(items)} articles")
    return {**state, "news_items": items}


def node_plan_scenes(state: PipelineState) -> PipelineState:
    _push(state, "stage:plan_scenes — Generating scene plan via LLM…")

    from backend.ai.agent import get_agent_llm
    llm = get_agent_llm(state.get("port", 8000))

    plan = plan_scenes(
        query=state["query"],
        news_items=state["news_items"],
        llm=llm,
        scene_duration=state.get("scene_duration", 150),
        fps=state.get("fps", 30.0),
        progress_cb=lambda msg: _push(state, f"stage:plan_scenes — {msg}"),
    )
    _push(state, f"stage:plan_scenes — Plan ready: {plan.totalScenes} scenes")
    return {**state, "scene_plan": plan}


async def node_gather_assets(state: PipelineState) -> PipelineState:
    _push(state, "stage:gather_assets — Downloading videos & generating images…")

    asset_map = await gather_assets(
        plan=state["scene_plan"],
        port=state.get("port", 8000),
        progress_cb=lambda msg: _push(state, f"stage:gather_assets — {msg}"),
    )
    return {**state, "asset_map": asset_map}


def node_build_timeline(state: PipelineState) -> PipelineState:
    _push(state, "stage:build_timeline — Assembling timeline…")

    result = build_timeline(
        plan=state["scene_plan"],
        asset_map=state.get("asset_map", {}),
        port=state.get("port", 8000),
        progress_cb=lambda msg: _push(state, f"stage:build_timeline — {msg}"),
    )
    return {**state, "build_result": result}


def node_summarize(state: PipelineState) -> PipelineState:
    plan = state["scene_plan"]
    result = state.get("build_result", {})
    placed = result.get("placed_clips", 0)
    failed = result.get("failed_scenes", [])
    total_sec = plan.totalFrames / plan.fps

    video_scenes = sum(1 for s in plan.scenes if s.broll.type == "video")
    image_scenes = sum(1 for s in plan.scenes if s.broll.type == "image")

    summary = (
        f"✅ Created a {plan.totalScenes}-scene news video "
        f"({total_sec:.0f} seconds at {plan.fps:.0f}fps).\n"
        f"• {video_scenes} YouTube b-roll clips downloaded\n"
        f"• {image_scenes} AI-generated images (Gemini Imagen)\n"
        f"• {placed} scenes successfully placed on the timeline\n"
    )
    if failed:
        summary += f"• ⚠️  {len(failed)} scenes had issues: {failed}\n"

    summary += "\nTimeline layout:\n"
    summary += "  Track 0 = B-roll  |  Track 1 = Headlines  |  Track 2 = Lower-thirds"

    _push(state, f"stage:done — {summary}")
    return {**state, "summary": summary}


#   Async wrapper for gather_assets node  

def node_gather_assets_sync(state: PipelineState) -> PipelineState:
    """Synchronous wrapper — runs async gather_assets in a new event loop."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, node_gather_assets(state))
                return future.result()
        else:
            return loop.run_until_complete(node_gather_assets(state))
    except RuntimeError:
        return asyncio.run(node_gather_assets(state))


#   Graph  

def build_pipeline():
    g = StateGraph(PipelineState)

    g.add_node("search_news",    node_search_news)
    g.add_node("plan_scenes",    node_plan_scenes)
    g.add_node("gather_assets",  node_gather_assets_sync)
    g.add_node("build_timeline", node_build_timeline)
    g.add_node("summarize",      node_summarize)

    g.set_entry_point("search_news")
    g.add_edge("search_news",    "plan_scenes")
    g.add_edge("plan_scenes",    "gather_assets")
    g.add_edge("gather_assets",  "build_timeline")
    g.add_edge("build_timeline", "summarize")
    g.add_edge("summarize",      END)

    return g.compile()


# Singleton
_pipeline = None

def get_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = build_pipeline()
    return _pipeline
