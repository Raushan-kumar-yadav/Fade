"""
Fade MCP Remote Client
======================
Connects to Fade's MCP SSE server and drives it with a configurable
remote LLM — llama.cpp over Tailscale, OpenAI, Claude (via OpenRouter),
Gemini, Groq, or any OpenAI-compatible endpoint.

This is "Option B": the LLM lives on a remote/Tailscale machine and
controls the local Fade editor through the MCP protocol over SSE.

Architecture
------------
  Remote machine (llama.cpp @ 100.88.241.12:808)
        ↓  OpenAI-compatible chat/completions
  MCPRemoteClient._build_llm()
        ↓  tool calls → MCP protocol
  Fade MCP SSE server  (http://localhost:7654/sse)
        ↓  HTTP calls
  Fade FastAPI backend (http://localhost:8000)
        ↓
  Timeline / Library / Effects / TTS / Export …
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable


 
PROVIDER_DEFAULTS: dict[str, dict] = {
    "llamacpp": {
        "label":   "llama.cpp (local / Tailscale)",
        "base_url": "http://100.88.241.12:808/v1",
        "api_key":  "none",
        "model":    "local-model",
        "needs_key": False,
    },
    "openai": {
        "label":   "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "api_key":  "",
        "model":    "gpt-4o-mini",
        "needs_key": True,
    },
    "claude": {
        "label":   "Claude (via OpenRouter)",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key":  "",
        "model":    "anthropic/claude-3-5-haiku",
        "needs_key": True,
    },
    "gemini": {
        "label":   "Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "api_key":  "",
        "model":    "gemini-2.0-flash",
        "needs_key": True,
    },
    "groq": {
        "label":   "Groq (fast inference)",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key":  "",
        "model":    "llama3-8b-8192",
        "needs_key": True,
    },
    "openrouter": {
        "label":   "OpenRouter (200+ models)",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key":  "",
        "model":    "mistralai/mistral-7b-instruct",
        "needs_key": True,
    },
    "custom": {
        "label":   "Custom OpenAI-compatible",
        "base_url": "http://localhost:11434/v1",
        "api_key":  "none",
        "model":    "llama3.2",
        "needs_key": False,
    },
}


 
@dataclass
class LLMConfig:
    provider:    str   = "llamacpp"
    base_url:    str   = "http://100.88.241.12:808/v1"
    api_key: str   = "none"
    model: str   = "local-model"
    temperature: float = 0.0
    timeout:     int   = 120

    @property
    def openai_base_url(self) -> str:
        """Ensure base_url ends with /v1 for OpenAI-compatible providers."""
        url = self.base_url.rstrip("/")
        if not url.endswith("/v1"):
            url += "/v1"
        return url

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "model": self.model,
            "temperature": self.temperature,
            "timeout":     self.timeout,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LLMConfig":
        valid = {k for k in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in valid})

    @classmethod
    def from_provider(cls, provider: str) -> "LLMConfig":
        """Create a config pre-filled with that provider's defaults."""
        defaults = PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["custom"])
        return cls(
            provider=provider,
            base_url=defaults["base_url"],
            api_key=defaults.get("api_key", "none"),
            model=defaults["model"],
        )

 
@dataclass
class TokenEvent:
    text: str

@dataclass
class ToolCallEvent:
    name: str
    args: dict

@dataclass
class ToolResultEvent:
    name: str
    result: str

@dataclass
class DoneEvent:
    final_text: str

@dataclass
class ErrorEvent:
    message: str

@dataclass
class ThinkingEvent:
    text: str    


 
