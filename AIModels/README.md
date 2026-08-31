# AIModels — Fade Local Model Registry

This folder is the **single source of truth** for every locally-stored AI/ML model
used by the Fade video editor backend. All paths in the codebase point here.

> **Note:** Model files (`.onnx`, `.pt`, `.bin`) are excluded from git via
> `.gitignore`. They are **auto-downloaded on first use** when you start the backend.

---

## Folder Structure

```
AIModels/
├── whisper/          # Faster-Whisper / OpenAI Whisper speech-to-text
│   ├── small.pt      # Whisper small (461 MB) — default model
│   ├── tiny/         # faster-whisper CTranslate2 format (auto-downloaded)
│   ├── base/
│   ├── small/        # faster-whisper CTranslate2 format (auto-downloaded)
│   └── medium/
│
└── kokoro/           # Kokoro TTS — local text-to-speech (ONNX)
    ├── kokoro-v1.0.int8.onnx   # INT8 quantized model (109 MB) - used by default
    ├── kokoro-v1.0.fp16.onnx   # FP16 model (156 MB) - higher quality
    └── voices-v1.0.bin         # Voice embeddings pack (27 MB)
```

---

## Model Details

### 1. Whisper (Speech-to-Text / Transcription)

| Property | Value |
|----------|-------|
| **Library** | `faster-whisper` (CTranslate2) or `openai-whisper` (fallback) |
| **Default model** | `small` |
| **Config key** | `ai.whisper_model` (`tiny` / `base` / `small` / `medium` / `large`) |
| **Backend key** | `ai.whisper_backend` (`faster` / `openai`) |
| **Code** | `backend/ai/whisper_tool.py` |
| **Auto-download** | Yes - downloads from HuggingFace on first transcription request |
| **GPU support** | Yes - auto-detects CUDA via `ctranslate2`, falls back to CPU |

**Used for:**
- Video semantic indexing (scene captions + transcript enrichment)
- Caption generation on the timeline
- Speech-segment detection for audio tools

---

### 2. Kokoro TTS (Text-to-Speech)

| Property | Value |
|----------|-------|
| **Library** | `kokoro-onnx` (ONNX Runtime inference) |
| **Model** | Kokoro v1.0 INT8 ONNX (~82M params, Apache 2.0) |
| **Config key** | `generators.tts_provider = "kokoro"` |
| **Voice key** | `generators.tts_kokoro_voice` (default: `af_heart`) |
| **Code** | `backend/tools/generators/tts_generator.py` |
| **Auto-download** | Yes - downloads from GitHub releases on first TTS call |
| **GPU support** | No - ONNX CPU inference (fast enough, no GPU needed) |

**Available voice families (54+ voices):**
- `af_*` / `am_*` - American English (female / male)
- `bf_*` / `bm_*` - British English (female / male)
- `hf_*` / `hm_*` - Hindi
- `jf_*` / `jm_*` - Japanese
- `ef_*` / `em_*` - Spanish
- `ff_*` - French
- `if_*` / `im_*` - Italian
- `pf_*` / `pm_*` - Portuguese
- `cf_*` / `cm_*` - Mandarin Chinese

**Windows extra requirement:**
espeak-ng must be installed for multilingual phonemization.
https://github.com/espeak-ng/espeak-ng/releases/download/1.52.0/espeak-ng.msi

---

## External AI Services (not stored here)

These run as external services or use cloud APIs - no local files needed:

| Service | Purpose | Config |
|---------|---------|--------|
| **Ollama** | LLM inference, image captioning, legacy TTS | `generators.ollama_url` |
| **Google Gemini** | Cloud image generation, TTS, LLM agent | `GOOGLE_API_KEY` in `.env` |
| **Google Imagen** | Cloud image generation | `GOOGLE_API_KEY` in `.env` |
| **ChromaDB** | Vector DB for semantic search (data, not model) | Per-project `.chroma/` folder |

---

## Restoring Models After Fresh Clone

Models are auto-downloaded on first use. You can also manually restore:

```powershell
# Kokoro TTS (int8 model + voices)
curl -L -o AIModels\kokoro\kokoro-v1.0.int8.onnx https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.int8.onnx
curl -L -o AIModels\kokoro\voices-v1.0.bin https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin

# Whisper small (auto-downloads from HuggingFace on first transcription)
```
