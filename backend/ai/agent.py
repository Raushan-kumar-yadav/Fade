"""
backend/ai/agent.py
LangGraph ReAct agent that wraps all Fade editor tools.
Uses Ollama by default (local, free). Switch provider via env var:
    FADE_AI_PROVIDER=ollama   (default)   model: llama3.2 or qwen2.5
    FADE_AI_PROVIDER=openai               OPENAI_API_KEY required
    FADE_AI_PROVIDER=groq                 GROQ_API_KEY required
    FADE_AI_PROVIDER=gemini               GOOGLE_API_KEY required
"""
from __future__ import annotations
import os
import json
from typing import Annotated
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from backend.ai.tools import ALL_TOOLS, set_port

# ── State ─────────────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]

# ── LLM provider selection ────────────────────────────────────────────────────

def _build_llm():
    provider = os.environ.get("FADE_AI_PROVIDER", "ollama").lower()
    model_name = os.environ.get("FADE_AI_MODEL", "")

    if provider == "ollama":
        from langchain_ollama import ChatOllama
        m = model_name or "qwen2.5:latest"
        print(f"[AI Agent] Using Ollama model: {m}", flush=True)
        return ChatOllama(model=m, temperature=0)

    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        m = model_name or "gpt-4o-mini"
        return ChatOpenAI(model=m, temperature=0)

    elif provider == "groq":
        from langchain_groq import ChatGroq
        m = model_name or "llama3-8b-8192"
        return ChatGroq(model=m, temperature=0)

    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        m = model_name or "gemini-1.5-flash"
        return ChatGoogleGenerativeAI(model=m, temperature=0)

    else:
        raise ValueError(f"Unknown FADE_AI_PROVIDER: {provider}")

# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM = """\
You are the AI Director inside Fade, a professional video editor.
You can read and edit the user's timeline using the tools provided.

RULES:
1. Always call get_timeline_state() first if you need clip IDs or frame numbers.
2. Explain what you are doing BEFORE calling tools, in plain language.
3. After tools complete, summarise the result clearly.
4. If the user asks something you cannot do with the tools, say so honestly.
5. Never invent clipIds - always read them from get_timeline_state().
6. Whisper transcription is available via the /ai/transcribe endpoint; the user
   can ask you to add subtitles and you will use add_text_clip() with the results.

Current project context will be injected by the router.
"""

# ── Graph builder ─────────────────────────────────────────────────────────────

def build_agent(port: int = 8000):
    """Build and return the compiled LangGraph agent."""
    set_port(port)
    llm = _build_llm()
    llm_with_tools = llm.bind_tools(ALL_TOOLS)
    tool_node = ToolNode(ALL_TOOLS)

    def call_model(state: AgentState):
        messages = [SystemMessage(content=_SYSTEM)] + state["messages"]
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    def should_continue(state: AgentState):
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile()

# ── Singleton ─────────────────────────────────────────────────────────────────

_agent = None

def get_agent(port: int = 8000):
    global _agent
    if _agent is None:
        print("[AI Agent] Building agent graph...", flush=True)
        _agent = build_agent(port)
        print("[AI Agent] Ready.", flush=True)
    return _agent