class MCPRemoteClient:
     

    def __init__(
        self,
        mcp_sse_url: str = "http://127.0.0.1:7654/sse",
        llm_config: LLMConfig | None = None,
    ) -> None:
        self.mcp_sse_url  = mcp_sse_url
        self.llm_config   = llm_config or LLMConfig()
        self._tools: list[dict] = []
        self._session     = None
        self._cm_stack: list = []
        self.connected    = False

    #   Connection  

    async def connect(self) -> None:
        """Open SSE connection to Fade MCP server and fetch tool list."""
        if self.connected:
            return

        try:
            from mcp.client.sse import sse_client
            from mcp import ClientSession
        except ImportError:
            raise RuntimeError(
                "mcp package not installed. Run: pip install 'mcp>=2.0'"
            )

        read, write = await self._cm_enter(sse_client(self.mcp_sse_url))
        session = await self._cm_enter(ClientSession(read, write))
        await session.initialize()
        self._session = session

        tools_resp = await session.list_tools()
        self._tools = [self._mcp_to_openai(t) for t in tools_resp.tools]
        self.connected = True
        print(
            f"[MCPClient] Connected: {self.mcp_sse_url} | "
            f"{len(self._tools)} tools | LLM: {self.llm_config.provider}",
            flush=True,
        )

    async def _cm_enter(self, cm):
        val = await cm.__aenter__()
        self._cm_stack.append(cm)
        return val

    async def disconnect(self) -> None:
        for cm in reversed(self._cm_stack):
            try:
                await cm.__aexit__(None, None, None)
            except Exception:
                pass
        self._cm_stack.clear()
        self._session = None
        self.connected = False

    @staticmethod
    def _mcp_to_openai(tool) -> dict:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema or {
                    "type": "object", "properties": {}
                },
            },
        }

    #   Streaming chat  

    async def stream_chat(
        self,
        user_message: str,
        history: list[dict] | None = None,
        max_steps: int = 15,
    ):
        """
        Async generator that yields event objects:
          TokenEvent, ToolCallEvent, ToolResultEvent, DoneEvent, ErrorEvent
        """
        if not self.connected:
            try:
                await self.connect()
            except Exception as exc:
                yield ErrorEvent(message=f"Connection failed: {exc}")
                return

        messages: list[dict] = list(history or [])
        messages.append({"role": "user", "content": user_message})

        try:
            llm = self._build_llm()
        except Exception as exc:
            yield ErrorEvent(message=f"LLM init failed: {exc}")
            return

        for step in range(max_steps):
            try:
                resp = await asyncio.to_thread(
                    llm.chat.completions.create,
                    model=self.llm_config.model,
                    messages=messages,
                    tools=self._tools or None,
                    tool_choice="auto" if self._tools else None,
                    temperature=self.llm_config.temperature,
                    stream=False,
                )
            except Exception as exc:
                yield ErrorEvent(message=f"LLM call failed: {exc}")
                return

            msg = resp.choices[0].message
            content = msg.content or ""

            # Build message dict for history
            msg_dict: dict = {"role": "assistant", "content": content}
            if msg.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
            messages.append(msg_dict)

          
            thinking_text = ""
            answer_text   = content

       
            raw_reasoning = getattr(msg, "reasoning_content", None)
            if raw_reasoning:
                thinking_text = raw_reasoning.strip()

            # Method 2: <think>…</think> tags inside content
            if not thinking_text and content:
                import re as _re
                think_match = _re.search(r"<think>(.*?)</think>", content, _re.DOTALL)
                if think_match:
                    thinking_text = think_match.group(1).strip()
                    answer_text   = _re.sub(r"<think>.*?</think>", "", content, flags=_re.DOTALL).strip()

            if thinking_text:
                yield ThinkingEvent(text=thinking_text)

            if answer_text:
                yield TokenEvent(text=answer_text)

            # Update history with clean answer (no <think> tags)
            messages[-1]["content"] = answer_text

            # No tool calls → final answer
            if not msg.tool_calls:
                yield DoneEvent(final_text=answer_text)
                return

            # Execute tool calls via MCP
            for tc in msg.tool_calls:
                fn_name = tc.function.name
                try:
                    fn_args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    fn_args = {}

                yield ToolCallEvent(name=fn_name, args=fn_args)

                result_str = await self._call_tool(fn_name, fn_args)

                yield ToolResultEvent(name=fn_name, result=result_str)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_str,
                })

        yield DoneEvent(final_text="(max steps reached)")

    async def _call_tool(self, name: str, args: dict) -> str:
        try:
            result = await self._session.call_tool(name, args)
            if result.content:
                parts = [
                    c.text if hasattr(c, "text") else str(c)
                    for c in result.content
                ]
                return "\n".join(parts)
            return "✓ done"
        except Exception as exc:
            return f"[tool error] {name}: {exc}"

    #   LLM builder  

    def _build_llm(self):
        from openai import OpenAI
        cfg = self.llm_config
        return OpenAI(
            base_url=cfg.openai_base_url,
            api_key=cfg.api_key or "none",
            timeout=cfg.timeout,
        )

    #   Status  

    def status(self) -> dict:
        return {
            "connected": self.connected,
            "mcp_url": self.mcp_sse_url,
            "tool_count": len(self._tools),
            "llm": self.llm_config.to_dict(),
            "providers":   {k: v["label"] for k, v in PROVIDER_DEFAULTS.items()},
        }


#   Module-level singleton  
_client: MCPRemoteClient | None = None

def get_client() -> MCPRemoteClient:
    global _client
    if _client is None:
        _client = MCPRemoteClient()
    return _client

def replace_client(new_client: MCPRemoteClient) -> None:
    global _client
    _client = new_client
