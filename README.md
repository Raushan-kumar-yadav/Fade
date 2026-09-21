# Echo — AI-Powered Video Editor 🎬✨

Echo is a next-generation, AI-first video editing platform that fuses traditional non-linear editing (NLE) with an intelligent **AI Director**. Built on a highly optimized stack of Electron, React, Python, and C++/Vulkan, Echo automates complex editing tasks, understands video semantics via vision models, and generates dynamic motion graphics on the fly.

![Electron](https://img.shields.io/badge/Electron-191970?style=for-the-badge&logo=Electron&logoColor=white)
![React](https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)
![C++](https://img.shields.io/badge/C++-00599C?style=for-the-badge&logo=c%2B%2B&logoColor=white)
![Vulkan](https://img.shields.io/badge/Vulkan-AA3322?style=for-the-badge&logo=Vulkan&logoColor=white)

---

## 🚀 Download & Run (No Installation Required)

> **Pre-built Windows x64 binary — just download and double-click.**

### 📦 [Download from Google Drive](https://drive.google.com/drive/folders/1ga8dbEF9xsMm5zsoMSc6cOVBdDtnOnT4?usp=sharing)

The Google Drive folder contains the complete `Echo-v1.0.0-win-x64.zip` distribution.

### Steps to run:

1. **Download** `Echo-v1.0.0-win-x64.zip` from the Google Drive link above
2. **Extract** the zip to any folder (e.g. `C:\Echo\`)
3. **Double-click** `Echo.exe` inside the extracted folder
4. The app will launch — no installation, no dependencies needed

> ⚠️ **Windows SmartScreen:** If Windows shows a security warning, click **"More info" → "Run anyway"**. The app is safe — it's just unsigned.

> 💡 All AI models (Kokoro TTS, Whisper) are bundled inside the zip. No internet required for core features.

---

## 🌟 Major Features

### 🤖 AI Director (LangGraph + LangChain)

The core of Echo is the AI Director — an intelligent agent running on a stateful graph (LangGraph). Instead of basic chat, the agent:

- Acts autonomously with access to dozens of timeline-manipulating tools (`split_clip`, `add_text_clip`, `apply_effect`, `add_transition`, and more).
- Reads live timeline state before making decisions, ensuring precise edits.
- Supports both local privacy-first models (Ollama: `llama3.2`, `qwen2.5`) and cloud LLMs (OpenAI, Gemini, **TokenRouter ✅ tested**).
- Automatically retries on transient API errors with exponential backoff.

### 🧠 Semantic Video Understanding

Echo doesn't just edit video — it _understands_ it using a multi-modal AI pipeline:

- **Vision Indexing (Ollama):** Extracts frames and runs local Ollama vision models (`moondream`, `llava`) to describe scenes in natural language — fully offline, no GPU cloud required.
- **Whisper Speech-to-Text:** Generates highly accurate, timestamped transcripts from audio tracks (bundled `small.pt` model, 461 MB).
- **ChromaDB Vector Search:** Embeds descriptions and transcripts into a local vector database for semantic clip retrieval.

### 🎞️ GPU-Accelerated C++ Rendering Engine

- **Vulkan & Skia Compositor:** A custom-built C++ headless compositor powers the timeline preview and export.
- **N-API Integration:** Bridges the C++ engine directly into Node.js (Electron) for zero-network-overhead frame rendering.
- **Nested Compositions:** Supports After Effects-style nested timelines compiled into a DAG for efficient GPU processing.

### 🎙️ Local Generative Media & WebComps

- **Kokoro Offline TTS:** Ultra-fast, local Text-to-Speech generating realistic voiceovers entirely offline (bundled fp16 + int8 ONNX models).
- **Auto B-Roll (`yt-dlp`):** AI autonomously fetches b-roll from YouTube based on script context.
- **WebComps:** AI generates pure HTML/CSS/JS motion graphics rendered frame-by-frame directly onto the timeline.
- **Image Generation (Stability AI ✅ tested):** AI generates images using Stability AI's REST API — photorealistic, anime, and cinematic styles supported.
- **Web Search:** Built-in news/web search with rate-limit retry for script research.

### 🖥️ Professional, Dockable UI

- **React 18 + Vite:** Lightning-fast frontend with a premium glassmorphism aesthetic.
- **Dockable Workspaces:** Fully resizable panels — Home, AI, Video, Export.
- **Real-time SSE:** Server-Sent Events keep the UI perfectly synchronized with the AI's backend actions.
- **Text Animator:** Per-character/word/line animations (opacity, scale, translateY, etc.) with easing.
- **Transitions:** CrossDissolve, SlideLeft, Wipe, Zoom, Fade between clips.
- **SkSL Effects:** Shader-based effects (vignette, glow, chromatic aberration) applied per-clip.

### 🔊 Audio Engine

- **Multi-track audio** with per-clip volume control.
- **Synchronized seek** — audio repositions correctly when scrubbing the timeline.
- **Clip-bound playback** — audio stops exactly when the clip ends, not when the source file ends.
- **Export muxing** — all audio tracks mixed with correct timing via FFmpeg filter_complex.

---

## 🏗️ System Architecture

Fade uses a highly decoupled, multi-process architecture:

1. **Frontend / Desktop Shell (Electron + React):** Handles local filesystem access and renders the UI.
2. **Backend / Orchestrator (Python + FastAPI):** Manages the AI agent, tools, timeline state, and streaming responses.
3. **Sandbox Worker (WorkerBus):** Heavy AI tasks (Whisper, Vision, TTS) run in an isolated Python process with automatic watchdog recovery.
4. **Fast-path Thread Pools:** Lightweight tasks bypass the heavy worker queue to keep the timeline snappy.
5. **Command Pattern History:** All edits use a strict Command Pattern for flawless Undo/Redo.

---

## 🗺️ Project Structure

```text
Echo/
├── backend/               # Python FastAPI, AI Agent (LangGraph), ChromaDB, PyAV
│   ├── ai/                # Agent, tools, video pipeline, web search
│   │   └── VideoSemantic/ # Frame-to-text indexing (Ollama vision models)
│   ├── encoder/           # FFmpeg export / audio muxing
│   ├── rendering/         # Skia-based compositor nodes
│   ├── tools/generators/  # Image generators (Stability AI, Gemini, ComfyUI)
│   └── routers/           # FastAPI route handlers
├── renderer/              # C++ Vulkan/Skia Headless Compositor (N-API bindings)
├── electron/              # Electron Main process & Preload scripts
├── src/                   # React Frontend (Workspaces, Components, API hooks)
│   └── workspaces/
│       └── viewport/      # Audio engine, WebComp sync, viewport widget
├── AIModels/              # Bundled AI models (Kokoro TTS, Whisper)
├── .env.example           # All environment variable templates with comments
└── index.html             # Electron window template
```

---

## 🛠️ Development Setup

### Prerequisites

- Node.js v18+
- Python 3.10+
- FFmpeg on system PATH

### 1. Clone & install

```bash
git clone https://github.com/Raushan-kumar-yadav/Echo.git
cd Echo
npm install
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 3. Run in development mode

```bash
npm run dev
```

### 4. Build production `.exe`

```bash
# Bundle Python backend
pyinstaller backend.spec --distpath pyinstaller-dist --clean --noconfirm

# Build Vite + Electron
npm run build

# Package with electron-builder
npx electron-builder build --win --publish never
```

---

## 🤖 AI Provider Setup

Echo supports multiple LLM providers for the AI Director.

> 💡 **Using the built `.exe`?** You don't need to edit `.env` manually.
> Open the app → click the **Settings ⚙️** icon (top-right) → **API Keys** tab.
> Enter your provider, API key, and model name there — they're saved automatically.

For development, set these in your `.env` file:

### ✅ TokenRouter (Tested & Recommended — Free tier available)

TokenRouter provides access to many frontier models via a single API key with token-based pricing. **This is the recommended provider for getting started quickly.**

1. Sign up at [tokenrouter.io](https://tokenrouter.io) and get your API key
2. Add to `.env`:
   ```env
   FADE_AI_PROVIDER=tokenrouter
   TOKENROUTER_API_KEY=your_key_here
   TOKENROUTER_BASE_URL=https://api.tokenrouter.io/v1
   # Default model (free tier):
   FADE_AI_MODEL=z-ai/glm-5.3-free
   ```
3. Other models you can use with TokenRouter:
   ```env
   FADE_AI_MODEL=gpt-4o-mini
   FADE_AI_MODEL=claude-3-5-haiku-20241022
   FADE_AI_MODEL=gemini-1.5-flash
   ```

### 🦙 Ollama (Local, Fully Offline)

Run models entirely on your machine — no API key, no internet after model download.

1. Install Ollama: [ollama.com/download](https://ollama.com/download)
2. Pull a model:
   ```bash
   ollama pull llama3.2        # recommended for tool-calling
   # or
   ollama pull qwen2.5         # strong alternative
   ollama pull gemma3          # lightweight option
   ```
3. Add to `.env`:
   ```env
   FADE_AI_PROVIDER=ollama
   # FADE_AI_MODEL=llama3.2   # optional — Echo auto-detects your best installed model
   ```
4. Echo automatically queries `http://localhost:11434` for available models and picks the best tool-capable one. No config needed if Ollama is running.

### 🌐 Other Cloud Providers

| Provider   | `.env` setting                | Key env var          |
| ---------- | ----------------------------- | -------------------- |
| OpenAI     | `FADE_AI_PROVIDER=openai`     | `OPENAI_API_KEY`     |
| Gemini     | `FADE_AI_PROVIDER=gemini`     | `GOOGLE_API_KEY`     |
| Anthropic  | `FADE_AI_PROVIDER=claude`     | `ANTHROPIC_API_KEY`  |
| Groq       | `FADE_AI_PROVIDER=groq`       | `GROQ_API_KEY`       |
| OpenRouter | `FADE_AI_PROVIDER=openrouter` | `OPENROUTER_API_KEY` |

---

## 🖼️ Image Generation Setup (Stability AI)

Echo uses **Stability AI** for AI image generation inside the editor. The AI Director can call `generate_image("prompt")` and the image lands directly in your library.

> 💡 **Using the built `.exe`?** Go to **Settings ⚙️ → Image Generation** tab — enter your Stability AI key and pick the model/style there. No `.env` file needed.

### ✅ Stability AI (Tested)

1. Get your API key: [platform.stability.ai/account/keys](https://platform.stability.ai/account/keys)
2. Add to `.env`:
   ```env
   STABILITY_API_KEY=sk-your_key_here
   ```
3. In the app: **Settings → Image Generation → Provider → Stability AI**
4. Optional model/style settings (also configurable in Settings UI):
   ```env
   # Model: core (default) | ultra | sd3
   # core   = Stable Image Core — fast, high quality, ~$0.003/image
   # ultra  = Stable Image Ultra — best quality, ~$0.008/image
   # sd3    = Stable Diffusion 3 — most controllable
   ```

The AI Director will automatically use Stability AI when you ask it to generate images:

```
"Generate a cinematic sunset background image"
"Create a photorealistic product shot of headphones"
```

---

## 🔍 Video Indexing Setup (Ollama Frame-to-Text)

Echo's **Semantic Video Understanding** extracts frames from imported videos and uses a local Ollama vision model to describe each scene in natural language. These descriptions are stored in ChromaDB and become searchable.

### How it works

```
Video file → extract frames (every 2 sec) → Ollama vision model → text descriptions
→ ChromaDB vector store → AI can search: "find the scene with the mountain"
```

### Setup

> 💡 **Using the built `.exe`?** Go to **Settings ⚙️ → Indexing** tab — choose Vision Provider (`Ollama` or `Gemini`) and set the model there. No `.env` file needed.

1. Install Ollama: [ollama.com/download](https://ollama.com/download)
2. Pull a vision model (choose one):
   ```bash
   ollama pull moondream          # recommended — fast, 1.7 GB, good accuracy
   ollama pull llava              # alternative — larger, slower, more detailed
   ollama pull llava-phi3         # lightweight alternative
   ```
3. That's it — **no `.env` changes needed**. Echo auto-detects available vision models in priority order: `moondream → llava → llava-phi3`.

### Optional: Use Gemini instead of Ollama for indexing

If you don't want to run Ollama locally, indexing can use Google Gemini Vision:

```env
GOOGLE_API_KEY=your_google_api_key
```

Then in the app: **Settings → Indexing → Vision Provider → Gemini**

### Triggering indexing

Indexing runs automatically when you import a video, or you can trigger it manually:

- Right-click any library clip → **"Index Video"**
- Ask the AI: `"Index my video so I can search scenes"`
- After indexing, ask: `"Find the scene where someone is talking at a desk"`

> ⚠️ **Note:** First-time indexing loads the vision model into RAM (~1.7 GB for moondream). Expect 30–90 seconds on first run; subsequent frames are fast.

---

## 📝 License

This project is licensed under the **MIT License**.
