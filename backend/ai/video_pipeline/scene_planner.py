"""
backend/ai/video_pipeline/scene_planner.py
LangChain node: takes news items → LLM structured output → ScenePlan
"""
from __future__ import annotations
import json
from typing import Callable

from backend.ai.video_pipeline.schema import ScenePlan
from backend.ai.video_pipeline.news_search import NewsItem, format_for_llm


def _build_prompt(
    query: str,
    news_items: list[NewsItem],
    scene_duration: int,
    fps: float,
) -> str:
    total_scenes = len(news_items)
    total_frames = total_scenes * scene_duration
    total_sec = total_frames / fps
    news_text = format_for_llm(news_items)

    schema_str = json.dumps(ScenePlan.model_json_schema(), indent=2)

    return f"""You are a professional video editor and news producer.
Your job is to create a detailed, frame-accurate scene plan for a news video.

USER QUERY: "{query}"

NEWS ITEMS ({total_scenes} stories):
{news_text}

VIDEO SPECS:
- FPS: {fps}
- Frames per scene: {scene_duration} ({scene_duration/fps:.1f} seconds each)
- Total scenes: {total_scenes}
- Total frames: {total_frames} ({total_sec:.0f} seconds total)

TRACK LAYOUT:
- Track 0: B-roll (video clip or AI-generated image — full scene duration)
- Track 1: Headline title overlay (appears at frame 0, holds for full scene)
- Track 2: Lower-third label (appears at frame 0, holds for 3 seconds = {int(fps*3)} frames)

BROLL RULES (strictly alternate):
- Odd scenes  (1, 3, 5...): type = "video" — write a short cinematic YouTube search query (5-8 words)
- Even scenes (2, 4, 6...): type = "image" — write a detailed Imagen-style prompt (20-40 words, rich adjectives, photorealistic)

EFFECTS RULE:
- For ALL image b-rolls: add a blur effect from relative frame 0 to {int(fps*1)} (1-second gentle blur-in)
  params: {{"radius": 8}}

TITLE RULES:
- textContent: the headline (max 80 chars, truncate if needed)
- fontSize: 52 for top stories (1-3), 44 for others
- dropShadow: always true
- backgroundColor: "#00000088"

LOWER THIRD RULES:
- textContent: source name in ALL CAPS (e.g. "BBC NEWS", "REUTERS") or a category tag

FRAME OFFSETS:
- Scene N starts at fromFrame = (N-1) × {scene_duration}
- Scene N ends at toFrame = N × {scene_duration}
- All fromFrame/toFrame in title and broll configs must be ABSOLUTE (not relative to scene start)

Return ONLY valid JSON matching this schema. No markdown, no explanation:
{schema_str}"""


def plan_scenes(
    query: str,
    news_items: list[NewsItem],
    llm,
    scene_duration: int = 150,
    fps: float = 30.0,
    progress_cb: Callable[[str], None] | None = None,
) -> ScenePlan:
    """
    Calls the LLM with structured output to generate a ScenePlan.

    Args:
        query:         Original user query.
        news_items:    List of news articles from news_search.
        llm:           A LangChain chat model instance.
        scene_duration: Frames per scene (default 150 = 5s @ 30fps).
        fps:           Project frame rate.
        progress_cb:   Optional callback for streaming progress strings.
    """
    from langchain_core.messages import HumanMessage

    if progress_cb:
        progress_cb(f"Planning {len(news_items)} scenes…")

    prompt = _build_prompt(query, news_items, scene_duration, fps)

    # Use structured output — LLM must return valid ScenePlan JSON
    structured_llm = llm.with_structured_output(ScenePlan)
    plan: ScenePlan = structured_llm.invoke([HumanMessage(content=prompt)])

    if progress_cb:
        progress_cb(f"Scene plan ready: {plan.totalScenes} scenes, {plan.totalFrames} frames")

    return plan
