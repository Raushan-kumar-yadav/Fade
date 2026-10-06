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

# How much of a step's output is carried into later steps. Must be large enough
# to keep a full script and the assetIds / clipIds a step produced.
_RESULT_CHARS = 3000

# Older steps are shortened in the prompt so long plans don't grow without bound.
_RECENT_FULL_STEPS = 4
_OLD_RESULT_CHARS = 700

_READ_ONLY_PREFIXES = ("get_", "list_", "search_", "describe_", "check_", "read_",
                       "find_", "analyze_", "wait_", "test_")


def _is_read_only(tool_name: str) -> bool:
    """True for tools that only inspect state (they never change the project)."""
    return not tool_name or tool_name.startswith(_READ_ONLY_PREFIXES)


def _context_summaries(done_summaries: list[str]) -> list[str]:
    """Recent step results in full, older ones cut to their label + closing summary."""
    cutoff = len(done_summaries) - _RECENT_FULL_STEPS
    out = []
    for i, s in enumerate(done_summaries):
        if i < cutoff and len(s) > _OLD_RESULT_CHARS + 80:
            s = s[:80] + " … " + s[-_OLD_RESULT_CHARS:]
        out.append(s)
    return out


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


#   Single step runner  

async def _run_step(
    step: TaskStep,
    skill_step: SkillStep,
    skill: SkillDef,
    done_summaries: list[str],
    port: int,
    tools_override: list | None = None,
    goal: str = "",
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

    if tools_override:
        tools = tools_override
    else:
        # Full agent toolset: a step usually needs helpers besides its primary
        # tool (e.g. placing a clip needs the download/lookup that produces the id).
        tools = list(get_tools_for(skill.agent_type))
        if skill_step.tool_name not in {getattr(t, "name", "") for t in tools}:
            from backend.ai.tools import ALL_TOOLS
            tools += [t for t in ALL_TOOLS if getattr(t, "name", "") == skill_step.tool_name]

    system_prompt = skill.step_system_prompt(
        skill_step, _context_summaries(done_summaries), goal)
    graph = build_agent(port=port, tools_override=tools, system_override=system_prompt)

    try:
        import re as _rex
        import time as _time

        config = {"recursion_limit": 60}
        human = f"Step {skill_step.order} — {skill_step.name}: {skill_step.instruction}"
        if goal:
            human = f"User request:\n{goal}\n\nNow do ONLY this step.\n{human}"

        expects_change = not _is_read_only(skill_step.tool_name)
        result_chunks: list[str] = []
        called_tools: list[str] = []
        note = ""               # extra guidance appended when a step is re-run
        error_retried = False   # one automatic retry for a crashed attempt
        nudged = False          # one re-prompt when the agent did nothing
        _attempt = 0
        _retry_start = None
        _MAX_RETRY_SECS = 300  # 5 minutes

        while True:
            _attempt += 1
            state = {"messages": [HumanMessage(content=human + note)]}
            try:
                async for event in graph.astream_events(state, config=config, version="v2"):
                    kind = event.get("event", "")

                    if kind == "on_chat_model_stream":
                        chunk = event.get("data", {}).get("chunk")
                        text = getattr(chunk, "content", "") if chunk else ""
                        if isinstance(text, str) and text:
                            result_chunks.append(text)
                            yield {"type": "step_token", "content": text}

                    elif kind == "on_tool_start":
                        name = event.get("name", "")
                        args = event.get("data", {}).get("input", {})
                        called_tools.append(name)
                        yield {"type": "step_tool_call", "name": name, "args": args}

                    elif kind == "on_tool_end":
                        name = event.get("name", "")
                        output = str(event.get("data", {}).get("output", ""))
                        if output:
                            result_chunks.append(f"\n[tool:{name}] {output[:1500]}")
                        yield {"type": "step_tool_result", "name": name, "content": output[:400]}

            except Exception as _exc:
                _err = str(_exc)
                _low = _err.lower()
                _is_rl = (
                    "429" in _err
                    or "rate limit" in _low
                    or "quota" in _low
                    or "request limit" in _low
                    or "too many requests" in _low
                )
                # A re-run starts the step from scratch, so tell the agent what
                # may already have happened instead of letting it duplicate work.
                if any(not _is_read_only(t) for t in called_tools):
                    note = (
                        "\n\nNOTE: an earlier attempt at this step was interrupted after it "
                        "had already called: " + ", ".join(dict.fromkeys(called_tools)) + ". "
                        "Call get_timeline_state / get_library_assets first and only do what "
                        "is still missing — do not repeat work that already took effect."
                    )

                if not _is_rl:
                    if error_retried:
                        raise
                    error_retried = True
                    logger.warning("[SkillExecutor] Step %s crashed (%s) — retrying once",
                                   skill_step.name, _err[:200])
                    yield {"type": "step_retry", "wait": 0, "attempt": _attempt,
                           "label": f"Step hit an error ({_err[:120]}) — retrying once…"}
                    continue

                _now = _time.monotonic()
                if _retry_start is None:
                    _retry_start = _now
                _elapsed = _now - _retry_start

                if _elapsed >= _MAX_RETRY_SECS:
                    raise RuntimeError(
                        f"[SkillExecutor] Rate-limited for over 5 minutes ({_attempt} retries). "
                        "Please switch to a different model or wait and try again."
                    )

                _m = _rex.search(r'retry.after["\:\s]+([0-9]+)', _err, _rex.IGNORECASE)
                _wait = int(_m.group(1)) if _m else min(10 * _attempt, 60)
                _remaining = _MAX_RETRY_SECS - _elapsed
                _wait = min(_wait, int(_remaining))

                logger.warning("[SkillExecutor] Rate-limited (429), retrying in %ds (attempt %d, elapsed %ds/300s)...",
                               _wait, _attempt, int(_elapsed))
                yield {"type": "step_retry", "wait": _wait, "attempt": _attempt,
                       "label": f"Rate limited — retrying in {_wait}s... ({int(_elapsed)}s/5min)"}
                await asyncio.sleep(_wait)
                continue

            # Verify the step actually did something: a text-only answer to a step
            # that is supposed to change the project is not a completed step.
            acted = any(not _is_read_only(t) for t in called_tools)
            if expects_change and not acted and not nudged:
                nudged = True
                note = (
                    "\n\nNOTE: your previous attempt ended without calling any tool that "
                    "changes the project, so nothing happened. Describing the action does "
                    f"not perform it. Call {skill_step.tool_name}() (or the correct tool) now. "
                    "If this step is impossible or already satisfied, reply with one line "
                    "starting with 'SKIPPED:' and the reason."
                )
                yield {"type": "step_retry", "wait": 0, "attempt": _attempt,
                       "label": "No action was taken — asking the agent to run the tool…"}
                continue
            break

        result_str = "".join(result_chunks)[-_RESULT_CHARS:] or f"Step {skill_step.name} completed."
        if expects_change and not any(not _is_read_only(t) for t in called_tools):
            result_str = ("WARNING: this step made NO changes to the project "
                          "(no editing tool was called). " + result_str)[:_RESULT_CHARS]
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
            done_summaries.append(f"Step {s.order} ({s.tool_name}): {s.result[-_RESULT_CHARS:]}")

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
        async for ev in _run_step(task_step, skill_step, skill, done_summaries, port,
                                  goal=plan.goal):
            et = ev["type"]
            if et == "step_token":
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
            elif et == "step_retry":
                yield {"type": "token", "content": f"\n↻ {ev['label']}\n"}
        elapsed = round(time.time() - t0, 1)

        if success:
            update_step_status(task_step.step_id, "done", result=result)
            done_count += 1
            done_summaries.append(
                f"Step {task_step.order} ({skill_step.tool_name}): {result}"
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
            # Paused (not failed) so the finished steps are kept and the user can
            # say "continue" to retry from this step instead of starting over.
            update_plan_status(plan.plan_id, "paused")
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
            yield {"type": "token", "content": (
                f"\n⚠️ Step {task_step.order} ({skill_step.name}) failed: {result[:300]}\n"
                f"The {done_count} finished step(s) are saved. Reply **continue** to retry "
                f"from this step, or **cancel plan** to discard it.\n")}
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
