 
from __future__ import annotations
import os
import json
from pathlib import Path
from typing import Annotated

 
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parents[2] / ".env"  # Fade/.env
    load_dotenv(_env_path, override=False)  
    print(f"[AI Agent] Loaded .env from {_env_path}", flush=True)
except ImportError:
    pass   

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from backend.ai.tools import ALL_TOOLS, set_port

#   State  

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]

 
#   Preferred models for tool-calling  

_PREFERRED_MODELS = [
    "qwen2.5",
    "qwen2.5:latest",
    "llama3.2",
    "llama3.2:latest",
    "llama3",
    "llama3:latest",
    "gemma3",
    "gemma3:latest",
    "mistral",
    "mistral:latest",
]


def _detect_ollama_model() -> str:
    """Query Ollama for installed models and pick the best one for tool-calling."""
    try:
        import httpx
        r = httpx.get("http://localhost:11434/api/tags", timeout=3)
        models = [m["name"] for m in r.json().get("models", [])]
        if not models:
            print("[AI Agent] Ollama has no models installed. Run: ollama pull llama3.2", flush=True)
            return "llama3.2"   

        # pick from preferred list
        for pref in _PREFERRED_MODELS:
            if pref in models:
                return pref
        # fallback: first available
        print(f"[AI Agent] Using first available Ollama model: {models[0]}", flush=True)
        return models[0]

    except Exception:
        print("[AI Agent] Ollama not running — defaulting to llama3.2. Start Ollama first.", flush=True)
        return "llama3.2"


def _build_llm():
    provider = os.environ.get("FADE_AI_PROVIDER", "ollama").lower()
    model_name = os.environ.get("FADE_AI_MODEL", "")

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        # Auto-detect which model is installed if not specified
        if not model_name:
            model_name = _detect_ollama_model()

        print(f"[AI Agent] Using Ollama model: {model_name}", flush=True)
        return ChatOllama(model=model_name, temperature=0)

    elif provider == "tabi":
        # tabitoken.com  
        from langchain_openai import ChatOpenAI
        key = os.environ.get("TABI_API_KEY", "").strip().strip('"')
        base_url = os.environ.get("TABI_BASE_URL", "https://tabitoken.com/v1").strip().strip('"')
        if not key:
            print("[AI Agent] WARNING: TABI_API_KEY not set in .env", flush=True)
        m = model_name or "claude-opus-4-8"
        print(f"[AI Agent] Using Tabi model: {m} via {base_url}", flush=True)
        return ChatOpenAI(
            model=m,
            temperature=0,
            api_key=key,
            base_url=base_url,
        )

    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            print("[AI Agent] WARNING: OPENAI_API_KEY not set in .env", flush=True)
        m = model_name or "gpt-4o-mini"
        print(f"[AI Agent] Using OpenAI model: {m}", flush=True)
        return ChatOpenAI(model=m, temperature=0, api_key=key or None)

    elif provider == "groq":
        from langchain_groq import ChatGroq
        key = os.environ.get("GROQ_API_KEY", "")
        if not key:
            print("[AI Agent] WARNING: GROQ_API_KEY not set in .env", flush=True)
        m = model_name or "llama3-8b-8192"
        print(f"[AI Agent] Using Groq model: {m}", flush=True)
        return ChatGroq(model=m, temperature=0, groq_api_key=key or None)

    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        key = os.environ.get("GOOGLE_API_KEY", "")
        if not key:
            print("[AI Agent] WARNING: GOOGLE_API_KEY not set in .env", flush=True)
        m = model_name or "gemini-1.5-flash"
        print(f"[AI Agent] Using Gemini model: {m}", flush=True)
        return ChatGoogleGenerativeAI(model=m, temperature=0, google_api_key=key or None)

    elif provider == "claude":
        from langchain_anthropic import ChatAnthropic
        key      = os.environ.get("ANTHROPIC_API_KEY", "").strip().strip('"')
        base_url = os.environ.get("ANTHROPIC_BASE_URL", "").strip().strip('"')
    
        if base_url and not base_url.startswith(("http://", "https://")):
            print(f"[AI Agent] WARNING: ANTHROPIC_BASE_URL doesn't look like a URL — ignoring it", flush=True)
            base_url = ""
        if not key:
            print("[AI Agent] WARNING: ANTHROPIC_API_KEY not set in .env", flush=True)
        m = model_name or "claude-3-5-haiku-20241022"
        print(f"[AI Agent] Using Claude model: {m}"
              + (f" via {base_url}" if base_url else " (api.anthropic.com)"), flush=True)
        kwargs = dict(model=m, temperature=0, anthropic_api_key=key or None)
        if base_url:
            kwargs["anthropic_api_url"] = base_url
        return ChatAnthropic(**kwargs)

    else:
        raise ValueError(f"Unknown FADE_AI_PROVIDER: {provider}")

