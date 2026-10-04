 
from __future__ import annotations
import json
import asyncio
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from backend.ai.prompt_shield import shield_prompt

ai_router = APIRouter(tags=["ai"])

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

@ai_router.post("/chat")
async def ai_chat(req: ChatRequest):
    from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

    async def event_stream():
        try:
            # ── Prompt-injection shield ──────────────────────────────
            ok, safe_message, err = shield_prompt(req.message)
            if not ok:
                yield f"data: {json.dumps({'type': 'error', 'message': err})}\n\n"
                return
            scanned_message = safe_message

            # ── Intent classification ────────────────────────────────
            from backend.ai.intent_classifier import classify_intent, Intent, intent_summary
            from backend.ai import task_store as _store

            active_plan = _store.get_active_plan()
            intent = classify_intent(scanned_message, has_active_plan=active_plan is not None)
            print(f"[AI Router] Intent: {intent.value} ({intent_summary(intent)})", flush=True)

            # ── Handle plan-management intents ───────────────────────
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
                # Resume: inject the plan context into the message
                next_step = active_plan.next_pending_step
                if next_step:
                    scanned_message = (
                        f"[CONTINUING PLAN: {active_plan.goal}]\n"
                        f"Current step ({next_step.order + 1}/{len(active_plan.steps)}): "
                        f"{next_step.description}\n"
                        f"Tool to use: {next_step.tool_name}\n"
                        f"Execute this step now."
                    )
                    _store.update_step_status(next_step.step_id, "running")
                    yield f"data: {json.dumps({'type': 'plan_step', 'step_id': next_step.step_id, 'status': 'running', 'description': next_step.description})}\n\n"
                else:
                    _store.update_plan_status(active_plan.plan_id, "done")
                    yield f"data: {json.dumps({'type': 'token', 'content': 'All steps are complete! The plan is done.'})}\n\n"
                    yield f"data: {json.dumps({'type': 'plan_update', 'plan': _store.get_plan(active_plan.plan_id).to_dict()})}\n\n"
                    yield f"data: {json.dumps({'type': 'status', 'phase': 'idle', 'label': ''})}\n\n"
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    return

            # ── Complex task: generate plan first ────────────────────
            if intent == Intent.COMPLEX_TASK:
                yield f"data: {json.dumps({'type': 'status', 'phase': 'planning', 'label': 'Creating plan...'})}\n\n"
                
                from backend.ai.planner import generate_plan_with_llm, format_plan_for_display
                plan = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: generate_plan_with_llm(scanned_message, req.agent)
                )

                # Show the plan to the user
                plan_text = format_plan_for_display(plan)
                yield f"data: {json.dumps({'type': 'token', 'content': plan_text})}\n\n"
                yield f"data: {json.dumps({'type': 'plan_created', 'plan': plan.to_dict()})}\n\n"

                # Start executing the first step
                first_step = plan.next_pending_step
                if first_step:
                    _store.update_step_status(first_step.step_id, "running")
                    yield f"data: {json.dumps({'type': 'plan_step', 'step_id': first_step.step_id, 'status': 'running', 'description': first_step.description})}\n\n"
                    scanned_message = (
                        f"[EXECUTING PLAN: {plan.goal}]\n"
                        f"Step {first_step.order + 1}/{len(plan.steps)}: "
                        f"{first_step.description}\n"
                        f"Tool to use: {first_step.tool_name}\n"
                        f"Execute this step now. After completing it, tell the user "
                        f"what you did and that they can say 'continue' for the next step."
                    )
                    active_plan = plan  # for step tracking below

            # ── Standard LangGraph execution ─────────────────────────
            from backend.ai.agent_registry import get_specialized_agent
            agent = get_specialized_agent(req.agent, req.port)

            # Rebuild history  
            messages = []
            for h in req.history:
                if h["role"] == "user":
                    messages.append(HumanMessage(content=h["text"]))
                else:
                    messages.append(AIMessage(content=h["text"]))
            messages.append(HumanMessage(content=scanned_message))

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

            # ── Post-execution: update plan step status ──────────────
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
                msg = "Rate limit reached on the AI model. Wait a moment and try again."
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

                # Run the graph synchronously in this thread
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

