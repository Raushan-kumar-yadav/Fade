 
from __future__ import annotations
import json
import asyncio
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from backend.ai.prompt_shield import shield_prompt

ai_router = APIRouter(tags=["ai"])

# ── Cancellation token ────────────────────────────────────────────────────────
# A simple asyncio.Event that is set when the user clicks Stop.
# The skill execution loop checks this between every yielded event.
_cancel_event = asyncio.Event()

# Module-level tool label map 
_TOOL_LABELS: dict[str, str] = {
    "get_timeline_state": "Reading timeline…",
    "get_library": "Scanning library…",
    "get_library_assets": "Scanning library…",
    "place_clip": "Placing clip…",
    "add_text_clip": "Adding text…",
    "add_shape_clip": "Drawing shape…",
    "split_clip": "Splitting clip…",
    "trim_clip": "Trimming clip…",
    "move_clip": "Moving clip…",
    "delete_clip": "Deleting clip…",
    "add_transition": "Adding transition…",
    "add_transitions_between_all_clips": "Adding transitions…",
    "apply_effect_to_clip": "Applying effect…",
    "download_videos": "Downloading footage…",
    "download_images": "Downloading images…",
    "schedule_download": "Scheduling download…",
    "generate_image": "Generating image…",
    "search_video_scenes": "Searching scenes…",
    "get_asset_context": "Reading asset…",
    "get_clip_context": "Reading clip…",
    "describe_clip": "Inspecting clip…",
    "describe_selected_clip": "Inspecting clip…",
    "get_timeline_context": "Reading context…",
    "create_news_video": "Building news video…",
    "create_webcomp": "Building WebComp…",
    "generate_tts": "Generating voice…",
    "check_job_status": "Checking job…",
    "animate_property": "Animating…",
    "apply_curve_preset": "Applying curve…",
    "search_news": "Searching news…",
    "find_free_overlay_track": "Finding overlay track…",
    "add_track": "Adding track…",
    "remove_silence": "Removing silence…",
    "generate_captions": "Generating captions…",
    "undo": "Undoing…",
    "redo": "Redoing…",
    # Phase 1 — Track control
    "solo_track": "Soloing track…",
    "lock_track": "Locking track…",
    "move_track": "Reordering track…",
    # Phase 2 — Masks
    "add_mask": "Adding mask…",
    "update_mask": "Updating mask…",
    "remove_mask": "Removing mask…",
    "list_masks": "Reading masks…",
    # Phase 3 — SVG
    "add_svg_clip": "Adding SVG clip…",
    # Phase 4 — Canvas
    "crop_canvas": "Cropping canvas…",
    # Phase 5 — Comp management
    "rename_composition": "Renaming comp…",
    "get_comp_layers": "Reading layers…",
    "update_comp_layer": "Updating layer…",
    "move_comp_layer": "Reordering layer…",
    # Phase 6 — PDF
    "create_pdf_doc": "Creating PDF doc…",
    "list_pdf_docs": "Listing PDF docs…",
    "list_pdf_pages": "Listing pages…",
    "add_pdf_page": "Adding page…",
    "delete_pdf_page": "Deleting page…",
    "reorder_pdf_pages": "Reordering pages…",
    # Phase 7 — Playback
    "play": "Starting playback…",
    "pause": "Pausing…",
    "set_playback_speed": "Setting speed…",
    "set_in_out_points": "Setting in/out…",
    # Phase 8 — Virality / social
    "analyze_virality": "Analyzing virality…",
    "get_social_connections": "Checking connections…",
    "get_youtube_videos": "Fetching YouTube videos…",
    # Phase 9 — Batch transform
    "transform_batch": "Batch transforming…",
}

def _tool_label(name: str) -> str:
    return _TOOL_LABELS.get(name, f"Running {name}…")

# Request models  

class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    port: int = 8000
    agent: str = "video"   # agent type: video | image | audio | pdf | director | home
    asset_id: Optional[str] = None   # dragged asset from library/timeline
    asset_type: Optional[str] = None  # "image" | "video" | "audio" — type of dragged asset

class TranscribeRequest(BaseModel):
    assetId: str
    model: str = "small"
    language: Optional[str] = None
    create_text_clips: bool = False
    track_index: int = 2
    fps: float = 30.0

class CreateVideoRequest(BaseModel):
    query: str                     # e.g. "today's top 10 tech news"
    scene_duration: int = 150      # frames per scene (150 = 5s @ 30fps)
    fps: float = 30.0
    port: int = 8000

#   /ai/status  

