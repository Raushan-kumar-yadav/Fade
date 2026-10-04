 
from __future__ import annotations

import json
from langchain_core.tools import tool


@tool
def get_current_plan() -> str:
    """Get the current active plan with all steps, their status, and progress.
    Use this to inspect the plan before deciding to skip, retry, or edit steps.
    Returns a JSON string with the full plan."""
    from backend.ai.task_store import get_active_plan
    plan = get_active_plan()
    if not plan:
        return "No active plan found."
    return json.dumps(plan.to_dict(), indent=2)


@tool
def skip_plan_step(step_id: str) -> str:
    """Skip a specific plan step without executing it.
    Use when a step is unnecessary for this particular goal.
    Args:
        step_id: The step_id to skip (get it from get_current_plan)
    """
    from backend.ai.task_store import skip_step
    ok = skip_step(step_id)
    if ok:
        return f"Step {step_id} marked as skipped. It will be bypassed during execution."
    return f"Could not skip step {step_id} — it may already be done or running."


@tool
def retry_plan_step(step_id: str) -> str:
    """Reset a failed or skipped step back to pending so it will be retried on next execution.
    Use after a step fails and you want the executor to try again.
    Args:
        step_id: The step_id to retry (get it from get_current_plan)
    """
    from backend.ai.task_store import reset_step
    ok = reset_step(step_id)
    if ok:
        return f"Step {step_id} reset to pending. It will be re-executed on next run."
    return f"Could not reset step {step_id} — it may be currently running."


@tool
def insert_plan_step(after_step_order: int, description: str, tool_name: str = "") -> str:
    """Insert a new step into the active plan after a given step order number.
    Existing steps are shifted up automatically.
    Use when the current plan is missing an important step.
    Args:
        after_step_order: The order number of the step AFTER which to insert (e.g. 3 inserts at position 4)
        description: What this new step should do
        tool_name: The tool to use for this step (optional, e.g. 'add_text_clip')
    """
    from backend.ai.task_store import get_active_plan, insert_step as _insert
    plan = get_active_plan()
    if not plan:
        return "No active plan to insert into."
    new_step = _insert(plan.plan_id, after_step_order, description, tool_name)
    return (f"Inserted new step {new_step.step_id} at order {new_step.order}: "
            f"'{description}' using tool '{tool_name or 'none'}'.")


@tool
def edit_plan_step(step_id: str, new_description: str = "", new_tool: str = "") -> str:
    """Edit the description or tool name of a PENDING step in the active plan.
    Only works on steps that haven't started yet.
    Args:
        step_id: The step_id to edit (get it from get_current_plan)
        new_description: New instruction text for the step (leave blank to keep current)
        new_tool: New tool name to use (leave blank to keep current)
    """
    from backend.ai.task_store import edit_step
    ok = edit_step(step_id,
                   description=new_description or None,
                   tool_name=new_tool or None)
    if ok:
        parts = []
        if new_description:
            parts.append(f"description -> '{new_description}'")
        if new_tool:
            parts.append(f"tool -> '{new_tool}'")
        return f"Step {step_id} updated: {', '.join(parts)}."
    return f"Could not edit step {step_id} — it may already be running or done."


@tool
def pause_current_plan() -> str:
    """Pause the current skill plan after the current step completes.
    The plan will stop at the next checkpoint and wait for the user to resume.
    Use when the user wants to review progress before continuing.
    """
    from backend.ai.task_store import get_active_plan, pause_plan
    plan = get_active_plan()
    if not plan:
        return "No active plan to pause."
    ok = pause_plan(plan.plan_id)
    if ok:
        done = sum(1 for s in plan.steps if s.status == "done")
        return (f"Plan '{plan.goal[:50]}' paused after {done}/{len(plan.steps)} steps. "
                f"Say 'resume' to continue.")
    return "Plan is not currently executing (may already be paused or done)."


@tool
def resume_current_plan() -> str:
    """Resume a paused skill plan from where it left off.
    Skips all already-done steps and continues from the next pending step.
    """
    from backend.ai.task_store import get_active_plan, resume_plan
    plan = get_active_plan()
    if not plan:
        return "No paused plan found."
    ok = resume_plan(plan.plan_id)
    if ok:
        pending = [s for s in plan.steps if s.status == "pending"]
        return (f"Plan '{plan.goal[:50]}' resumed. "
                f"{len(pending)} steps remaining.")
    return "Plan could not be resumed — it may not be paused."


@tool
def get_plan_summary() -> str:
    """Get a brief human-readable summary of the current plan progress.
    Use to tell the user what's been done and what remains.
    """
    from backend.ai.task_store import get_active_plan
    plan = get_active_plan()
    if not plan:
        return "No active plan."
    p = plan.progress
    lines = [
        f"Plan: {plan.goal[:80]}",
        f"Status: {plan.status} — {p['done']}/{p['total']} steps done ({p['percent']}%)",
        "",
    ]
    for s in sorted(plan.steps, key=lambda x: x.order):
        icon = {"done": "✓", "running": "⟳", "pending": "○",
                "skipped": "⊘", "failed": "✗"}.get(s.status, "?")
        lines.append(f"  {icon} [{s.order}] {s.description[:60]} ({s.tool_name})")
    return "\n".join(lines)


# All plan management tools as a list
PLAN_TOOLS = [
    get_current_plan,
    skip_plan_step,
    retry_plan_step,
    insert_plan_step,
    edit_plan_step,
    pause_current_plan,
    resume_current_plan,
    get_plan_summary,
]
