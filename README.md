# Fade (Echo) - AI-Powered Professional Media Editor

![Electron](https://img.shields.io/badge/Electron_29-191970?style=for-the-badge&logo=Electron&logoColor=white)
![React](https://img.shields.io/badge/React_18-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)
![TypeScript](https://img.shields.io/badge/TypeScript_5-007ACC?style=for-the-badge&logo=typescript&logoColor=white)
![Python](https://img.shields.io/badge/Python_3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)
![C++](https://img.shields.io/badge/C++20-00599C?style=for-the-badge&logo=c%2B%2B&logoColor=white)
![Vulkan](https://img.shields.io/badge/Vulkan-AA3322?style=for-the-badge&logo=Vulkan&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-2E86AB?style=for-the-badge)

> A next-generation, AI-first professional video and media editor. Five-layer architecture:
> **Electron shell -> React UI -> Python FastAPI backend -> C++20/Vulkan GPU renderer**,
> all orchestrated by a **hierarchical multi-agent AI system**.

### Download Pre-built Binary

No build required. Download the self-contained Windows executable:

**Google Drive:** https://drive.google.com/drive/folders/10WzWDuEOPObGmxKkgonT9sPAAYzh8YUw?usp=sharing

Extract and double-click `Echo.exe`. All models and dependencies are bundled.
If Windows SmartScreen warns, click **More info -> Run anyway**.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Software Architecture](#2-software-architecture)
3. [Layer 1 - Electron Shell](#3-layer-1--electron-shell)
4. [Layer 2 - React Frontend](#4-layer-2--react-frontend)
5. [Layer 3 - Python FastAPI Backend](#5-layer-3--python-fastapi-backend)
6. [Layer 4 - C++20 Renderer (Vulkan + Skia)](#6-layer-4--c20-renderer)
7. [Layer 5 - N-API Bridge (C++ <-> Node.js)](#7-layer-5--n-api-bridge)
8. [Multi-Agent AI System](#8-multi-agent-ai-system)
9. [Media Pipeline (FFmpeg + HW Decode)](#9-media-pipeline)
10. [Library and Asset Uploading](#10-library--asset-uploading)
11. [Animation and Expression Engine](#11-animation--expression-engine)
12. [PDF and Document Engine](#12-pdf--document-engine)
13. [WebComp - Live HTML Compositions](#13-webcomp--live-html-compositions)
14. [Export Pipeline](#14-export-pipeline)
15. [Technology Stack Summary](#15-technology-stack-summary)
16. [Project Structure](#16-project-structure)
17. [Getting Started (Development)](#17-getting-started-development)

---

## 1. Overview

**Fade** (shipped as **Echo**) is a desktop-native professional media editor that unifies:

| Workspace | Capability |
|-----------|-----------|
| **Video** | Multi-track NLE timeline, clip manipulation, effects, transitions, animations |
| **Image** | Layer-based canvas compositor (Photoshop-style) |
| **PDF / Docs** | Multi-page document builder with visual layer editor |
| **Audio** | Volume mixing, TTS voiceover, Whisper transcription |
| **Director** | AI campaign orchestrator -- dispatches tasks to specialized agents |

Ships as a **self-contained Windows executable** -- no Python, Node.js, or GPU drivers needed.

---

## 2. Software Architecture

```
+------------------------------------------------------------------+
|             ELECTRON SHELL  (Node.js 20)                          |
|  Window mgmt . IPC bridge . Python spawn . WebComp host           |
+-----------------------------+------------------------------------+
                              | contextBridge (IPC)
+-----------------------------v------------------------------------+
|         REACT FRONTEND  (Vite 5 + TypeScript 5)                   |
|  Multi-workspace UI . Timeline . Library . Per-agent AI chat      |
+----------+--------------------------------+-----------------------+
           | HTTP REST + SSE               | N-API (.node addon)
           | WebSocket (frame pixels)      | via Electron IPC
+----------v-------------------+    +------v--------------------+
|  PYTHON FASTAPI BACKEND       |    |  C++20 RENDER ENGINE      |
|                              |    |                           |
|  21 REST API routers          |<-->|  Vulkan GPU device        |
|  Timeline state machine       |HTTP|  Skia 2D rasterizer       |
|  Multi-agent AI (LangGraph)   |    |  FFmpeg HW video decode   |
|  Background job queue         |    |  Compositor render graph  |
|  Media library + SSE push     |    |  Frame cache + scheduler  |
|  Whisper / TTS / ChromaDB     |    |  RGBA -> TSFN -> JS Buf   |
|  Export pipeline (PyAV)       |    |                           |
+-------------------------------+    +---------------------------+
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Electron** (not web) | Native FS, IPC to C++ `.node`, frameless window |
| **Python backend** | LangGraph, Whisper, ChromaDB, PyTorch ecosystem |
| **C++ GPU renderer** | HW video decode, Vulkan memory, sub-ms compositing |
| **N-API** (not HTTP for frames) | Zero-serialization -- avoids 60fps JPEG overhead |
| **FastAPI + SSE** for AI | LangGraph streams tokens/tool events natively |

---

## 3. Layer 1 - Electron Shell

**Files:** `electron/main.ts` (1390 lines), `electron/preload.ts`, `electron/webComp/`

### Python Process Lifecycle

```typescript
// Spawn Python backend as child process
pyProcess = spawn(pythonExe, [backendScript], {
  env: { ...process.env, FADE_PORT: String(port) }
})
// Polls stdout for "Backend ready on port XXXX"
// On quit: SIGTERM + taskkill /F /T /PID (kills GPU worker threads too)
```

### Splash Screen

A dedicated `BrowserWindow` shows boot progress while:
- Python subprocess starts and loads FastAPI routes
- Bundled ML models (Whisper `small.pt`, Kokoro TTS) initialize  
- C++ Vulkan device is selected and GPU context created

### IPC Bridge (contextBridge)

```typescript
// electron/preload.ts
contextBridge.exposeInMainWorld('electronAPI', {
  minimize:    () => ipcRenderer.send('window:minimize'),
  maximize:    () => ipcRenderer.send('window:maximize'),
  close:       () => ipcRenderer.send('window:close'),
  openFile:    () => ipcRenderer.invoke('dialog:openFile'),
  renderFrame: (data) => ipcRenderer.invoke('render:frame', data),
})
```

### WebComp Renderer (`electron/webComp/`)

Each WebComp (live HTML composition) gets its own **Puppeteer/Playwright** headless browser
page inside Electron's main process. `captureFrame()` screenshots the page and passes RGBA
pixel data to the C++ compositor via the same N-API path as video frames.

---

## 4. Layer 2 - React Frontend

**Files:** `src/` -- **Vite 5**, **React 18**, **TypeScript 5**

### Always-Mounted Workspaces

All workspaces are **always mounted** but toggled with `display: none`. Local state
(scroll, zoom, selected layers) survives tab switches without component destruction:

```tsx
// App.tsx
<div style={{ display: isVideoTab ? 'flex' : 'none' }}>
  <VideoWorkspace compId={videoCompId} />
</div>
<div style={{ display: isImageTab ? 'flex' : 'none' }}>
  <ImageWorkspace compId={imageCompId} />
</div>
```

### Per-Agent Chat Isolation

`key={activeTab}` forces `FloatingAIChat` to **remount** on every tab switch. Each remount
re-runs `useState` which reads the correct per-agent Map slot:

```tsx
// App.tsx
<FloatingAIChat key={activeTab} agentId={activeTab} onClose={...} />

// FloatingAIChat.tsx -- module-level Map store (persists across remounts)
const _storeMessages: Map<string, Message[]> = new Map()
const _storeHistory:  Map<string, History[]>  = new Map()
```

Each agent has its own greeting:
- **video** -- "I can edit the timeline, place clips, add effects..."
- **image** -- "I can create image compositions, add layers, apply filters..."
- **audio** -- "I can adjust volumes, TTS, transcribe speech..."
- **pdf**   -- "I can create PDF documents, add pages, populate content..."
- **director** -- "Give me a high-level brief and I'll plan the campaign..."

---

## 5. Layer 3 - Python FastAPI Backend

**Files:** `backend/` -- **FastAPI** on **Uvicorn** (full async I/O)

### API Router Map

| Prefix | File | Responsibility |
|--------|------|----------------|
| `/ai` | `ai/router.py` | Chat SSE streaming, agent restart, Director run |
| `/timeline` | `routers/timeline.py` | Timeline state, track management |
| `/clips` | `routers/clips.py` | CRUD: video / image / text / shape / SVG clips |
| `/comps` | `routers/comps.py` | Composition create / activate / state / PDF pages |
| `/library` | `routers/library.py` | Asset listing, import, SSE change events |
| `/render` | `routers/render.py` | Frame requests (routed to C++ renderer) |
| `/playback` | `routers/playback.py` | Play / pause / seek / speed |
| `/effects` | `routers/effects.py` | Effect catalog, add / remove / params |
| `/transitions` | `routers/transitions.py` | Transition catalog + insertion |
| `/audio` | `routers/audio.py` | Audio track management |
| `/animation` | `routers/animation.py` | Keyframes, expressions, easing curves |
| `/export` | `routers/export_.py` | Export triggers + SSE progress stream |
| `/jobs` | `routers/jobs.py` | Background job queue (TTS, Whisper, downloads) |
| `/search` | `routers/search.py` | DuckDuckGo search + yt-dlp download trigger |
| `/context` | `routers/context.py` | LLM-optimized timeline/clip context dumps |
| `/scene-tools` | `routers/scene_tools.py` | Semantic scene search (ChromaDB + vision AI) |
| `/virality` | `routers/virality.py` | Virality predictor + social connections |
| `/image-tools` | `routers/image_tools.py` | Image-specific operations |
| `/debug` | `routers/debug.py` | Animation diagnostics |
| `/mcp-remote` | `routers/mcp_remote_router.py` | MCP protocol for external AI access |

### Background Job Queue

```python
# Status flow: pending -> running -> done | failed
class Job:
    job_id:   str
    type:     Literal["whisper", "tts", "download", "index", "export"]
    status:   JobStatus
    progress: float     # 0.0 to 1.0
    result:   dict | None
```

Frontend polls `GET /jobs/{job_id}` or listens to SSE events for completion.

---
## 6. Layer 4 - C++20 Renderer (Vulkan + Skia)

**Files:** `renderer/src/` -- 39 `.cpp` files, built as a `.node` native addon

### Source Layout

```
renderer/src/
|-- napi/RenderEngineAddon.cpp         N-API entry: all JS-callable exports
|-- HeadlessCompositor.cpp             Top-level compositor orchestrator
|-- gpu/vulkan/
|   |-- device/DeviceContext.cpp       VkInstance, VkDevice, VMA allocator
|   |-- memory/Buffer.cpp              VMA-backed GPU buffer allocation
|   |-- memory/Texture.cpp             VkImage + VkImageView + VkSampler
|   |-- command/CommandBuffer.cpp      Recorded GPU draw commands
|   |-- command/CommandPool.cpp        Thread-local command pool management
|   `-- skia/SkiaContext.cpp           GrDirectContext (Skia Vulkan backend)
|-- rendering/
|   |-- Renderer.cpp                   Per-frame render loop
|   |-- RenderThread.cpp               Dedicated C++ render thread
|   |-- clips/VideoClip.cpp            Video frame -> textured quad
|   |-- compositor/
|   |   |-- Compositor.cpp             Graph execution engine
|   |   |-- graph/RenderGraph.cpp      Node dependency graph
|   |   `-- passes/
|   |       |-- CameraSetupNode        Viewport + project transform
|   |       |-- uploadTextureNode      CPU/GPU frame -> VkImage
|   |       |-- CompDrawNode           Layer z-order compositing
|   |       |-- EffectNode             Per-clip shader effects
|   |       `-- MaskNode               Alpha mask compositing
|   |-- effects/
|   |   |-- EffectRegistry.cpp         Built-in effect catalog
|   |   `-- EffectInstance.cpp         Per-clip effect state
|   |-- DrawText.cpp                   Skia SkFont + SkTextBlob
|   |-- DrawShape.cpp                  Skia SkPath (rect, ellipse, star)
|   |-- DrawPen.cpp                    Freehand brush strokes
|   `-- DrawSvg.cpp                    SkSVGDOM full SVG rendering
|-- video/
|   |-- HwVideoDecoder.cpp             DXVA2 / D3D11VA hardware decode
|   |-- videoDecoder.cpp               Software fallback (CPU YUV->RGBA)
|   `-- ClipDecoder.cpp                Per-clip decoder lifecycle
`-- engine/
    |-- DecodeScheduler.cpp            Pre-fetch frames ahead of playhead
    |-- DecoderPool.cpp                Per-clip decoder instance pool
    |-- FrameCache.cpp                 LRU ring buffer of decoded frames
    |-- ThreadPool.cpp                 N worker threads for parallel decode
    `-- SchedulerBridge.cpp            N-API TSFN callback bridge to JS
```

### GPU Device (DeviceContext.cpp)

```cpp
class DeviceContext {
    VkInstance       instance;       // Vulkan instance (validation in debug)
    VkPhysicalDevice physicalDevice; // GPU selection (prefers discrete GPU)
    VkDevice         device;         // Logical device
    VkQueue          graphicsQueue;
    VmaAllocator     allocator;      // VulkanMemoryAllocator
};
```

**VulkanMemoryAllocator (VMA)** manages GPU heap fragmentation automatically. Critical for
long editing sessions where thousands of video frame textures are allocated and freed.

### Skia on Vulkan (SkiaContext.cpp)

```cpp
GrVkBackendContext vkCtx {
    .fInstance       = device.instance,
    .fPhysicalDevice = device.physicalDevice,
    .fDevice         = device.device,
    .fQueue          = device.graphicsQueue,
};
GrDirectContext* grContext = GrDirectContext::MakeVulkan(vkCtx).release();
sk_sp<SkSurface> surface   = SkSurface::MakeRenderTarget(grContext, ...);
```

Skia renders to the **same Vulkan image** as video frame textures. No CPU readback between
video compositing and 2D drawing -- one unified GPU render pass.

### Hardware Video Decoding (HwVideoDecoder.cpp)

```cpp
// Hardware path: DXVA2 -> D3D11VA -> GPU VRAM -> VkImage (zero-copy)
av_hwdevice_ctx_create(&hwDevCtx, AV_HWDEVICE_TYPE_D3D11VA, nullptr, nullptr, 0);

// Software fallback: CPU YUV420P -> pixel convert -> VMA staging -> VkImage
```

### Render Graph (Compositor Passes)

```
Frame N render:
  CameraSetupNode    -- viewport matrix, aspect ratio correction
  uploadTextureNode  -- video frame VRAM -> VkImage
  CompDrawNode       -- iterate layers in z-order:
    VideoClip        --   textured quad + transform matrix
    TextClip         --   SkTextBlob (font cache, kerning)
    ShapeClip        --   SkPath (rectangle, ellipse, polygon)
    SVGClip          --   SkSVGDOM parse + rasterize
  EffectNode         -- per-clip fragment shader (blur, color grade, etc.)
  MaskNode           -- alpha mask compositing
  DebugOverlayNode   -- fps counter (dev builds only)
```

---

## 7. Layer 5 - N-API Bridge (C++ <-> Node.js)

**Files:** `renderer/src/napi/RenderEngineAddon.cpp`

**N-API** (Node-API) is the ABI-stable C API for native Node.js addons. The renderer compiles
to `render_engine.node` and is loaded directly by Electron -- no serialization, no HTTP, no IPC.

### Exported JavaScript API

```cpp
// RenderEngineAddon.cpp
Napi::Object Init(Napi::Env env, Napi::Object exports) {
    exports.Set("initRenderer",     Napi::Function::New(env, InitRenderer));
    exports.Set("renderFrame",      Napi::Function::New(env, RenderFrame));
    exports.Set("setTimeline",      Napi::Function::New(env, SetTimeline));
    exports.Set("setFrameCallback", Napi::Function::New(env, SetFrameCallback));
    exports.Set("startExport",      Napi::Function::New(env, StartExport));
    exports.Set("cancelExport",     Napi::Function::New(env, CancelExport));
    exports.Set("setPythonPort",    Napi::Function::New(env, SetPythonPort));
    exports.Set("setPreviewScale",  Napi::Function::New(env, SetPreviewScale));
    return exports;
}
NODE_API_MODULE(render_engine, Init)
```

```typescript
// Electron main.ts -- used like a normal Node.js module
const engine = require('./renderer/build/Release/render_engine.node')
engine.initRenderer({ width: 1920, height: 1080, fps: 30 })
engine.setFrameCallback((frameBuffer: Buffer) => {
  // Raw RGBA bytes -- direct V8 ArrayBuffer, one memcopy only
  ws.send(frameBuffer)  // WebSocket -> frontend canvas
})
```

### ThreadSafeFunction (TSFN) - Cross-Thread Callbacks

The renderer runs on its own C++ thread (not the Node.js event loop). Frames are delivered
to JavaScript via `Napi::ThreadSafeFunction`:

```cpp
// SchedulerBridge.cpp -- called from C++ render thread
g_tsfn.NonBlockingCall(
  [frameData](Napi::Env env, Napi::Function jsCallback) {
    // One memcopy: C++ heap -> V8 heap
    auto buf = Napi::Buffer<uint8_t>::Copy(env, frameData.data(), frameData.size());
    jsCallback.Call({ buf });
  }
);
```

### Export State

```cpp
struct ExportProgress { int frame; int total; bool done; std::string error; };
std::atomic<bool> g_exporting{false};
std::atomic<bool> g_exportCancel{false};
Napi::ThreadSafeFunction g_exportTsfn;  // second TSFN for export progress
```

### Build System

```bash
# cmake-js builds the C++ addon with Electron's exact Node.js ABI version
npx cmake-js build --runtime electron --runtime-version 29.0.0
# Output: renderer/build/Release/render_engine.node

# Key CMakeLists.txt settings:
#   find_package(Vulkan REQUIRED)
#   NAPI_VERSION=8
#   NAPI_DISABLE_CPP_EXCEPTIONS
#   VK_USE_PLATFORM_WIN32_KHR
#   Includes: FFmpeg headers, Skia source, VMA, GLM, stb, nlohmann/json
```

---
## 8. Multi-Agent AI System

**Files:** `backend/ai/` -- **LangGraph** + **LangChain**

### Architecture

```
User on any tab
      |
      v
POST /ai/chat  { message, agent: "video"|"image"|"audio"|"pdf"|"director"|"home" }
      |
      v
agent_registry.get_specialized_agent(agent_type, port)
      |
      v
+------------------------------------------------------------+
|          SPECIALIZED LANGGRAPH AGENT                        |
|  SystemMessage  <- specialized system prompt per agent     |
|  Tools          <- scoped to this agent's domain only      |
|  History        <- isolated per-agent (frontend Map)       |
|  call_model <-> tool_node  (loop until done)               |
+------------------------------------------------------------+
      |
      v  SSE stream: tokens . tool_call . tool_result . status
FloatingAIChat.tsx -- renders in real-time
```

### Agent Registry (`backend/ai/agent_registry.py`)

```python
_cache: dict[str, CompiledGraph] = {}   # key: "video:8000"

def get_specialized_agent(agent_type: str, port: int) -> CompiledGraph:
    key = f"{agent_type}:{port}"
    if key not in _cache:
        tools  = get_tools_for(agent_type)      # domain-scoped tool list
        system = SYSTEM_PROMPTS[agent_type]     # specialized system prompt
        _cache[key] = build_agent(port, tools_override=tools,
                                  system_override=system)
    return _cache[key]
```

### Tool Sets (`backend/ai/tool_sets.py`)

| Agent | Tools | Scoped to |
|-------|-------|-----------|
| `video` | 117 | Timeline, clips, effects, transitions, export, animations |
| `image` | 58 | Compositions, layers, image download/generate, masks |
| `audio` | 39 | Volume, TTS, Whisper, silence removal, audio tracks |
| `pdf` | 22 | PDF docs, pages, content, summaries |
| `director` | ALL + 3 | Everything + dispatch_task, get_campaign_status, list_platform_presets |
| `home` | 25 | Read-only: library, search, project overview |

### Director Agent - Campaign Orchestration

```
User: "Make social media content for all platforms"

Director:
  1. list_platform_presets()
     -> YouTube (1920x1080), IG Story (1080x1920), TikTok (1080x1920)...

  2. dispatch_task("video", "60s YouTube video",
                   platform="youtube", create_comp_name="YouTube_Post")
     -> creates 1920x1080 comp -> queues AgentTask -> returns task_id

  3. dispatch_task("image", "IG square post",
                   platform="instagram_post", create_comp_name="IG_Post")

  4. dispatch_task("video", "30s Reel",
                   platform="instagram_story", create_comp_name="Reel")

  5. get_campaign_status()
     -> "3 tasks: 1 done, 1 running, 1 pending"
```

### Platform Presets (`backend/ai/platform_presets.py`)

| Key | Dimensions | FPS | Max Duration |
|-----|-----------|-----|-------------|
| `youtube` | 1920x1080 | 30 | 60s |
| `instagram_post` | 1080x1080 | 30 | 60s |
| `instagram_story` | 1080x1920 | 30 | 90s |
| `tiktok` | 1080x1920 | 30 | 180s |
| `twitter` | 1280x720 | 30 | 140s |
| `youtube_short` | 1080x1920 | 30 | 60s |
| `linkedin` | 1920x1080 | 30 | 600s |
| `pinterest` | 1000x1500 | 30 | 15s |
| `facebook` | 1280x720 | 30 | 240s |
| `facebook_story` | 1080x1920 | 30 | 20s |

### Task Queue (`backend/ai/task_queue.py`)

```python
@dataclass
class AgentTask:
    id:          str
    agent_type:  Literal["video", "image", "audio", "pdf"]
    job:         str          # natural language instruction
    comp_id:     str | None   # composition created by Director
    platform:    str | None   # platform preset name
    status:      Literal["pending", "running", "done", "failed"]
    result:      str | None
```

asyncio-safe via `asyncio.Lock`. Supports concurrent Director writes and worker reads.

### LangGraph Agent (`backend/ai/agent.py`)

```python
def build_agent(port, tools_override=None, system_override=""):
    llm            = _build_llm()              # Ollama / OpenAI / Gemini / Groq
    llm_with_tools = llm.bind_tools(tools)     # LangChain tool binding
    tool_node      = ToolNode(tools)           # auto-executes tool calls

    def call_model(state: AgentState):
        system   = system_override + "\n\n" + _SYSTEM
        messages = [SystemMessage(content=system)] + state["messages"]
        response = llm_with_tools.invoke(_trim_messages(messages))
        return {"messages": [response]}

    graph = StateGraph(AgentState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", tool_node)
    graph.add_conditional_edges("agent", should_continue)
    return graph.compile()
```

Retries on transient errors with exponential backoff -- up to 4 attempts.

### Supported LLM Providers

| Provider | `FADE_AI_PROVIDER` | Notes |
|----------|-------------------|-------|
| **Ollama** (default) | `ollama` | Local, offline. Needs: `llama3.2`, `qwen2.5`, `mistral` |
| **OpenAI** | `openai` | GPT-4o, GPT-4-turbo |
| **Anthropic** | `anthropic` | Claude 3.5 Sonnet |
| **Google Gemini** | `google` | Gemini 1.5 Pro |
| **Groq** | `groq` | Ultra-fast inference |
| **TokenRouter** | `tokenrouter` | Multi-provider load balancer |

---

## 9. Media Pipeline (FFmpeg + HW Decode)

### Video Decode Flow

```
Video file (mp4 / mov / mkv / webm / avi)
    |
    v
FFmpeg AVFormatContext (demux) -> AVCodecContext (decode)
    |
    |-- HW path: DXVA2 / D3D11VA -> GPU VRAM -> VkImage (zero-copy)
    `-- SW path: CPU YUV420P -> pixel convert -> VMA staging -> VkImage
    |
    v
ClipDecoder -> DecodeScheduler (pre-fetch lookahead in ThreadPool)
    |
    v
FrameCache (LRU ring buffer)
    |
    v
Compositor render graph -> VkImage (all layers composited)
    |
    v
RGBA readback -> N-API TSFN -> Node.js Buffer -> WebSocket -> frontend canvas
```

### Audio Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Decode | FFmpeg / PyAV (`av`) | Audio stream demux + decode |
| TTS | **Kokoro** (bundled, offline) | Neural text-to-speech |
| Speech-to-text | **Faster-Whisper** (CTranslate2) | Timestamped transcription |
| Processing | **Numba / LLVM** | Silence detection, waveform analysis |
| Mixing | FFmpeg audio graph | Multi-track mix for export |

### Image Processing

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Load/save | **Pillow (PIL)** | Format conversion, thumbnails |
| Analysis | **OpenCV** (headless) | Frame extraction, filtering |
| ML inference | **PyTorch + torchvision** | Vision model inference |
| Server-side 2D | **skia-python** | PDF page composition |

---

## 10. Library and Asset Uploading

### Upload Flow

```
User drags file into Library panel  (or AI downloads media)
    |
    v
POST /library/import  { filePath }
    |
    v
library.py:
    1. Validate type (video / image / audio / pdf / svg)
    2. Generate assetId (UUID)
    3. Copy to /project/media/
    4. FFprobe: duration, dimensions, fps, codec
    5. Generate thumbnail (Pillow / FFmpeg first frame)
    6. Append to library.json manifest
    |
    v
SSE push -> GET /library/events -> LibraryPanel live update
```

### Asset Schema

```json
{
  "assetId":    "a1b2c3d4",
  "name":       "promo_clip.mp4",
  "type":       "video",
  "path":       "/project/media/a1b2c3d4.mp4",
  "duration":   30.5,
  "width":      1920,
  "height":     1080,
  "fps":        30,
  "thumbnail":  "/project/thumbnails/a1b2c3d4.jpg",
  "indexed":    true,
  "transcript": null
}
```

### Semantic Video Search (ChromaDB)

```
When "Index" is triggered on a video:
  1. FFmpeg extracts frames (default: 1 per 2 seconds)
  2. Ollama vision model (moondream/llava) describes each frame
  3. Faster-Whisper generates word-level transcript
  4. sentence-transformers embeds descriptions + transcript
  5. Stored in ChromaDB local vector database
  6. search_video_scenes(query) -> cosine similarity -> frame timestamps
```

---

## 11. Animation and Expression Engine

**Files:** `backend/animation/`, `backend/routers/animation.py`

### Keyframe Mode

```python
class AnimatableProperty:
    keyframes: list[Keyframe]  # [{frame, value, curve_type}]

def evaluate(frame: int) -> float:
    return interpolate_keyframes(self.keyframes, frame)
```

### Expression Mode

```javascript
// Mathematical expressions evaluated server-side per frame:
"sin(time * 2) * 100"                   // oscillating position
"frame / totalFrames * 360"             // full rotation over clip duration
"Math.random() * 10 + scale"            // camera shake
"linkedProp('clip_abc', 'opacity')"     // link to another clip's property
```

**Easing presets:** `linear` / `ease_in` / `ease_out` / `ease_in_out` / `bounce` / `spring` / `back` / `elastic`

---

## 12. PDF and Document Engine

PDFs are **multi-page compositions** -- each page rendered by the C++ GPU compositor,
then assembled into a PDF via Skia's PDF canvas backend.

```
PDFDocument
  |-- Page 1  (comp: 2480x3508 -- A4)
  |   |-- TextClip  (Skia SkTextBlob)
  |   |-- ImageClip (VkImage)
  |   `-- ShapeClip (SkPath)
  |-- Page 2 ...
  `-- Page N ...
        | export
        v
    Skia PDF canvas -> .pdf file
```

**AI tools:** `create_pdf_doc` / `add_pdf_page` / `delete_pdf_page` / `reorder_pdf_pages` / `get_pdf_doc_summary`

---

## 13. WebComp - Live HTML Compositions

WebComps are live web pages (HTML/CSS/JS) that render as **clips in the video timeline**.

```
WebComp clip in timeline
    |
    v
Electron main -> Puppeteer/Playwright page (isolated browser context)
    |
    v
Page loads editable HTML/CSS/JS (created/modified by AI or user)
    |
    v
captureFrame() -> RGBA Buffer -> N-API -> C++ compositor layer
```

**AI tools:**
```python
create_webcomp(name, html_body, css, js)         # create live HTML comp
edit_webcomp_file(webcomp_id, filename, content) # edit HTML/CSS/JS
set_webcomp_params(clip_id, params)              # update runtime params
```

**Use cases:** animated lower-thirds / data-driven infographics / live dashboards / generative art

---

## 14. Export Pipeline

```
POST /export/start  { format, quality, in_point, out_point }
    |
    v
ExportJob -> background thread
    |
    v
Per frame in [in_point, out_point]:
  1. C++ renderer -> full-resolution RGBA (no preview downscale)
  2. RGBA Buffer -> Python via N-API TSFN callback
  3. PyAV / FFmpeg encode (H.264 / H.265 / ProRes / VP9 / AV1)
  4. Audio: FFmpeg audio graph mixes all tracks
    |
    v
Progress -> SSE stream (GET /export/progress) -> ExportProgressOverlay (live %)
    |
    v
Done -> file saved to disk -> desktop notification
```

| Format | Codec | Best For |
|--------|-------|---------|
| MP4 H.264 | libx264 | Universal compatibility |
| MP4 H.265 | libx265 | Smaller file, same quality |
| ProRes 422 | prores_ks | Professional post-production |
| WebM VP9 | libvpx-vp9 | Web streaming |
| GIF | palettegen+paletteuse | Short animated clips |
| PNG Sequence | rawvideo | Frame-by-frame editing |

---

## 15. Technology Stack Summary

### Frontend

| Technology | Version | Purpose |
|-----------|---------|---------|
| Electron | 29 | Desktop shell, native APIs, process management |
| React | 18 | UI component framework |
| TypeScript | 5/7 | Static typing |
| Vite | 5 | Build tool + HMR dev server |
| FlexLayout-React | 0.10 | Dockable panel layout |
| Allotment | 1.20 | Resizable split panes |

### Backend (Python)

| Technology | Version | Purpose |
|-----------|---------|---------|
| FastAPI | >=0.111 | REST API + SSE streaming |
| Uvicorn | >=0.29 | ASGI server |
| LangGraph | >=0.2 | Stateful AI agent graphs |
| LangChain | >=0.3 | LLM provider abstractions |
| PyAV (`av`) | >=13 | Python FFmpeg bindings |
| Pillow | >=10 | Image I/O and processing |
| NumPy | >=1.26 | Array operations |
| PyTorch | >=2.0 | ML inference runtime |
| sentence-transformers | >=2.0 | Semantic embeddings |
| ChromaDB | latest | Local vector database |
| Faster-Whisper | 1.2.1 | CTranslate2 speech-to-text |
| Kokoro TTS | bundled | Offline neural TTS |
| yt-dlp | latest | Media downloading |
| DuckDuckGo Search | >=9.0 | Content search |
| OpenCV | headless | Frame extraction, filtering |
| skia-python | latest | Server-side 2D rendering |
| MCP | >=1.0 | Model Context Protocol |

### C++ Renderer

| Technology | Purpose |
|-----------|---------|
| C++20 | Language standard |
| CMake 3.20 + cmake-js | Build system + Node.js integration |
| node-addon-api 8.9 | N-API C++ wrapper |
| Vulkan 1.3 | GPU compute and rendering |
| Skia (Chromium m126) | 2D GPU-accelerated drawing |
| FFmpeg 6.x | Video/audio decode/encode |
| VulkanMemoryAllocator | GPU memory management |
| GLM | Mathematics (matrices, vectors) |
| stb_image | Lightweight image loading |
| nlohmann/json | JSON parsing in C++ |
| WinHTTP | HTTP requests from C++ |

---

## 16. Project Structure

```
fade/
|-- electron/                    Electron main process (Node.js)
|   |-- main.ts                  Lifecycle, IPC, Python spawn, N-API bridge
|   |-- preload.ts               contextBridge API exposure
|   `-- webComp/                 Puppeteer WebComp renderer
|-- src/                         React frontend (Vite + TypeScript)
|   |-- App.tsx                  Root: tab routing, workspace mounts
|   |-- api/                     Backend hooks (SSE, REST)
|   |-- components/              Shared UI (TitleBar, Library, DraggableAI)
|   |-- context/                 React context providers (PortContext)
|   `-- workspaces/
|       |-- VideoWorkspace.tsx
|       |-- ImageWorkspace.tsx
|       |-- FloatingAIChat.tsx   Per-agent isolated AI chat (key={activeTab})
|       `-- director/            Campaign orchestrator UI
|-- backend/                     Python FastAPI backend
|   |-- main.py                  App entry, 21 router mounts
|   |-- ai/
|   |   |-- agent.py             LangGraph agent builder
|   |   |-- agent_registry.py    Per-type agent cache + system prompts
|   |   |-- tool_sets.py         Domain-scoped tool lists (VIDEO/IMAGE/AUDIO/PDF)
|   |   |-- tools.py             80+ tool implementations (4220+ lines)
|   |   |-- platform_presets.py  Social media platform dimensions
|   |   |-- task_queue.py        Director->Worker async task queue
|   |   |-- director.py          DirectorSession + AgentScratchpad
|   |   |-- router.py            /ai/* HTTP endpoints
|   |   |-- whisper_tool.py      Faster-Whisper integration
|   |   |-- mcp_client.py        MCP remote client
|   |   `-- mcp_server.py        MCP tool server
|   |-- animation/               Keyframe + expression engine
|   |-- engine/                  Timeline engine, frame cache
|   |-- routers/                 21 REST API routers
|   |-- timeline/                Timeline + clip data models
|   |-- worker/                  Background job workers
|   `-- project/                 Project save/load (JSON)
`-- renderer/                    C++ GPU renderer (39 .cpp files)
    |-- CMakeLists.txt
    |-- src/
    |   |-- napi/                N-API bridge (RenderEngineAddon.cpp)
    |   |-- gpu/vulkan/          Vulkan device, memory, Skia context
    |   |-- rendering/           Compositor, effects, draw modules
    |   |-- engine/              Decode scheduler, frame cache, thread pool
    |   `-- video/               FFmpeg HW/SW decoder
    `-- deps/
        |-- ffmpeg/              FFmpeg headers + static libs
        |-- skia/                Skia source (Vulkan backend)
        |-- vma/                 VulkanMemoryAllocator
        `-- include/             GLM, stb, nlohmann/json
```

---

## 17. Getting Started (Development)

### Prerequisites

- **Windows 10/11 x64** (renderer uses DXVA2/D3D11VA hardware decode)
- **Node.js 20+** with npm
- **Python 3.12** with pip
- **Vulkan SDK 1.3+** from https://www.lunarg.com/vulkan-sdk/
- **Visual Studio 2022** with "Desktop development with C++" workload
- **CMake 3.20+**

### Setup

```bash
# 1. Install Node.js dependencies
npm install

# 2. Python virtual environment
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 3. Build C++ renderer (requires Vulkan SDK + VS2022)
npx cmake-js build --runtime electron --runtime-version 29.0.0

# 4. Configure AI provider in .env
echo FADE_AI_PROVIDER=ollama > .env
ollama pull llama3.2   # pull a tool-capable model

# 5. Start development server
npm run dev
```

### Environment Variables (`.env`)

```env
# AI Provider (choose one)
FADE_AI_PROVIDER=ollama          # ollama | openai | anthropic | google | groq
FADE_AI_MODEL=                   # auto-detected if empty

# API Keys (cloud providers only)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...
GROQ_API_KEY=gsk_...

# Backend
FADE_PORT=8000

# Optional
FADE_USER_NAME=                  # AI addresses user by name
```
```

---

*Built for Smart India Hackathon (SIH) 2025 -- Fade/Echo team*