@ai_router.get("/status")
def ai_status():
    import os
    provider = os.environ.get("FADE_AI_PROVIDER", os.environ.get("FADE_AI_PROVIDER", "ollama"))
    model = os.environ.get("FADE_AI_MODEL", os.environ.get("FADE_AI_MODEL", ""))

    ollama_ok = False
    available_models: list[str] = []

    if provider == "ollama":
        try:
            import httpx
            r = httpx.get("http://localhost:11434/api/tags", timeout=3)
            available_models = [m["name"] for m in r.json().get("models", [])]
            ollama_ok = True
            if not model:
                from backend.ai.agent import _detect_ollama_model
                model = _detect_ollama_model()
        except Exception:
            ollama_ok = False
            model = model or "llama3.2 (Ollama not running)"

    return {
        "provider": provider,
        "model": model,
        "ready": True,
        "ollama_running":  ollama_ok,
        "available_models": available_models,
    }


@ai_router.post("/restart")
async def ai_restart():
    """Reset the cached agent so it rebuilds with current os.environ on next request.
    
    NOTE: Do NOT re-read .env here. _write_env_file() in project.py already
    updates os.environ immediately when settings are saved. Re-reading .env
    with load_dotenv in a PyInstaller build would use the wrong path and
    override the correct value, reverting the provider back to ollama.
    """
    import os
    try:
        from backend.ai.agent import _reset_agent
        from backend.ai.agent_registry import reset_all as _reset_registry
        _reset_agent()
        _reset_registry()
        provider = os.environ.get("FADE_AI_PROVIDER", "ollama")
        model = os.environ.get("FADE_AI_MODEL", "")
        return {"ok": True, "provider": provider, "model": model,
                "message": f"All agents will restart with provider '{provider}' on next message."}
    except Exception as e:
        return {"ok": False, "message": str(e)}

# /ai/chat   

@ai_router.post("/cancel")
async def ai_cancel():
    """Signal the backend to stop the current skill/plan execution."""
    _cancel_event.set()
    return {"ok": True}

