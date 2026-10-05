"""
skill_executor.py — Checkpoint-driven skill plan executor.

Runs a TaskPlan built from a SkillDef step-by-step.
Each step is a focused single-tool agent call.
Results are checkpointed in SQLite — safe to resume after crash/pause.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncIterator, Callable, Optional

from backend.ai.skill_loader import SkillDef, SkillStep
from backend.ai.task_store import (
    TaskPlan, TaskStep,
    create_plan, add_step,
    update_step_status, update_plan_status,
    get_plan,
)

logger = logging.getLogger(__name__)


# ── Plan builder ──────────────────────────────────────────────────────────────

def plan_from_skill(skill: SkillDef, goal: str, agent_type: str | None = None) -> TaskPlan:
    """Convert a SkillDef into a persisted TaskPlan with one TaskStep per skill step.

    If a plan for this goal+skill already exists and is not done/failed, it is
    returned as-is (enabling resume without duplicating steps).
    """
    from backend.ai.task_store import list_plans

    # Check for a resumable plan with the same skill
    for existing in list_plans(limit=10):
        if (existing.status in ("paused", "executing", "planning")
                and existing.goal == goal
                and getattr(existing, "_skill_name", None) == skill.name):
            logger.info("[SkillExecutor] Resuming existing plan %s", existing.plan_id)
            return existing

    plan = create_plan(goal=goal, agent_type=agent_type or skill.agent_type)
    # Tag with skill name via a special prefix in goal field (task_store has no skill_name col yet)
    # We encode it as a JSON prefix — backward-compatible
    plan.goal = goal  # keep original for display

    for ss in sorted(skill.steps, key=lambda x: x.order):
        add_step(
            plan_id=plan.plan_id,
            description=f"[{ss.name}] {ss.instruction[:120]}",
            tool_name=ss.tool_name,
            order=ss.order,
        )

    update_plan_status(plan.plan_id, "executing")
    # Reload to pick up steps
    reloaded = get_plan(plan.plan_id)
    return reloaded or plan


# ── Single step runner ────────────────────────────────────────────────────────

async def _run_step(
    step: TaskStep,
    skill_step: SkillStep,
    skill: SkillDef,
    done_summaries: list[str],
    port: int,
    tools_override: list | None = None,
):
    """Run one skill step, yielding SSE-style events as they happen.

    Yields dicts with type:
      step_token       – streamed LLM text
      step_tool_call   – tool being called
      step_tool_result – tool output
      step_ok          – step succeeded, payload: result str
      step_err         – step failed,     payload: error str
    """
    from backend.ai.agent import build_agent
    from backend.ai.tool_sets import get_tools_for
    from langchain_core.messages import HumanMessage

    READ_ONLY = {"get_timeline_state", "get_library_assets", "get_playback_state",
                 "get_current_viewport_image", "get_clip_info", "undo", "redo"}
    if tools_override:
        tools = tools_override
    else:
        all_tools = get_tools_for(skill.agent_type)
        allowed_names = READ_ONLY | {skill_step.tool_name}
        tools = [t for t in all_tools if getattr(t, "name", "") in allowed_names]
        if not tools:
            tools = get_tools_for(skill.agent_type)

    system_prompt = skill.step_system_prompt(skill_step, done_summaries)
    graph = build_agent(port=port, tools_override=tools, system_override=system_prompt)

    try:
        config = {"recursion_limit": 25}
        state = {"messages": [HumanMessage(content=skill_step.instruction)]}
        result_chunks: list[str] = []

        _dbg_event_count = 0
        async for event in graph.astream_events(state, config=config, version="v2"):
            kind = event.get("event", "")
            _dbg_event_count += 1

            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                text = getattr(chunk, "content", "") if chunk else ""
                if isinstance(text, str) and text:
                    result_chunks.append(text)
                    yield {"type": "step_token", "content": text}
                elif text:
                    # Non-string content (list of blocks, etc.)
                    print(f"[DBG _run_step] non-str content type={type(text).__name__} val={str(text)[:100]}", flush=True)

            elif kind == "on_tool_start":
                name = event.get("name", "")
                args = event.get("data", {}).get("input", {})
                yield {"type": "step_tool_call", "name": name, "args": args}

            elif kind == "on_tool_end":
                name = event.get("name", "")
                output = str(event.get("data", {}).get("output", ""))
                if output:
                    result_chunks.append(f"\n[tool:{name}] {output[:200]}")
                yield {"type": "step_tool_result", "name": name, "content": output[:400]}

        result_str = "".join(result_chunks)[:500] or f"Step {skill_step.name} completed."
        print(f"[DBG _run_step] DONE events={_dbg_event_count} tokens_chars={len(''.join(result_chunks))}", flush=True)
        yield {"type": "step_ok", "result": result_str}

    except Exception as e:
        logger.error("[SkillExecutor] Step %s failed: %s", skill_step.name, e)
        yield {"type": "step_err", "error": str(e)}


# ── Main executor ─────────────────────────────────────────────────────────────

async def execute_skill_plan(
    plan: TaskPlan,
    skill: SkillDef,
    port: int = 8000,
    emit_fn: Optional[Callable] = None,
) -> AsyncIterator[dict]:
    """Execute a skill plan step-by-step with checkpointing.

    Yields progress dicts suitable for SSE streaming.
    Skips steps already marked "done" (resume support).

    Args:
        plan:     TaskPlan built by plan_from_skill().
        skill:    The SkillDef driving execution.
        port:     Backend port for agent HTTP calls.
        emit_fn:  Optional callback(event_dict) for non-SSE callers.
    """
    def _emit(event: dict):
        if emit_fn:
            emit_fn(event)

    total_steps = len(plan.steps)
    done_summaries: list[str] = []

    # Pre-populate summaries from already-done steps (resume scenario)
    for s in sorted(plan.steps, key=lambda x: x.order):
        if s.status == "done" and s.result:
            done_summaries.append(f"Step {s.order} ({s.tool_name}): {s.result[:100]}")

    # Map plan steps → skill steps by order
    skill_step_map = {ss.order: ss for ss in skill.steps}

    _emit({"type": "skill_start", "skill": skill.name, "plan_id": plan.plan_id,
           "total_steps": total_steps, "version": skill.version})
    yield {"type": "skill_start", "skill": skill.name, "plan_id": plan.plan_id,
           "total_steps": total_steps}

    done_count = sum(1 for s in plan.steps if s.status == "done")

    for task_step in sorted(plan.steps, key=lambda x: x.order):
        # Resume: skip already done steps
        if task_step.status == "done":
            continue

      
        _live = get_plan(plan.plan_id)
        if _live and _live.status in ("paused", "failed", "done"):
            halted = {"type": "plan_halted", "plan_id": plan.plan_id, "status": _live.status}
            _emit(halted)
            yield halted
            return

        skill_step = skill_step_map.get(task_step.order)
        if not skill_step:
            logger.warning("[SkillExecutor] No skill step for order %d", task_step.order)
            continue

        # Emit step start
        event = {
            "type": "step_start",
            "plan_id": plan.plan_id,
            "step_id": task_step.step_id,
            "order": task_step.order,
            "name": skill_step.name,
            "tool": skill_step.tool_name,
            "progress": int(done_count / total_steps * 100),
        }
        _emit(event)
        yield event

        # Mark running in DB
        update_step_status(task_step.step_id, "running")

        # Run the step — forward tokens and tool events to the SSE stream
        t0 = time.time()
        success = False
        result = f"Step {skill_step.name} completed."
        _fwd_tokens = 0
        async for ev in _run_step(task_step, skill_step, skill, done_summaries, port):
            et = ev["type"]
            if et == "step_token":
                _fwd_tokens += 1
                if _fwd_tokens <= 3 or _fwd_tokens % 50 == 0:
                    print(f"[DBG execute_plan] fwd token #{_fwd_tokens}: {ev['content'][:30]!r}", flush=True)
                yield {"type": "token", "content": ev["content"]}
            elif et == "step_tool_call":
                yield {"type": "tool_call", "name": ev["name"], "args": ev.get("args", {})}
            elif et == "step_tool_result":
                yield {"type": "tool_result", "name": ev["name"], "content": ev["content"]}
            elif et == "step_ok":
                success = True
                result = ev["result"]
            elif et == "step_err":
                result = ev["error"]
        elapsed = round(time.time() - t0, 1)

        if success:
            update_step_status(task_step.step_id, "done", result=result)
            done_count += 1
            done_summaries.append(
                f"Step {task_step.order} ({skill_step.tool_name}): {result[:100]}"
            )

            # Check if this is a named checkpoint
            checkpoint_label = skill.checkpoints.get(task_step.order)
            cp_event = {
                "type": "step_done",
                "plan_id": plan.plan_id,
                "step_id": task_step.step_id,
                "order": task_step.order,
                "name": skill_step.name,
                "elapsed_s": elapsed,
                "progress": int(done_count / total_steps * 100),
                "checkpoint": checkpoint_label,
            }
            _emit(cp_event)
            yield cp_event

            if checkpoint_label:
                cp = {
                    "type": "checkpoint",
                    "label": checkpoint_label,
                    "step": task_step.order,
                    "plan_id": plan.plan_id,
                }
                _emit(cp)
                yield cp

        else:
            update_step_status(task_step.step_id, "failed", error=result)
            update_plan_status(plan.plan_id, "failed")
            err_event = {
                "type": "step_failed",
                "plan_id": plan.plan_id,
                "step_id": task_step.step_id,
                "order": task_step.order,
                "name": skill_step.name,
                "error": result,
            }
            _emit(err_event)
            yield err_event
            # Stop on failure  
            return

    # All steps done
    update_plan_status(plan.plan_id, "done")
    final_event = {
        "type": "skill_done",
        "plan_id": plan.plan_id,
        "skill": skill.name,
        "steps_completed": done_count,
        "progress": 100,
    }
    _emit(final_event)
    yield final_event
    print(f"[SkillExecutor] Skill '{skill.name}' completed — {done_count}/{total_steps} steps",
          flush=True)
