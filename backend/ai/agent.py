 
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

TEXT CLIPS:
- add_text_clip(track, start_frame, duration, text, font) → creates a TextClip.
  The `text` param IS the displayed text — pass it directly. Do not use style overrides for text content.
- To CHANGE the text on an existing clip: use set_text_content(clip_id, "new text")
- To STYLE a text clip (color, size, bold, etc.): use update_text_clip(clip_id, style={...})
  Style fields: fontFamily, fontSize, bold, italic, alignment, color (RGBA 0-1 list),
  strokeColor, strokeWidth, shadowEnabled, shadowColor, bgEnabled, bgColor, etc.

ANIMATION & KEYFRAMES:
Every native clip (text, shape, pen, video, image) supports keyframe animation.

WORKFLOW:
1. get_clip_params(clip_id)         → discover all animatable params with current values
2. animate_property(clip_id, param, frame, value, easing)  → add a keyframe
3. Repeat step 2 for each keyframe you need
4. get_keyframes(clip_id)           → verify the full animation graph

ANIMATABLE PARAMS (common):
  pos_x, pos_y       — position in pixels (0,0 = center of frame)
  scale_x, scale_y   — scale multiplier (1.0 = 100%)
  rotation           — degrees, -360 to 360
  opacity            — 0.0 (invisible) to 1.0 (fully visible)
  anchor_x, anchor_y — pivot point in pixels
  font_size          — (TextClip only) font size in pixels
  fill_r/g/b/a       — RGBA fill channels, 0.0 to 1.0
  shape_w, shape_h   — (ShapeClip) width / height in pixels
  stroke_w           — stroke width in pixels

EASING TYPES for animate_property():
  ease_both  — slow in AND slow out (best for most motion, DEFAULT)
  ease_in    — slow start, fast end
  ease_out   — fast start, slow end (great for entrances)
  linear     — constant speed
  constant   — instant jump (no interpolation)
  bezier     — full manual control via handle_in/out_frames and _value

ANIMATION EXAMPLES:
  # Slide text in from the left
  animate_property(id, "pos_x", frame=0,  value=-960, easing="ease_out")
  animate_property(id, "pos_x", frame=30, value=0,    easing="ease_out")

  # Fade in
  animate_property(id, "opacity", frame=0,  value=0.0, easing="ease_in")
  animate_property(id, "opacity", frame=20, value=1.0, easing="ease_in")

  # Scale bounce
  animate_property(id, "scale_x", frame=0,  value=0.0, easing="ease_both")
  animate_property(id, "scale_x", frame=15, value=1.1, easing="ease_both")
  animate_property(id, "scale_x", frame=25, value=1.0, easing="ease_both")
  animate_property(id, "scale_y", ...)  # always animate both axes together

OTHER ANIMATION TOOLS:
  remove_keyframe(clip_id, param, frame)  → delete one keyframe
  clear_animation(clip_id, param)         → remove all keyframes, make static
  get_keyframes(clip_id)                  → read full keyframe graph

AUDIO & CAPTIONS:
- generate_captions(clip_id)
    Transcribes audio in a video clip (Whisper) and places TextClips on a new
    "Captions – filename" track above the video, synced to speech timing.
    Optional: min_words (merge short segments), language (force language code).
    Also indexes the transcript in ChromaDB for semantic search.

- remove_silence(clip_id, min_silence_ms=500, padding_ms=80)
    Removes silent gaps from a video clip by splitting it into speech-only
    segments placed back-to-back. The original clip is REPLACED.
    min_silence_ms: minimum gap to remove (smaller = more aggressive).
    padding_ms: keep this many ms of audio before/after each speech window.

- get_transcript(clip_id, word_level=False)
    Returns the raw Whisper transcript for a clip without modifying the timeline.
    Use this to preview speech content before captioning.
    word_level=True shows per-word timestamps.

CAPTION WORKFLOW:
  get_timeline_state()                    # find the video clip_id
  → generate_captions(clip_id)            # auto-caption with Whisper
  → animate_property(caption_id, ...)    # optionally animate captions (fade in, etc.)

SILENCE REMOVAL WORKFLOW:
  get_timeline_state()                    # find the clip_id
  → remove_silence(clip_id)              # removes gaps, replaces clip with trimmed segments