@ai_router.post("/chat")
async def ai_chat(req: ChatRequest):
    from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

    async def event_stream():
        # Reset cancel flag for this new request
        _cancel_event.clear()
        try:
            # Prompt-injection shield  
            ok, safe_message, err = shield_prompt(req.message)
            if not ok:
                yield f"data: {json.dumps({'type': 'error', 'message': err})}\n\n"
                return
            scanned_message = safe_message

            #  keyword-based skill match  
            from backend.ai.skill_loader import skill_registry
            matched_skill = skill_registry.match(scanned_message)

            #   LLM skill classifier fallback  
            from backend.ai.intent_classifier import (
                classify_intent, Intent, intent_summary, route_request,
            )
            from backend.ai import task_store as _store
            active_plan = _store.get_active_plan()
            intent = classify_intent(scanned_message, has_active_plan=active_plan is not None)

             
            if not matched_skill and intent in (
                Intent.SIMPLE_EDIT, Intent.SIMPLE_QUERY, Intent.COMPLEX_TASK
            ):
                all_skills = [
                    skill_registry.get(s["name"])
                    for s in skill_registry.list_skills()
                ]
                all_skills = [s for s in all_skills if s]
                try:
                    from backend.ai.agent import _build_llm
                    llm_for_routing = _build_llm()
                    decision = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: route_request(scanned_message, all_skills,
                                              llm_for_routing, req.agent),
                    )
                    print(f"[AI Router] Route: {decision.route} ({decision.reason})", flush=True)
                    if decision.route == "skill" and decision.skill:
                        matched_skill = decision.skill
                    elif decision.route == "plan":
                        intent = Intent.COMPLEX_TASK
                    elif decision.route == "query":
                        intent = Intent.SIMPLE_QUERY
                    else:
                        intent = Intent.SIMPLE_EDIT
                except Exception as _e:
                    print(f"[AI Router] LLM routing skipped: {_e}", flush=True)

            if matched_skill:
                print(f"[AI Router] Skill matched: '{matched_skill.name}' — switching to "
                      f"checkpoint executor", flush=True)
                yield f"data: {json.dumps({'type': 'skill_detected', 'skill': matched_skill.name, 'version': matched_skill.version, 'steps': len(matched_skill.steps), 'message': f'Skill detected: {matched_skill.name} ({len(matched_skill.steps)} steps)'})}\n\n"

                from backend.ai.skill_executor import plan_from_skill, execute_skill_plan
                skill_plan = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: plan_from_skill(matched_skill, goal=scanned_message,
                                            agent_type=req.agent)
                )

                yield f"data: {json.dumps({'type': 'plan_created', 'plan': skill_plan.to_dict(), 'skill': matched_skill.name})}\n\n"


                total = len(skill_plan.steps)
                cancelled = False
                async for evt in execute_skill_plan(
                    plan=skill_plan,
                    skill=matched_skill,
                    port=req.port,
                ):
                    # Check cancel before forwarding each event
                    if _cancel_event.is_set():
                        cancelled = True
                        break

                    t = evt["type"]

                    if t == "step_start":
                        label = f"[{evt['order']}/{total}] {evt['name']} — {evt.get('tool', '')}…"
                        yield f"data: {json.dumps({'type': 'status', 'phase': 'skill', 'label': label})}\n\n"
                        yield f"data: {json.dumps({'type': 'step_start', 'order': evt['order'], 'step_id': evt['step_id'], 'name': evt['name'], 'tool': evt.get('tool', '')})}\n\n"

                    elif t == "step_done":
                        yield f"data: {json.dumps({'type': 'step_done', 'order': evt['order'], 'step_id': evt['step_id'], 'name': evt['name'], 'checkpoint': evt.get('checkpoint')})}\n\n"
                        if evt.get("checkpoint"):
                            chk = evt["checkpoint"]
                            yield f"data: {json.dumps({'type': 'status', 'phase': 'checkpoint', 'label': f'Checkpoint: {chk}'})}\n\n"

                    elif t == "step_failed":
                        yield f"data: {json.dumps({'type': 'step_failed', 'order': evt['order'], 'step_id': evt['step_id'], 'name': evt['name'], 'error': evt.get('error', '')})}\n\n"

                    elif t == "skill_done":
                        n = evt.get("steps_completed", total)
                        pretty = matched_skill.name.replace("_", " ").title()
                        yield f"data: {json.dumps({'type': 'skill_done', 'skill': matched_skill.name, 'steps_completed': n})}\n\n"
                        yield f"data: {json.dumps({'type': 'token', 'content': f'\n✅ **{pretty}** complete — {n} steps done.'})}\n\n"

                    elif t == "checkpoint":
                        lbl = evt.get("label", "")
                        yield f"data: {json.dumps({'type': 'status', 'phase': 'checkpoint', 'label': f'Checkpoint: {lbl}'})}\n\n"

                    # Forward live LLM output 
                    elif t == "token":
                        yield f"data: {json.dumps({'type': 'token', 'content': evt['content']})}\n\n"
                    elif t == "tool_call":
                        yield f"data: {json.dumps({'type': 'tool_call', 'name': evt['name'], 'args': evt.get('args', {})})}\n\n"
                    elif t == "tool_result":
                        yield f"data: {json.dumps({'type': 'tool_result', 'name': evt['name'], 'content': evt['content']})}\n\n"

                if cancelled:
                    yield f"data: {json.dumps({'type': 'token', 'content': '\n⏹ Stopped.'})}\n\n"
                yield f"data: {json.dumps({'type': 'status', 'phase': 'idle', 'label': ''})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

            #   Intent classification  
            print(f"[AI Router] Intent: {intent.value} ({intent_summary(intent)})", flush=True)

            #   Handle plan-management intents  
            if intent == Intent.CHECK_PROGRESS:
                if active_plan:
                    from backend.ai.planner import format_plan_for_display
                    plan_text = format_plan_for_display(active_plan)
                    yield f"data: {json.dumps({'type': 'token', 'content': plan_text})}\n\n"
                    yield f"data: {json.dumps({'type': 'plan_update', 'plan': active_plan.to_dict()})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'token', 'content': 'No active plan. Ask me to do something complex and I will create a step-by-step plan.'})}\n\n"
                yield f"data: {json.dumps({'type': 'status', 'phase': 'idle', 'label': ''})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

            if intent == Intent.CANCEL_TASK:
                if active_plan:
                    for step in active_plan.steps:
                        if step.status in ("pending", "running"):
                            _store.update_step_status(step.step_id, "skipped")
                    _store.update_plan_status(active_plan.plan_id, "failed")
                    yield f"data: {json.dumps({'type': 'token', 'content': f'Plan cancelled: {active_plan.goal}'})}\n\n"
                    yield f"data: {json.dumps({'type': 'plan_update', 'plan': _store.get_plan(active_plan.plan_id).to_dict()})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'token', 'content': 'No active plan to cancel.'})}\n\n"
                yield f"data: {json.dumps({'type': 'status', 'phase': 'idle', 'label': ''})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

            if intent == Intent.CONTINUE_TASK and active_plan:
                 
                next_step = active_plan.next_pending_step
                if next_step:
                    from backend.ai.planner import plan_to_pseudo_skill
                    from backend.ai.skill_executor import execute_skill_plan
                    _store.update_plan_status(active_plan.plan_id, "executing")
                    resume_plan = _store.get_plan(active_plan.plan_id)
                    resume_skill = plan_to_pseudo_skill(resume_plan)
                    yield f"data: {json.dumps({'type': 'plan_created', 'plan': resume_plan.to_dict()})}\n\n"
                    total_r = len(resume_plan.steps)
                    cancelled_r = False
                    async for evt in execute_skill_plan(plan=resume_plan, skill=resume_skill, port=req.port):
                        if _cancel_event.is_set():
                            cancelled_r = True
                            break
                        t = evt["type"]
                        if t == "step_start":
                            label = f"[{evt['order']}/{total_r}] {evt['name']} — {evt.get('tool', '')}..."
                            yield f"data: {json.dumps({'type': 'status', 'phase': 'skill', 'label': label})}\n\n"
                            yield f"data: {json.dumps({'type': 'step_start', 'order': evt['order'], 'step_id': evt['step_id'], 'name': evt['name'], 'tool': evt.get('tool', '')})}\n\n"
                        elif t == "step_done":
                            yield f"data: {json.dumps({'type': 'step_done', 'order': evt['order'], 'step_id': evt['step_id'], 'name': evt['name'], 'checkpoint': evt.get('checkpoint')})}\n\n"
                        elif t == "step_failed":
                            yield f"data: {json.dumps({'type': 'step_failed', 'order': evt['order'], 'step_id': evt['step_id'], 'name': evt['name'], 'error': evt.get('error', '')})}\n\n"
                        elif t == "skill_done":
                            yield f"data: {json.dumps({'type': 'skill_done', 'skill': 'auto_plan', 'steps_completed': evt.get('steps_completed')})}\n\n"
                            yield f"data: {json.dumps({'type': 'token', 'content': '\n\u2705 Plan complete.'})}\n\n"
                        elif t == "plan_halted":
                            _halt_msg = f"Plan {evt.get('status', 'halted')}. Say continue to resume."
                            yield f"data: {json.dumps({'type': 'token', 'content': _halt_msg})}\n\n"
                        elif t == "token":
                            yield f"data: {json.dumps({'type': 'token', 'content': evt['content']})}\n\n"
                        elif t == "tool_call":
                            yield f"data: {json.dumps({'type': 'tool_call', 'name': evt['name'], 'args': evt.get('args', {})})}\n\n"
                        elif t == "tool_result":
                            yield f"data: {json.dumps({'type': 'tool_result', 'name': evt['name'], 'content': evt['content']})}\n\n"
                    if cancelled_r:
                        yield f"data: {json.dumps({'type': 'token', 'content': '\n\u23f9 Stopped.'})}\n\n"
                    yield f"data: {json.dumps({'type': 'status', 'phase': 'idle', 'label': ''})}\n\n"
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    return
                else:
                    _store.update_plan_status(active_plan.plan_id, "done")
                    yield f"data: {json.dumps({'type': 'token', 'content': 'All steps are complete! The plan is done.'})}\n\n"
                    yield f"data: {json.dumps({'type': 'plan_update', 'plan': _store.get_plan(active_plan.plan_id).to_dict()})}\n\n"
                    yield f"data: {json.dumps({'type': 'status', 'phase': 'idle', 'label': ''})}\n\n"
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    return

            #   Complex task: generate plan then execute step-by-step  
            if intent == Intent.COMPLEX_TASK:
                yield f"data: {json.dumps({'type': 'status', 'phase': 'planning', 'label': 'Analysing goal and building plan...'})}\n\n"

                from backend.ai.planner import generate_plan_with_llm, format_plan_for_display, plan_to_pseudo_skill
                plan = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: generate_plan_with_llm(scanned_message, req.agent)
                )

                # Show the plan to the user
                plan_text = format_plan_for_display(plan)
                yield f"data: {json.dumps({'type': 'token', 'content': plan_text})}\n\n"
                yield f"data: {json.dumps({'type': 'plan_created', 'plan': plan.to_dict()})}\n\n"

 
                _risky = {"export_video", "delete_clip", "delete_track"}
                _flagged = sorted({s.tool_name for s in plan.steps if s.tool_name in _risky})
                if _flagged:
                    _store.update_plan_status(plan.plan_id, "paused")
                    _msg = (f"\n⚠️ This plan uses {', '.join(_flagged)}. "
                            f"Reply **approve** (or *continue*) to run it, or *cancel plan* to discard.")
                    yield f"data: {json.dumps({'type': 'token', 'content': _msg})}\n\n"
                    yield f"data: {json.dumps({'type': 'status', 'phase': 'idle', 'label': ''})}\n\n"
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    return

                 
                pseudo_skill = plan_to_pseudo_skill(plan)
                total = len(plan.steps)

                yield f"data: {json.dumps({'type': 'status', 'phase': 'skill', 'label': f'Executing {total}-step plan...'})}\n\n"

                from backend.ai.skill_executor import execute_skill_plan
                cancelled_c = False
                async for evt in execute_skill_plan(
                    plan=plan,
                    skill=pseudo_skill,
                    port=req.port,
                ):
                    if _cancel_event.is_set():
                        cancelled_c = True
                        break
                    t = evt["type"]
                    if t == "step_start":
                        label = f"[{evt['order']}/{total}] {evt['name']} — {evt.get('tool', '')}..."
                        yield f"data: {json.dumps({'type': 'status', 'phase': 'skill', 'label': label})}\n\n"
                        yield f"data: {json.dumps({'type': 'step_start', 'order': evt['order'], 'step_id': evt['step_id'], 'name': evt['name'], 'tool': evt.get('tool', '')})}\n\n"
                    elif t == "step_done":
                        yield f"data: {json.dumps({'type': 'step_done', 'order': evt['order'], 'step_id': evt['step_id'], 'name': evt['name'], 'checkpoint': evt.get('checkpoint')})}\n\n"
                    elif t == "step_failed":
                        yield f"data: {json.dumps({'type': 'step_failed', 'order': evt['order'], 'step_id': evt['step_id'], 'name': evt['name'], 'error': evt.get('error', '')})}\n\n"
                    elif t == "skill_done":
                        n = evt.get("steps_completed", total)
                        yield f"data: {json.dumps({'type': 'skill_done', 'skill': 'auto_plan', 'steps_completed': n})}\n\n"
                        yield f"data: {json.dumps({'type': 'token', 'content': f'\n\u2705 Plan complete \u2014 {n}/{total} steps done.'})}\n\n"
                    elif t == "token":
                        yield f"data: {json.dumps({'type': 'token', 'content': evt['content']})}\n\n"
                    elif t == "tool_call":
                        yield f"data: {json.dumps({'type': 'tool_call', 'name': evt['name'], 'args': evt.get('args', {})})}\n\n"
                    elif t == "tool_result":
                        yield f"data: {json.dumps({'type': 'tool_result', 'name': evt['name'], 'content': evt['content']})}\n\n"

                if cancelled_c:
                    yield f"data: {json.dumps({'type': 'token', 'content': '\n\u23f9 Stopped.'})}\n\n"
                yield f"data: {json.dumps({'type': 'status', 'phase': 'idle', 'label': ''})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

            #   Standard LangGraph execution  
            from backend.ai.agent_registry import get_specialized_agent
            agent = get_specialized_agent(req.agent, req.port)

            # Rebuild history
            messages = []
            for h in req.history:
                if h["role"] == "user":
                    messages.append(HumanMessage(content=h["text"]))
                else:
                    messages.append(AIMessage(content=h["text"]))

 
            final_message_text = scanned_message

            if req.asset_id:
                asset_filepath = None
                try:
                    from backend.state import _library as _lib
                    _ast = _lib.get(req.asset_id)
                    if _ast:
                        asset_filepath = getattr(_ast, "filepath", None)
                except Exception:
                    pass

                _atype = (req.asset_type or "").lower()
                _is_image = _atype == "image" or bool(
                    asset_filepath and
                    asset_filepath.lower().endswith(
                        (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")
                    )
                )

                if _is_image and asset_filepath:
                    # Image = face reference for tracking
                    final_message_text = (
                        scanned_message
                        + "\n\n[ATTACHED IMAGE]"
                        + f"\nreference_image_path: {asset_filepath}"
                        + f"\nasset_id: {req.asset_id}"
                        + "\nThis is a FACE REFERENCE image. DO NOT place it on the timeline."
                        + " Call track_face_with_image(clip_id=<active_clip>,"
                        + f" reference_image_path=\"{asset_filepath}\")."
                        + " Find the active clip with get_timeline_state() first."
                    )
                    print(f"[AI Router] Image ref injected: {asset_filepath}", flush=True)

                elif asset_filepath:
                    # Video / audio / other asset
                    final_message_text = (
                        scanned_message
                        + "\n\n[DROPPED ASSET]"
                        + f"\nasset_id: {req.asset_id}"
                        + f"\nfilepath: {asset_filepath}"
                        + f"\ntype: {req.asset_type or 'video'}"
                        + "\nUse asset_id for tracking (track_face_and_blur_by_asset)."
                        + " Do NOT place it on the timeline unless explicitly asked."
                    )
                    print(f"[AI Router] Asset injected: {req.asset_id[:8]}", flush=True)

                else:
                    final_message_text = (
                        scanned_message
                        + f"\n\n[DROPPED ASSET - asset_id: {req.asset_id}"
                        + f" | type: {req.asset_type or 'unknown'}]"
                    )

            messages.append(HumanMessage(content=final_message_text))

            # Emit initial thinking status
            yield f"data: {json.dumps({'type': 'status', 'phase': 'thinking', 'label': 'Thinking...'})}\n\n"

            last_phase = "thinking"
            current_step = None

            # Track which step we're executing (for plan-aware mode)
            if active_plan and active_plan.status == "executing":
                current_step = active_plan.next_pending_step
                if current_step and current_step.status == "running":
                    pass  # already marked running
                elif current_step:
                    _store.update_step_status(current_step.step_id, "running")

            # Retry loop: retries on 429 for up to 5 minutes, then gives up
            _attempt = 0
            _retry_start = None
            _MAX_RETRY_SECS = 300  # 5 minutes
            while True:
                _attempt += 1
                try:
                    # Stream events from LangGraph
                    async for event in agent.astream_events(
                        {"messages": messages},
                        version="v2",
                        config={"recursion_limit": 100},
                    ):
                        kind = event["event"]

                        # LLM token streaming
                        if kind == "on_chat_model_stream":
                            chunk = event["data"]["chunk"]
                            text = chunk.content if hasattr(chunk, "content") else ""
                            if text:
                                if last_phase != "responding":
                                    last_phase = "responding"
                                    yield f"data: {json.dumps({'type': 'status', 'phase': 'responding', 'label': 'Responding...'})}\n\n"
                                yield f"data: {json.dumps({'type': 'token', 'content': text})}\n\n"

                        # Tool call start
                        elif kind == "on_tool_start":
                            name = event.get("name", "")
                            args = event["data"].get("input", {})
                            label = _tool_label(name)
                            last_phase = "tool"
                            yield f"data: {json.dumps({'type': 'status', 'phase': 'tool', 'label': label, 'tool': name})}\n\n"
                            yield f"data: {json.dumps({'type': 'tool_call', 'name': name, 'args': args})}\n\n"

                        # Tool call end
                        elif kind == "on_tool_end":
                            name = event.get("name", "")
                            output = event["data"].get("output", "")
                            content = str(output) if not isinstance(output, str) else output
                            last_phase = "thinking"
                            yield f"data: {json.dumps({'type': 'status', 'phase': 'thinking', 'label': 'Thinking...'})}\n\n"
                            yield f"data: {json.dumps({'type': 'tool_result', 'name': name, 'content': content})}\n\n"

                    break  # success — exit retry loop

                except Exception as _rl_exc:
                    _rl_str = str(_rl_exc)
                    _is_rl = (
                        "429" in _rl_str
                        or "rate limit" in _rl_str.lower()
                        or "quota" in _rl_str.lower()
                        or "request limit" in _rl_str.lower()
                        or "too many requests" in _rl_str.lower()
                    )
                    if not _is_rl:
                        raise  # not a rate limit — propagate to outer except

                    import time as _time, re as _rex
                    _now = _time.monotonic()
                    if _retry_start is None:
                        _retry_start = _now
                    _elapsed = _now - _retry_start

                    # Give up after 5 minutes total
                    if _elapsed >= _MAX_RETRY_SECS:
                        raise RuntimeError(
                            f"Rate-limited for over 5 minutes ({_attempt} retries). "
                            "Please switch to a different model or wait and try again."
                        )

                    _m = _rex.search(r'retry.after[":\s]+([0-9]+)', _rl_str, _rex.IGNORECASE)
                    _wait = int(_m.group(1)) if _m else min(10 * _attempt, 60)
                    # Don't sleep past the 5-min deadline
                    _remaining = _MAX_RETRY_SECS - _elapsed
                    _wait = min(_wait, int(_remaining))

                    _elapsed_str = f"{int(_elapsed)}s"
                    print(f"[AI Router] Rate-limited (429), retrying in {_wait}s (attempt {_attempt}, elapsed {_elapsed_str}/300s)...", flush=True)
                    yield f"data: {json.dumps({'type': 'status', 'phase': 'thinking', 'label': f'Rate limited — retrying in {_wait}s... ({_elapsed_str}/5min)'})}\n\n"
                    await asyncio.sleep(_wait)
                    yield f"data: {json.dumps({'type': 'status', 'phase': 'thinking', 'label': f'Retrying (attempt {_attempt + 1})...'})}\n\n"


            # Post-execution: update plan step status  
            if current_step and active_plan:
                _store.update_step_status(current_step.step_id, "done")
                yield f"data: {json.dumps({'type': 'plan_step', 'step_id': current_step.step_id, 'status': 'done', 'description': current_step.description})}\n\n"
                
                # Refresh plan and check completion
                updated_plan = _store.get_plan(active_plan.plan_id)
                if updated_plan:
                    remaining = updated_plan.progress["pending"]
                    if remaining == 0:
                        _store.update_plan_status(updated_plan.plan_id, "done")
                        total = updated_plan.progress["total"]
                        done_msg = f"\n\n**Plan complete!** All {total} steps finished."
                        yield f"data: {json.dumps({'type': 'token', 'content': done_msg})}\n\n"
                    yield f"data: {json.dumps({'type': 'plan_update', 'plan': updated_plan.to_dict()})}\n\n"

            yield f"data: {json.dumps({'type': 'status', 'phase': 'idle', 'label': ''})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            import traceback
            err_str = str(e)
 
            if any(k in type(e).__name__ for k in ("Timeout", "TimeoutError")):
                msg = "The AI model took too long to respond. The free model may be busy -- please try again."
            elif "429" in err_str or "rate limit" in err_str.lower() or "quota" in err_str.lower():
                msg = "The AI model is rate-limited (429). Please wait a moment and try again."
            elif "connect" in err_str.lower() or "connection" in err_str.lower():
                msg = "Could not connect to the AI model. Check your internet connection."
            else:
                traceback.print_exc()
                msg = f"AI error: {err_str}"
            print(f"[AI Router] error: {msg}", flush=True)

 
            try:
                if current_step is not None and active_plan is not None:
                    _store.update_step_status(current_step.step_id, "failed", error=msg)
            except Exception:
                pass

            yield f"data: {json.dumps({'type': 'status', 'phase': 'idle', 'label': ''})}\n\n"
            yield f"data: {json.dumps({'type': 'error', 'message': msg})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@ai_router.get("/resume-queue")
def ai_resume_queue():
     
    from backend.ai.agent_jobs import pop_resume_messages
    return {"messages": pop_resume_messages()}


@ai_router.get("/pending-jobs")
def ai_pending_jobs():
    """Return all in-flight background jobs that the agent is waiting on."""
    from backend.ai.agent_jobs import pending_intents
    return {"jobs": pending_intents()}


#   /ai/transcribe  

@ai_router.post("/transcribe")
def ai_transcribe(req: TranscribeRequest):
     
    import httpx as _httpx

    # Resolve filepath from library
    base = f"http://127.0.0.1:{8000}"
    library = _httpx.get(f"{base}/library/assets", timeout=5).json()
    asset = next((a for a in library if a["assetId"] == req.assetId), None)
    if asset is None:
        from fastapi import HTTPException
        raise HTTPException(404, f"Asset {req.assetId!r} not in library")

    filepath = asset["filepath"]

    # Run Whisper
    from backend.ai.whisper_tool import transcribe, segments_to_srt
    segments = transcribe(filepath, model_name=req.model, language=req.language)
    srt = segments_to_srt(segments)

    # Optionally create text clips on the timeline
    if req.create_text_clips and segments:
        fps = req.fps
        created = []
        for seg in segments:
            start_frame = int(seg["start_s"] * fps)
            duration    = max(1, int((seg["end_s"] - seg["start_s"]) * fps))
            try:
                r = _httpx.post(f"{base}/clips/text", json={
                    "trackIndex": req.track_index,
                    "startFrame": start_frame,
                    "duration": duration,
                    "text": seg["text"],
                    "fontSize":   36.0,
                }, timeout=10)
                if r.is_success:
                    created.append(r.json().get("clipId"))
            except Exception as e:
                print(f"[Transcribe] text clip error: {e}", flush=True)

        return {"segments": segments, "srt": srt, "created_clips": created}

    return {"segments": segments, "srt": srt}


 
@ai_router.post("/create-video")
async def ai_create_video(req: CreateVideoRequest):
     
    async def event_stream():
        import threading
        import queue as queue_mod

        q: queue_mod.Queue = queue_mod.Queue()

        def progress_cb(msg: str):
            """Called synchronously from pipeline nodes."""
             
            if " — " in msg:
                stage, detail = msg.split(" — ", 1)
                stage = stage.replace("stage:", "").strip()
            else:
                stage = "running"
                detail = msg
            q.put({"type": "progress", "stage": stage, "detail": detail})

        def run_pipeline():
            try:
                from backend.ai.video_pipeline.pipeline import get_pipeline
                pipeline = get_pipeline()

                 
                initial_state = {
                    "query": req.query,
                    "scene_duration": req.scene_duration,
                    "fps": req.fps,
                    "port": req.port,
                    "progress": [],
                }

 
                final_state = None
                for step_output in pipeline.stream(initial_state):
                    # Each step_output is 
                    for node_name, delta in step_output.items():
                        new_progress = delta.get("progress", [])
                        for msg in new_progress:
                            progress_cb(msg)
                        if "summary" in delta:
                            final_state = delta

                summary = final_state.get("summary", "Pipeline complete.") if final_state else "Done."
                q.put({"type": "done", "summary": summary})
            except Exception as e:
                import traceback
                traceback.print_exc()
                q.put({"type": "error", "message": str(e)})
            finally:
                q.put(None)  # sentinel

         
        thread = threading.Thread(target=run_pipeline, daemon=True)
        thread.start()

         
        while True:
            try:
                item = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: q.get(timeout=300)
                )
            except Exception:
                break

            if item is None:
                break

            yield f"data: {json.dumps(item)}\n\n"

        thread.join(timeout=5)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

