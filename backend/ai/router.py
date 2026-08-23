"""
backend/ai/router.py
FastAPI router for all AI endpoints.
Mount in main.py with:
    from backend.ai.router import ai_router
    app.include_router(ai_router, prefix="/ai")
"""
from __future__ import annotations
import json
import asyncio
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

ai_router = APIRouter(tags=["ai"])

# Request models  

class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []   
    port: int = 8000

class TranscribeRequest(BaseModel):
    assetId: str
    model: str = "small"
    language: Optional[str] = None
    create_text_clips: bool = False
    track_index: int = 2        
    fps: float = 30.0

#   /ai/status  

@ai_router.get("/status")
def ai_status():
    import os
    provider = os.environ.get("FADE_AI_PROVIDER", "ollama")
    model    = os.environ.get("FADE_AI_MODEL", "")

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

# /ai/chat   

@ai_router.post("/chat")
async def ai_chat(req: ChatRequest):
    """
    Stream the agent response as Server-Sent Events.
    Each event is a JSON line with one of:
        {"type": "token", "content": "..."}
        {"type": "tool_call", "name": "...", "args": {...}}
        {"type": "tool_result", "name": "...", "content": "..."}
        {"type": "done"}
        {"type": "error", "message": "..."}
    """
    from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

    async def event_stream():
        try:
            from backend.ai.agent import get_agent
            agent = get_agent(req.port)

            # Rebuild history  
            messages = []
            for h in req.history:
                if h["role"] == "user":
                    messages.append(HumanMessage(content=h["text"]))
                else:
                    messages.append(AIMessage(content=h["text"]))
            messages.append(HumanMessage(content=req.message))

            # Stream events from LangGraph
            async for event in agent.astream_events(
                {"messages": messages},
                version="v2",
            ):
                kind = event["event"]

                # LLM token streaming
                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    text = chunk.content if hasattr(chunk, "content") else ""
                    if text:
                        yield f"data: {json.dumps({'type': 'token', 'content': text})}\n\n"

                # Tool call start
                elif kind == "on_tool_start":
                    name = event.get("name", "")
                    args = event["data"].get("input", {})
                    yield f"data: {json.dumps({'type': 'tool_call', 'name': name, 'args': args})}\n\n"

                # Tool call end
                elif kind == "on_tool_end":
                    name = event.get("name", "")
                    output = event["data"].get("output", "")
                    content = str(output) if not isinstance(output, str) else output
                    yield f"data: {json.dumps({'type': 'tool_result', 'name': name, 'content': content})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

#   /ai/transcribe  

@ai_router.post("/transcribe")
def ai_transcribe(req: TranscribeRequest):
    """
    Transcribe audio from an asset using Whisper.
    If create_text_clips=True, creates TextClip objects on the timeline
    for each subtitle segment.
    Returns: {segments: [{start_s, end_s, text}], srt: str}
    """
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
                    "duration":   duration,
                    "text":       seg["text"],
                    "fontSize":   36.0,
                }, timeout=10)
                if r.is_success:
                    created.append(r.json().get("clipId"))
            except Exception as e:
                print(f"[Transcribe] text clip error: {e}", flush=True)

        return {"segments": segments, "srt": srt, "created_clips": created}

    return {"segments": segments, "srt": srt}