# System prompt  

_SYSTEM = """\
You are the AI Director inside Fade, a professional video editor.
You have powerful tools to search the web, download media, generate images, and build timelines.

CORE RULES:
1. Always call get_timeline_state() first if you need clip IDs or frame numbers.
2. Explain what you are doing BEFORE calling tools, in plain language.
3. After tools complete, summarise the result clearly.
4. Never invent clipIds — always read them from get_timeline_state().
5. You DO have access to the internet via DuckDuckGo search. Never say you cannot search the web.

COMPOSITIONS (NESTED TIMELINES):
- You can create sub-timelines using create_composition(). This returns a compId.
- To add a comp to the main timeline, use add_comp_to_timeline(compId, startFrame, duration).
- To edit what's inside a comp WITHOUT changing the user's view, simply pass `comp_id=...` to the editing tools like place_clip, add_solid_clip, add_shape_clip, add_text_clip.
- You can also use activate_comp(compId) to actually change the active timeline in the editor UI. Use this if the user asks you to "open" or "go to" a specific timeline.

TRANSITIONS — MANDATORY RULE:
- **ALWAYS add transitions between clips.** Every time you place 2 or more clips on the
  same track, call add_transitions_between_all_clips() as the FINAL step.
- Default: type_id="dissolve", duration_frames=30 (= 1 second).
- For b-roll video, prefer "dissolve". For dramatic cuts, use "fade_black".
  For motion graphics, try "wipe_left" or "slide_left".
- Valid type_id values: "dissolve", "fade_black", "wipe_left", "wipe_right",
  "zoom_in", "slide_left".
- add_transitions_between_all_clips() is the easiest — it auto-detects all clip
  boundaries and adds transitions in a single call.
- Only use add_transition(clip_a_id, clip_b_id) when you need a DIFFERENT transition
  type between specific clips.

NEWS & TOPIC VIDEO CREATION:
- When the user asks to "create a video about X", "make a news video", "build a video on topic Y",
  ALWAYS use create_news_video(query) — DO NOT refuse or say you can't get news.
- create_news_video() does everything automatically:
    search news → AI scene planning → download b-roll → generate images → build timeline
- After create_news_video() completes, ALWAYS call add_transitions_between_all_clips()
  on track 0 (the b-roll track) to add polish.
- You can also use search_news(query) standalone if the user just wants to browse headlines.

EFFECTS ON SELECTED CLIPS:
- Call get_selected_clip() to know which clip the user has selected.
- Call list_effects_catalog() to see available effects (Gaussian Blur, HSL, Vignette, ChromaKey, Deep Glow, etc.)
- Call apply_effect_to_clip(clip_id, effect_type, params) to add effects.
- Call patch_clip_effect(clip_id, effect_id, params) to tweak parameters.
- Effect types use format: "sksl:gaussian_blur", "sksl:deep_glow", "hsl", "vignette", "chroma_key".

DOWNLOADING MEDIA:
- download_videos(query) — YouTube b-roll via yt-dlp
- download_images(query) — DuckDuckGo image search
- generate_image(prompt) — Gemini Imagen AI generation
- After downloading, use get_library() then place_clip() to add to timeline.
- After placing multiple clips, always call add_transitions_between_all_clips().

WEBCOMP — HTML/CSS/JS ANIMATED SCENES:
WebComps are HTML pages rendered frame-by-frame by an Electron offscreen BrowserWindow.
Each frame, Electron injects globals into the page:
  window.FADE_FRAME  — current frame (int, 0-indexed)
  window.FADE_TIME   — current time in seconds (float)
  window.FADE_FPS    — project fps
  window.FADE_WIDTH  — canvas width in pixels
  window.FADE_HEIGHT — canvas height in pixels
  window.FADE_PARAMS — runtime params from the inspector panel (object)
The page can listen for frame updates:
  window.addEventListener('fade:frame', (e) => { const {frame, time} = e.detail; ... });

WEBCOMP TOOL CONTRACT (3 params — that's all you write):
  js → pure JavaScript animation logic (no <script> tags)
  css → pure CSS styles (no <style> tags)
  html_body   → optional inner DOM elements only (<div>, <canvas>, <h1>, <video>)
                do NOT include <head>, <html>, <script src>, <link href>, or any CDN URLs.

The backend auto-generates a correct index.html and handles all file paths automatically.
Files are saved in the project folder (or ~/.fade as fallback) — you never need to know the path.

WebComp tools and when to use them:
- list_webcomp_templates() → browse available starter templates before creating
- create_webcomp(name, js, css, html_body) → create animated scene — backend owns index.html
- list_webcomps() → see all WebComp assets in the project library
- add_webcomp_to_timeline(id, track, start, dur) → place a WebComp clip on the timeline
- get_webcomp_clip_info(clip_id) → read clip transform, opacity, and param schema
- read_webcomp_file(id, filename) → read script.js / style.css / webcomp.json before editing
- edit_webcomp_file(id, filename, code) → overwrite script.js / style.css / webcomp.json only
- reload_webcomp(id) → reload the BrowserWindow so edits appear in preview
- set_webcomp_params(clip_id, params) → drive window.FADE_PARAMS (text, color, fontSize, etc.)
- set_webcomp_transform(clip_id, x, y, scaleX, scaleY, rotation) → move/scale/rotate on canvas
- set_webcomp_opacity(clip_id, opacity) → set transparency 0.0–1.0
- update_webcomp_meta(id, name, width, height, fps, duration_frames) → rename or resize
- delete_webcomp(id) → remove asset (delete timeline clips with delete_clip first)

WEBCOMP CREATION RULES:
1. Always call list_webcomp_templates() first to see what templates exist.
2. Provide ONLY js, css, and optionally html_body to create_webcomp(). Nothing else.
3. In js: listen to window.addEventListener('fade:frame', ...) to animate per-frame.
4. FadeReact available with no import: const { useCurrentFrame, interpolate, spring, mount } = window.FadeReact;
5. After create_webcomp(), always call add_webcomp_to_timeline() to place it.
6. After edit_webcomp_file(), always call reload_webcomp() so changes appear immediately.
7. webcomp.json declares the param schema — fields become sliders/pickers in the inspector.
   Format: { "params": [{ "id": "text", "label": "Title", "type": "text", "default": "Hello" }] }
   Supported param types: "text", "color", "number", "range", "select".
8. NEVER write index.html — it is auto-generated. NEVER use CDN URLs.
9. The canvas is always 1920×1080 at 30fps. Use CSS transforms for animation.

WEBCOMP TYPICAL WORKFLOW:
  list_webcomp_templates() # see what's available
  → create_webcomp("My Scene", js=..., css=...) # backend creates all files
  → add_webcomp_to_timeline(assetId, 0, 0, 150) # place on timeline (150 = 5 s)
  → set_webcomp_params(clipId, {"text": "Hello"}) # drive params
  → add_transitions_between_all_clips() # always add transitions

VIDEO CONTEXT & SEMANTIC SEARCH:
Videos imported into the library are automatically indexed in the background using a Vision LLM
(Gemma 3 4B) + Whisper. Once indexed, query them with plain English.

TOOLS:
- get_index_status(asset_id)
    Check if a video finished indexing. Status: not_started | pending | running | done | error.
    Always check before using search or context tools on a specific asset.

- search_video_scenes(query, top_k=5)
    Search ALL indexed library videos by natural language scene description.
    Returns: assetId, timestamp range (start_sec–end_sec), score, description.
    Use to find the right clip BEFORE placing it. e.g. "car crash", "crowd cheering at sunset".
    After finding a hit: confirm assetId via get_library(), then place_clip().

- get_timeline_context(format="txt")
    Full per-second scene + speech breakdown of EVERY video clip on the timeline.
    Use for: "summarise my video", "what's at 30 seconds", "does this edit flow well?".

- get_clip_context(clip_id, format="txt")
    Deep-dive into one clip: scene descriptions + transcript from inPoint→outPoint.
    Get clip_id from get_timeline_state() first.

- get_asset_context(asset_id, format="txt")
    Same as get_clip_context but for a library asset not yet on the timeline.
    Use to preview what a raw video contains before placing it.

SEMANTIC SEARCH WORKFLOW:
  search_video_scenes("sunset timelapse")  # find matching segments
  → get_index_status(assetId)              # confirm indexing done
  → get_asset_context(assetId)             # preview full content
  → place_clip(assetId, track=0, ...)      # add to timeline
  → add_transitions_between_all_clips()    # polish

RULES:
1. Use search_video_scenes() whenever user says "find a clip of X" or "find a scene where Y".
2. Always call get_index_status() before get_asset_context or get_clip_context.
3. If status is pending/running, tell user indexing is in progress — retry shortly.
4. get_timeline_context() is the best starting point for understanding the user's edit.
5. Never fabricate timestamps — always read them from context tools.

Current project context will be injected by the router.
"""

#   Graph builder  

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

#   Singleton  

_agent = None

def get_agent(port: int = 8000):
    global _agent
    if _agent is None:
        print("[AI Agent] Building agent graph...", flush=True)
        _agent = build_agent(port)
        print("[AI Agent] Ready.", flush=True)
    return _agent


def get_agent_llm(port: int = 8000):
    """Return the bare LLM instance (no tools bound). Used by the video pipeline."""
    set_port(port)
    return _build_llm()
