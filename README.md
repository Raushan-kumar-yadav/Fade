# Fade — AI-Powered Video Editor 🎬✨

Fade is a next-generation, AI-first video editing platform that fuses traditional non-linear editing (NLE) with an intelligent "AI Director". Built on a highly optimized stack of Electron, React, Python, and C++/Vulkan, Fade automates complex editing tasks, understands video semantics via vision models, and generates dynamic motion graphics on the fly.

![Fade Interface](https://img.shields.io/badge/UI-Glassmorphism-6c63ff?style=for-the-badge)
![Electron](https://img.shields.io/badge/Electron-191970?style=for-the-badge&logo=Electron&logoColor=white)
![React](https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)
![C++](https://img.shields.io/badge/C++-00599C?style=for-the-badge&logo=c%2B%2B&logoColor=white)
![Vulkan](https://img.shields.io/badge/Vulkan-AA3322?style=for-the-badge&logo=Vulkan&logoColor=white)

---

## 🌟 Major Features

### 🤖 AI Director (LangGraph + LangChain)
The core of Fade is the AI Director, an intelligent agent running on a stateful graph (LangGraph). Instead of basic chat, the agent:
- Acts autonomously with access to dozens of timeline-manipulating tools (`split_clip`, `add_text_clip`, `apply_curve_preset`).
- Reads live timeline state before making decisions, ensuring precise edits.
- Supports both local privacy-first models (Ollama: `llama3.2`, `gemma3`) and cloud LLMs (Claude, OpenAI, Gemini).

### 🧠 Semantic Video Understanding
Fade doesn't just edit video; it *understands* it using a multi-modal AI pipeline:
- **Vision Indexing:** Extracts frames and runs local quantized vision models (Ollama/Moondream) to describe scenes in natural language.
- **Whisper Speech-to-Text:** Generates highly accurate, timestamped transcripts from audio tracks.
- **ChromaDB Vector Search:** Embeds descriptions and transcripts into a local vector database. The AI can instantly retrieve clips matching concepts like *"a red car on a highway"* or *"when the speaker talks about AI"*.

### 🎞️ GPU-Accelerated C++ Rendering Engine
- **Vulkan & Skia Compositor:** A custom-built C++ headless compositor powers the timeline preview and export.
- **N-API Integration:** Bridges the C++ engine directly into Node.js (Electron), providing the React frontend with zero-network-overhead frame rendering.
- **Nested Compositions:** Supports After Effects-style nested timelines, compiled into a Directed Acyclic Graph (DAG) for efficient GPU processing.

### 🎙️ Local Generative Media & WebComps
- **Kokoro Offline TTS:** Ultra-fast, 82M-parameter local Text-to-Speech model generating realistic, multi-lingual voiceovers entirely offline.
- **Auto B-Roll (`yt-dlp`):** AI can autonomously fetch high-quality b-roll from YouTube based on script context.
- **WebComps:** The AI can generate pure HTML/CSS/JS code to create dynamic text animations and motion graphics, which are rendered frame-by-frame via offscreen Electron windows directly onto the timeline.

### 🖥️ Professional, Dockable UI
- **React 18 + Vite:** Lightning-fast frontend reactivity with a premium glassmorphism aesthetic.
- **Dockable Workspaces:** Fully resizable, customizable panels using `react-resizable-panels`. Tailored environments for:
  - 🏠 **Home:** Analytics and library indexing.
  - 🤖 **AI:** Agentic chat and timeline reasoning.
  - 🎥 **Video:** Core NLE timeline, properties, effects, and viewport.
  - 📤 **Export:** Output configurations for Shorts, Reels, 4K, etc.
- **Optimistic Updates & SSE:** Real-time Server-Sent Events (SSE) keep the UI perfectly synchronized with the AI's backend actions, with 60fps optimistic dragging and trimming.

---

## 🏗️ System Architecture

Fade uses a highly decoupled, multi-process architecture to guarantee UI responsiveness even during heavy AI inference:

1. **Frontend / Desktop Shell (Electron + React):** Handles local filesystem access and renders the UI.
2. **Backend / Orchestrator (Python + FastAPI):** Manages the AI agent, tools, timeline state, and streaming responses via `async` endpoints.
3. **Sandbox Worker (WorkerBus):** Heavy AI tasks (Whisper, Vision, TTS) run in a sandboxed, isolated Python process with automatic watchdog recovery. This ensures OOM errors or CUDA spikes never freeze the main editor.
4. **Fast-path Thread Pools:** Lightweight tasks (like PyAV audio waveform generation) bypass the heavy worker queue to keep the timeline snappy.
5. **Command Pattern History:** All edits utilize a strict Command Pattern, allowing flawless Undo/Redo across both user clicks and AI actions.

---

## 📦 Installation & Setup

### Prerequisites
- Node.js (v18+)
- Python 3.10+
- FFmpeg (added to system PATH)
- *Optional (for local TTS):* `espeak-ng` installed on system.

### 1. Clone the repository
```bash
git clone https://github.com/Raushan-kumar-yadav/Fade.git
cd Fade
```

### 2. Install Node Dependencies
```bash
npm install
```

### 3. Set up Python Environment
```bash
python -m venv .venv
# Activate venv:
# Windows: .venv\Scripts\activate
# Mac/Linux: source .venv/bin/activate

pip install -r requirements.txt
```

### 4. Install Kokoro (Local TTS) - Optional
```bash
pip install kokoro-onnx soundfile
```
*(Windows users must also install [espeak-ng](https://github.com/espeak-ng/espeak-ng/releases/download/1.52.0/espeak-ng.msi) for multilingual TTS support).*

### 5. Run in Development Mode
This single command concurrently starts Vite, compiles the Electron process, launches the Python backend, and opens the app.
```bash
npm run dev
```

---

## 🗺️ Project Structure

```text
Fade/
├── backend/               # Python FastAPI, AI Agent (LangGraph), ChromaDB, PyAV
├── renderer/              # C++ Vulkan/Skia Headless Compositor (N-API bindings)
├── electron/              # Electron Main process & Preload scripts
├── src/                   # React Frontend (Workspaces, Components, API hooks)
├── tools/                 # Scripts and utility tasks
└── index.html             # Electron window template
```

---

## 📝 License

This project is licensed under the **MIT License**.
