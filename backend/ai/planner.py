 
from __future__ import annotations
import json
import logging
from typing import Any

from backend.ai.task_store import TaskPlan, TaskStep, create_plan, add_step, update_plan_status

logger = logging.getLogger(__name__)


# Known tool names the planner can assign to steps
_KNOWN_TOOLS = [
    "get_timeline_state", "get_library_assets", "search_video_scenes",
    "download_videos", "download_images", "generate_image",
    "place_clip", "add_text_clip", "add_shape_clip",
    "find_free_overlay_track", "add_transitions_between_all_clips",
    "apply_effect_to_clip", "generate_tts", "generate_captions",
    "remove_silence", "animate_property", "apply_curve_preset",
    "create_webcomp", "add_webcomp_to_timeline",
    "search_news", "create_news_video",
    "split_clip", "trim_clip", "move_clip", "delete_clip",
    "set_text_content", "update_text_clip",
    "describe_clip", "get_clip_params",
    # Tracking & Privacy
    "start_track", "wait_for_track", "check_track_job",
    "list_tracks_for_clip", "delete_track",
    "add_blur_to_track", "add_follow_to_track",
    "track_and_blur_face", "track_and_blur_text",
]

PLANNER_SYSTEM = """\
You are a task planner for Fade, a professional video editor.
Given a user's creative goal, break it into ordered execution steps.
Each step should map to ONE primary tool call from the available tools.

RULES:
1. Always start with get_timeline_state or get_library_assets if you need context.
2. Order steps by dependency -- downloads before placements, etc.
3. Keep steps atomic -- one tool call per step.
4. Use find_free_overlay_track before any text/overlay placement.
5. End with add_transitions_between_all_clips if placing multiple clips.
6. Be specific in descriptions (include what to search for, what text to add, etc.)

Available tools: {tools}

Return ONLY valid JSON in this exact format (no markdown, no explanation):
{{
  "steps": [
    {{"description": "human-readable step description", "tool": "tool_name"}},
    {{"description": "...", "tool": "tool_name"}}
  ]
}}
"""


def generate_plan_with_llm(
    user_message: str,
    agent_type: str = "video",
    llm=None,
) -> TaskPlan:
    """Use LLM to generate a structured plan, then store it in the task store.
    
    Args:
        user_message: The user's creative goal / prompt.
        agent_type: Which agent type this plan is for.
        llm: Pre-built LLM instance (from _build_llm). If None, builds one.
    
    Returns:
        A TaskPlan with steps populated and stored in SQLite.
    """
    from langchain_core.messages import SystemMessage, HumanMessage

    if llm is None:
        from backend.ai.agent import _build_llm
        llm = _build_llm()

    system = PLANNER_SYSTEM.format(tools=", ".join(_KNOWN_TOOLS))
    
    print(f"[Planner] Generating plan for: {user_message[:80]}...", flush=True)

    try:
        response = llm.invoke([
            SystemMessage(content=system),
            HumanMessage(content=f"Goal: {user_message}"),
        ])
        
        raw = response.content.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        parsed = json.loads(raw)
        steps_data = parsed.get("steps", [])
        
        if not steps_data:
            raise ValueError("LLM returned empty steps list")
        
        print(f"[Planner] LLM generated {len(steps_data)} steps", flush=True)

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning("[Planner] LLM output parse failed: %s -- using fallback", e)
        print(f"[Planner] Parse failed: {e} -- generating fallback plan", flush=True)
        steps_data = _fallback_plan(user_message)

    # Create plan in SQLite
    plan = create_plan(goal=user_message, agent_type=agent_type)
    
    prev_step_id = None
    for i, step_data in enumerate(steps_data):
        desc = step_data.get("description", f"Step {i+1}")
        tool = step_data.get("tool", "")
        # Validate tool name
        if tool and tool not in _KNOWN_TOOLS:
            tool = ""  
        
        step = add_step(
            plan_id=plan.plan_id,
            description=desc,
            tool_name=tool,
            order=i,
            depends_on=prev_step_id if i > 0 else None,
        )
        prev_step_id = step.step_id
        print(f"[Planner]   Step {i}: {desc[:60]} (tool={tool})", flush=True)

    update_plan_status(plan.plan_id, "executing")
    
    # Reload to get steps attached
    from backend.ai.task_store import get_plan
    plan = get_plan(plan.plan_id)
    
    print(f"[Planner] Plan {plan.plan_id} ready with {len(plan.steps)} steps", flush=True)
    return plan


def _fallback_plan(user_message: str) -> list[dict]:
    """Generate a basic fallback plan when LLM parsing fails."""
    msg = user_message.lower()
    steps = []

    # Always start with context
    steps.append({"description": "Read current timeline state", "tool": "get_timeline_state"})
    steps.append({"description": "Check library assets", "tool": "get_library_assets"})

    if any(w in msg for w in ["news", "topic", "about"]):
        steps.append({"description": f"Create video: {user_message[:50]}", "tool": "create_news_video"})
    elif any(w in msg for w in ["download", "search", "find"]):
        steps.append({"description": "Download media content", "tool": "download_videos"})
        steps.append({"description": "Place downloaded clips on timeline", "tool": "place_clip"})
    
    if "caption" in msg or "subtitle" in msg:
        steps.append({"description": "Generate captions", "tool": "generate_captions"})
    if "music" in msg or "audio" in msg or "voiceover" in msg:
        steps.append({"description": "Generate voiceover", "tool": "generate_tts"})
    if "text" in msg or "title" in msg:
        steps.append({"description": "Find overlay track for text", "tool": "find_free_overlay_track"})
        steps.append({"description": "Add title text", "tool": "add_text_clip"})
    if "transition" in msg:
        steps.append({"description": "Add transitions between clips", "tool": "add_transitions_between_all_clips"})

    if not steps or len(steps) <= 2:
        # Very generic fallback
        steps.append({"description": f"Execute: {user_message[:80]}", "tool": ""})

    return steps


def format_plan_for_display(plan: TaskPlan) -> str:
    """Format a plan as a readable string for chat display."""
    lines = [f"**Plan: {plan.goal}**\n"]
    
    status_icons = {
        "pending": "[ ]",
        "running": "[~]",
        "done": "[x]",
        "failed": "[!]",
        "skipped": "[-]",
    }
    
    for step in sorted(plan.steps, key=lambda s: s.order):
        icon = status_icons.get(step.status, "[ ]")
        lines.append(f"{icon} {step.order + 1}. {step.description}")
    
    prog = plan.progress
    lines.append(f"\nProgress: {prog['done']}/{prog['total']} steps ({prog['percent']}%)")
    
    return "\n".join(lines)
