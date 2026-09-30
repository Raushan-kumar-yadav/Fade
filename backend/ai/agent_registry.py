 
from __future__ import annotations

import os

# Per-type agent cache
_cache: dict[str, object] = {}


#   System prompts per agent type  

_BASE_PROMPT = (
    "You are an AI assistant inside Fade, a professional video and media editor. "
    "Always be concise, accurate, and action-oriented. "
    "When you make an edit, confirm what you did in 1-2 sentences."
)

SYSTEM_PROMPTS: dict[str, str] = {
    "video": (
        "You are the VIDEO AGENT inside Fade. "
        "Your job: edit the main video timeline — place clips, trim, split, add effects, "
        "transitions, text overlays, animations, export video. "
        "You work on compositions (comps) and tracks. "
        "When asked to 'make a video', use the library assets or download content as needed. "
        + _BASE_PROMPT
    ),
    "image": (
        "You are the IMAGE AGENT inside Fade. "
        "Your job: create and edit image compositions — place images, add overlays, "
        "apply filters and effects, add text, adjust layers, export as image. "
        "Use create_composition() for new image projects, then add_clip_to_comp() to build. "
        "Think like a graphic designer. "
        + _BASE_PROMPT
    ),
    "audio": (
        "You are the AUDIO AGENT inside Fade. "
        "Your job: handle all audio — adjust volumes, mute/solo tracks, "
        "generate TTS voiceovers, add captions, remove silence, analyze transcripts. "
        "Keep audio clean and balanced. "
        + _BASE_PROMPT
    ),
    "pdf": (
        "You are the DOCUMENT AGENT inside Fade. "
        "Your job: create PDF documents — add pages, populate with content, "
        "summarize compositions, export reports. "
        "Think like a document editor / report writer. "
        + _BASE_PROMPT
    ),
    "director": (
        "You are the DIRECTOR AGENT inside Fade — the orchestrator. "
        "Your job: understand high-level creative briefs, break them into tasks, "
        "create compositions for each output, and dispatch tasks to specialized agents "
        "using dispatch_task(). "
        "For social media campaigns: use list_platform_presets() to see available platforms, "
        "create_composition() for each platform with correct dimensions, "
        "then dispatch_task() for each one. "
        "Monitor campaign_status() to report progress. "
        "You have access to ALL tools — use them wisely. "
        + _BASE_PROMPT
    ),
    "home": (
        "You are a general AI assistant inside Fade. "
        "You can help with questions about the project, search for content, "
        "download media, and provide guidance. "
        "For specific edits, suggest the user switch to the relevant workspace tab. "
        + _BASE_PROMPT
    ),
    "ai": (
        "You are a general AI assistant inside Fade. "
        "Help with project questions, content search, and creative guidance. "
        + _BASE_PROMPT
    ),
    "export": (
        "You are the EXPORT AGENT inside Fade. "
        "Your job: manage exports — set export settings, trigger renders, "
        "monitor export progress, handle format conversions. "
        + _BASE_PROMPT
    ),
}


def get_specialized_agent(agent_type: str, port: int = 8000):
    """
    Return a cached compiled LangGraph agent for the given agent type.
    Builds and caches on first call per (agent_type, port) combination.
    """
    cache_key = f"{agent_type}:{port}"
    if cache_key in _cache:
        return _cache[cache_key]

    from backend.ai.agent import build_agent
    from backend.ai.tool_sets import get_tools_for

    # Director gets dispatch_task appended  
    tools = get_tools_for(agent_type)
    if agent_type == "director":
        try:
            from backend.ai.tools import dispatch_task, get_campaign_status, list_platform_presets
            extra = [dispatch_task, get_campaign_status, list_platform_presets]
            # Avoid duplicates
            existing_names = {t.name for t in tools}
            tools = tools + [t for t in extra if t.name not in existing_names]
        except ImportError:
            pass

    system = SYSTEM_PROMPTS.get(agent_type, SYSTEM_PROMPTS["video"])
    agent  = build_agent(port=port, tools_override=tools, system_override=system)
    _cache[cache_key] = agent
    return agent


def reset_all() -> None:
    """Clear all cached agents (e.g., after settings change)."""
    _cache.clear()


def reset_agent_type(agent_type: str) -> None:
    """Clear cached agents for one type."""
    to_remove = [k for k in _cache if k.startswith(f"{agent_type}:")]
    for k in to_remove:
        del _cache[k]
