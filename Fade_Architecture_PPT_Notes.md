# Fade Architecture & Tech Stack (PPT Notes & Options)

This document provides a comprehensive breakdown of the Fade architecture. Each section has been expanded with multiple bullet points and "Speaker Options" so you can choose which details to highlight depending on your audience (e.g., highly technical engineers vs. general judges/investors).

---

## 1. The Core Tech Stack (High Priority)

_Start your presentation by establishing the overall foundation of the app. Choose the points that best fit your narrative._

### Frontend / Desktop Shell (The User Experience)

- **Electron Container:** We chose Electron over a standard web app because video editing requires deep OS integration, raw local file system access, and the ability to spawn background Python processes without cloud upload bottlenecks.
- **React & Vite:** The UI is built with React 18 for high-performance reactivity. Vite provides lightning-fast hot-module replacement during development.
- **Custom UI Engine:** The interface uses a custom dockable, resizable panel system (via `react-resizable-panels`), styled with Vanilla CSS and Tailwind for a premium "glassmorphism" aesthetic.

### Backend / Orchestration (The Brains)

- **Python & FastAPI:** Acts as the high-performance bridge between the UI, the AI models, and the local file system. We use FastAPI for its native `async` support, which is critical for streaming AI responses (SSE) without blocking.
- **ChromaDB:** A local vector database embedded in the backend to store semantic embeddings of video scenes and audio transcripts for lightning-fast natural language search.

### Rendering Engine (The Muscle)

- **C++ Headless Compositor:** A custom rendering engine written in C++ that leverages **Vulkan/Skia** for high-performance, GPU-accelerated video compositing, transitions, and frame extraction.
- **Node-Addon-API (N-API):** We use this to bridge our C++ rendering engine directly into the Node.js (Electron) environment, allowing the frontend to trigger heavy renders with zero network overhead.
- **FFmpeg & PyAV:** Used heavily on the Python side for fast, memory-efficient media decoding and streaming audio waveforms.

> **🗣️ Speaker Choice:** If the audience is highly technical, focus on the **C++ Vulkan / N-API bridge**. If they are more product-focused, highlight **Electron's local-first architecture** (no cloud upload waits).

---

## 2. AI Agent Architecture (High Priority)

_Explain how the "AI Director" thinks and acts. This separates Fade from standard editors._

- **Stateful Graphs (LangGraph + LangChain):** The agent isn't just a simple chatbot. It operates as a cyclical state graph. It can think, execute a tool, observe the result, and decide if it needs to take further action to complete the user's request.
- **Agnostic LLM Support:** Built on LangChain, the agent supports local models via **Ollama** (e.g., `llama3.2`, `gemma3`) for total privacy, as well as cloud models (OpenAI, Anthropic, Gemini, Tabi).
- **Strict System Prompts:** The agent is given a strict set of rules. For example, it is hard-coded to _never_ guess a clip ID. It must always read the live timeline state first.
- **Tool-Calling Engine:** The agent has access to dozens of Python functions decorated with `@tool` (e.g., `split_clip`, `add_text_clip`, `apply_curve_preset`). These tools make HTTP requests to the FastAPI backend, which mutates the global timeline state and forces the React UI to re-render.

> **🗣️ Speaker Choice:** Highlight **LangGraph** to show you are using cutting-edge agentic workflows, not just basic LLM API calls.

---

## 3. How the Agent is "Aware" of Clips (Medium Priority)

_This is the "magic" of the application. Explain how the agent knows what is inside a video without eyes._

- **The Semantic Indexing Pipeline:** When a user drops a video into the library, it doesn't just sit there. The backend automatically spawns a background worker to extract frames every few seconds.
- **Vision Models (Ollama/Moondream/Gemma):** Extracted frames are passed to a local, quantized vision model which generates a rich text description of the visual scene (e.g., "A red car driving on a coastal highway").
- **Speech-to-Text (Whisper):** Simultaneously, the audio track is passed to Whisper to generate timestamped transcripts.
- **Vector Search & Retrieval:** Both the scene descriptions and the transcripts are embedded into **ChromaDB**. When the agent runs `search_video_scenes("sunset")`, it queries the database and gets the exact timestamps of matching scenes.
- **The Virtual Eyes (`describe_clip`):** Before making _any_ edit, the agent's system prompt forces it to run `describe_clip(clip_id)`. This tool acts as the agent's eyes, returning a JSON summary of the clip's state—including text content, styling, animations, or transcription—so it knows exactly what it is editing.

> **🗣️ Speaker Choice:** Focus on **ChromaDB + Whisper + Vision** to emphasize the multi-modal nature of the app. It's not just editing video; it's _understanding_ video.

---

## 4. Downloading, TTS, and Media Generation (Medium Priority)

_Explain how the application generates or sources content autonomously._

- **B-Roll Downloading (`yt-dlp`):** The agent has a tool called `download_videos(query)` which wraps `yt-dlp` to fetch high-quality b-roll directly from YouTube into the local library based on the user's script.
- **Image Generation:** Uses tools to generate AI images (via Gemini/Imagen) or fetch real images (via DuckDuckGo search API).
- **Local Text-to-Speech (Kokoro):** We integrated Kokoro, an incredibly fast, offline 82M-parameter TTS model. It generates highly realistic voiceovers in multiple languages instantly, without needing API keys or internet access.
- **WebComps (HTML/CSS/JS Animations):** The agent can generate pure code (HTML/CSS/JS) which is rendered frame-by-frame in an offscreen Electron window to create dynamic motion graphics and text animations on the timeline.
- **Asynchronous Fire-and-Forget:** To prevent the agent from freezing while waiting for a 1GB download, we built a `schedule_download()` tool. The task is sent to a background worker, the agent ends its turn, and the system automatically wakes the agent up when the file is ready.

> **🗣️ Speaker Choice:** Highlight **Local TTS (Kokoro)** to appeal to privacy/cost-conscious users, or highlight **WebComps** to show off how the AI can literally code motion graphics on the fly.

---

## 5. Worker Architecture & Concurrency (Low Priority / Advanced)

_Use this section if you get technical questions from judges about performance, UI freezing, or stability._

- **WorkerBus (Multiprocessing):** Heavy AI tasks (like Whisper transcription or Vision inference) run in a completely separate sandboxed Python process (`sandbox_worker.py`). If a heavy model hangs or spikes memory, it doesn't freeze the FastAPI server or the React UI.
- **Fast-path Thread Pools:** We engineered a split-queue system. Lightweight tasks (like streaming audio to draw UI waveforms via PyAV) are routed to a dedicated `ThreadPoolExecutor`. This guarantees the UI always feels snappy, because fast tasks never get stuck behind massive 3-hour video indexing jobs.
- **Streaming Memory (O(1) Footprint):** Our audio processing streams media frame-by-frame instead of loading everything into RAM. This prevents Out-Of-Memory (OOM) crashes even on massive, multi-gigabyte video files.
- **Watchdog Auto-Recovery:** A daemon thread constantly monitors the sandbox worker. If the worker crashes (e.g., from a CUDA error), the watchdog automatically restarts it in the background, ensuring system resilience without user intervention.

> **🗣️ Speaker Choice:** This is pure engineering flex. Use these points to prove the application is production-ready, highly optimized, and fault-tolerant.