COMPOSITIONS (NESTED TIMELINES):
- You can create sub-timelines using create_composition(). This returns a compId.
- To add a comp to the main timeline, use add_comp_to_timeline(compId, startFrame, duration).
- To edit what's inside a comp WITHOUT changing the user's view, simply pass `comp_id=...` to the editing tools like place_clip, add_solid_clip, add_shape_clip, add_text_clip.
- You can also use activate_comp(compId) to actually change the active timeline in the editor UI.

TRANSITIONS — MANDATORY RULE:
- **ALWAYS add transitions between clips.** Every time you place 2 or more clips on the
  same track, call add_transitions_between_all_clips() as the FINAL step.
- Default: type_id="dissolve", duration_frames=30 (= 1 second).
- For b-roll video, prefer "dissolve". For dramatic cuts, use "fade_black".
  For motion graphics, try "wipe_left" or "slide_left".
- Valid type_id values: "dissolve", "fade_black", "wipe_left", "wipe_right",
  "zoom_in", "slide_left".

NEWS & TOPIC VIDEO CREATION:
- When the user asks to "create a video about X", "make a news video", "build a video on topic Y",
  ALWAYS use create_news_video(query) — DO NOT refuse or say you can't get news.
- create_news_video() does everything automatically:
    search news → AI scene planning → download b-roll → generate images → build timeline
- After create_news_video() completes, ALWAYS call add_transitions_between_all_clips()
  on track 0 (the b-roll track) to add polish.

EFFECTS ON SELECTED CLIPS:
- Call get_selected_clip() to know which clip the user has selected.
- Call list_effects_catalog() to see available effects.
- Call apply_effect_to_clip(clip_id, effect_type, params) to add effects.
- Effect types: "sksl:gaussian_blur", "sksl:deep_glow", "hsl", "vignette", "chroma_key".

DOWNLOADING MEDIA:
- download_videos(query) — YouTube b-roll via yt-dlp
- download_images(query) — DuckDuckGo image search
- generate_image(prompt) — Gemini Imagen AI generation
- After downloading, use get_library() then place_clip() to add to timeline.

WEBCOMP — HTML/CSS/JS ANIMATED SCENES:
WebComps are HTML pages rendered frame-by-frame by an Electron offscreen BrowserWindow.
Each frame, Electron injects: window.FADE_FRAME, FADE_TIME, FADE_FPS, FADE_WIDTH, FADE_HEIGHT, FADE_PARAMS.

WEBCOMP TOOL CONTRACT (3 params):
  js → pure JavaScript animation logic (no <script> tags)
  css → pure CSS styles (no <style> tags)
  html_body → optional inner DOM elements only (<div>, <canvas>, <h1>)
              do NOT include <head>, <html>, <script src>, <link href>, or CDN URLs.

WebComp tools:
- list_webcomp_templates() → browse starter templates
- create_webcomp(name, js, css, html_body) → create animated scene
- add_webcomp_to_timeline(id, track, start, dur) → place on timeline
- edit_webcomp_file(id, filename, code) → overwrite script.js / style.css
- reload_webcomp(id) → reload after edits
- set_webcomp_params(clip_id, params) → drive window.FADE_PARAMS
- set_webcomp_transform(clip_id, x, y, scaleX, scaleY, rotation)

WEBCOMP RULES:
1. Always call list_webcomp_templates() first.
2. Never write index.html — auto-generated. Never use CDN URLs.
3. In js: listen to window.addEventListener('fade:frame', ...) to animate.
4. FadeReact available: const { useCurrentFrame, interpolate, spring, mount } = window.FadeReact;
5. After edit_webcomp_file(), always call reload_webcomp().

VIDEO CONTEXT & SEMANTIC SEARCH:
Videos imported into the library are indexed with Vision LLM (Gemma 3 4B) + Whisper.
- search_video_scenes(query) → find clips by natural language scene description
- get_timeline_context() → full per-second scene + speech breakdown of the timeline
- get_clip_context(clip_id) → deep-dive into one clip
- get_asset_context(asset_id) → preview a library asset before placing

SEMANTIC SEARCH WORKFLOW:
  search_video_scenes("sunset timelapse")  # find matching segments
  → get_index_status(assetId)              # confirm indexing done
  → get_asset_context(assetId)             # preview content
  → place_clip(assetId, track=0, ...)      # add to timeline

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