# Director - multi-agent parallel composition

class DirectorRequest(BaseModel):
    assets: list[str] = []
    intent: str = ""
    comp_types: list[str] = ["image", "video", "pdf"]
    publish_after: bool = False
    port: int = 8000


@ai_router.post("/director/run")
async def director_run(req: DirectorRequest):
    """Launch parallel agents (one per comp type). Returns SSE stream of progress."""
    from backend.ai.director import Director
    import os
    port = req.port or int(os.environ.get("BACKEND_PORT", 8000))

    async def stream():
        director = Director()
        async for event in director.run(
            assets=req.assets,
            intent=req.intent,
            port=port,
            comp_types=req.comp_types,
            publish_after=req.publish_after,
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@ai_router.get("/director/status/{session_id}")
async def director_status(session_id: str):
    """Poll status of all agents in a Director session."""
    from backend.ai.director import Director
    from fastapi import HTTPException
    result = Director().status(session_id)
    if result is None:
        raise HTTPException(404, f"Session {session_id!r} not found")
    return result


@ai_router.post("/director/cancel/{session_id}")
async def director_cancel(session_id: str):
    """Cancel all running agents in a Director session."""
    from backend.ai.director import Director
    from fastapi import HTTPException
    ok = Director().cancel(session_id)
    if not ok:
        raise HTTPException(404, f"Session {session_id!r} not found")
    return {"status": "cancelled", "session_id": session_id}



# Skills management

@ai_router.get('/skills')
def list_skills():
    ''''List all available skills and their trigger phrases.'''
    from backend.ai.skill_loader import skill_registry
    return {'skills': skill_registry.list_skills()}


@ai_router.get('/skills/{skill_name}')
def get_skill(skill_name: str):
    ''''Get full details of a skill including steps, rules, and checkpoints.'''
    from backend.ai.skill_loader import skill_registry
    from fastapi import HTTPException
    skill = skill_registry.get(skill_name)
    if not skill:
        raise HTTPException(404, f"Skill '{skill_name}' not found")
    return {'name': skill.name, 'version': skill.version, 'triggers': skill.triggers,
            'comp_type': skill.comp_type, 'agent_type': skill.agent_type,
            'description': skill.description, 'rules': skill.rules,
            'checkpoints': skill.checkpoints,
            'steps': [{'order': s.order, 'name': s.name, 'tool_name': s.tool_name,
                        'instruction': s.instruction} for s in skill.steps]}


@ai_router.post('/skills/reload')
def reload_skills():
    '''Hot-reload all skill .md files from disk without server restart.'''
    from backend.ai.skill_loader import skill_registry
    count = skill_registry.reload()
    return {'ok': True, 'skills_loaded': count,
            'skills': [s['name'] for s in skill_registry.list_skills()]}


class SkillImportRequest(BaseModel):
    filename: str   # original filename e.g. "my_skill.md"
    content:  str   # full .md file text


@ai_router.post('/skills/import')
def import_skill(req: SkillImportRequest):
    """Save a skill .md file to the skills directory and re-index."""
    import re as _re
    from fastapi import HTTPException
    from backend.ai.skill_loader import skill_registry, SKILLS_DIR, load_skill

 
    lower = req.content.lower()
    BLOCKED = [
        'ignore previous instructions', 'ignore all previous',
        'disregard the above', 'jailbreak', 'do anything now',
        'dan mode', '__import__', 'subprocess', 'os.system',
        'exec(', 'eval(', '<script', 'drop table',
    ]
    for pat in BLOCKED:
        if pat in lower:
            raise HTTPException(400, f"Blocked pattern detected: '{pat}'. Import rejected.")

    if not req.content.strip().startswith('---'):
        raise HTTPException(400, "Skill file must start with YAML frontmatter (---)")
    if '## Steps' not in req.content:
        raise HTTPException(400, "Skill file must contain a ## Steps section")

    # Sanitise filename  
    safe_name = _re.sub(r'[^a-z0-9_]', '_', req.filename.lower().removesuffix('.md'))
    if not safe_name:
        raise HTTPException(400, "Invalid filename")

    dest = SKILLS_DIR / f"{safe_name}.md"
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    dest.write_text(req.content, encoding='utf-8')

    # Parse to validate
    skill = load_skill(dest)
    if not skill:
        dest.unlink(missing_ok=True)
        raise HTTPException(422, "Skill file parsed but no valid skill found. Check frontmatter.")

    # Re-index registry
    skill_registry.reload()
    print(f"[SkillImport] Imported skill '{skill.name}' -> {dest}", flush=True)
    return {'ok': True, 'name': skill.name, 'steps': len(skill.steps),
            'triggers': skill.triggers[:3]}


@ai_router.delete('/skills/{skill_name}')
def delete_skill(skill_name: str):
    """Delete a skill .md file from disk and re-index."""
    import re as _re
    from fastapi import HTTPException
    from backend.ai.skill_loader import skill_registry, SKILLS_DIR

    # Sanitise
    safe = _re.sub(r'[^a-z0-9_]', '', skill_name.lower())
    if not safe:
        raise HTTPException(400, "Invalid skill name")

    target = SKILLS_DIR / f"{safe}.md"
    if not target.exists():
        raise HTTPException(404, f"Skill file '{safe}.md' not found")

    target.unlink()
    skill_registry.reload()
    print(f"[SkillDelete] Deleted skill '{safe}'", flush=True)
    return {'ok': True, 'deleted': safe}
