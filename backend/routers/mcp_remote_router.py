 

from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.ai.mcp_client import (
    MCPRemoteClient,
    LLMConfig,
    PROVIDER_DEFAULTS,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
    DoneEvent,
    ErrorEvent,
    ThinkingEvent,
    get_client,
    replace_client,
)

mcp_remote_router = APIRouter(prefix="/mcp-remote", tags=["mcp-remote"])


#   Request models  

class ConfigRequest(BaseModel):
    provider: str
    base_url: str
    api_key: str   = "none"
    model: str
    temperature: float = 0.0
    timeout: int   = 120
    mcp_sse_url: str   = "http://127.0.0.1:7654/sse"

class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


#   Status / providers  

@mcp_remote_router.get("/status")
async def get_status():
    client = get_client()
    return client.status()


@mcp_remote_router.get("/providers")
async def get_providers():
    """Return all supported providers with their default configs."""
    return {
        "providers": PROVIDER_DEFAULTS,
        "current": get_client().llm_config.to_dict(),
    }


#   Config + connect  

@mcp_remote_router.post("/config")
async def set_config(req: ConfigRequest):
    """
    Apply new LLM + MCP config.
    Disconnects the old client (if any) and creates a fresh one.
    Does NOT auto-connect — call /connect to open the SSE session.
    """
    client = get_client()
    was_connected = client.connected
    if was_connected:
        try:
            await client.disconnect()
        except Exception:
            pass

    new_cfg = LLMConfig(
        provider=req.provider,
        base_url=req.base_url,
        api_key=req.api_key,
        model=req.model,
        temperature=req.temperature,
        timeout=req.timeout,
    )
    new_client = MCPRemoteClient(
        mcp_sse_url=req.mcp_sse_url,
        llm_config=new_cfg,
    )
    replace_client(new_client)
    return {"ok": True, "config": new_cfg.to_dict()}


@mcp_remote_router.post("/connect")
async def connect():
    """Open SSE connection to Fade MCP server and load tool list."""
    client = get_client()
    if client.connected:
        return {"ok": True, "already_connected": True, "tool_count": len(client._tools)}
    try:
        await client.connect()
        return {"ok": True, "tool_count": len(client._tools)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp_remote_router.post("/disconnect")
async def disconnect():
    """Close the SSE connection."""
    client = get_client()
    await client.disconnect()
    return {"ok": True}


#   Chat (SSE streaming)  

@mcp_remote_router.post("/chat")
async def chat(req: ChatRequest):
    """
    Stream an agentic chat turn as Server-Sent Events.

    Event types (JSON):
      {"type": "token", "text": "..."}         LLM text chunk
      {"type": "tool_call", "name": "...", "args": {...}}
      {"type": "tool_result", "name": "...", "result": "..."}
      {"type": "done", "text": "..."}         final answer
      {"type": "error", "message": "..."}
    """
    client = get_client()

    async def event_stream():
        try:
            async for event in client.stream_chat(
                req.message,
                history=req.history,
            ):
                if isinstance(event, ThinkingEvent):
                    data = {"type": "thinking", "text": event.text}
                elif isinstance(event, TokenEvent):
                    data = {"type": "token", "text": event.text}
                elif isinstance(event, ToolCallEvent):
                    data = {"type": "tool_call", "name": event.name, "args": event.args}
                elif isinstance(event, ToolResultEvent):
                    data = {"type": "tool_result", "name": event.name, "result": event.result}
                elif isinstance(event, DoneEvent):
                    data = {"type": "done", "text": event.final_text}
                elif isinstance(event, ErrorEvent):
                    data = {"type": "error", "message": event.message}
                else:
                    continue

                yield f"data: {json.dumps(data)}\n\n"

        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        finally:
            yield "data: {\"type\": \"end\"}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
