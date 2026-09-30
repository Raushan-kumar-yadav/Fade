# AIModels — Fade Local Model Registry

This folder is the **single source of truth** for every locally-stored AI/ML model
used by the Fade video editor backend. All paths in the codebase point here.

---

## Folder Structure

```
AIModels/
├── yolov8n.pt            # ✅ git-tracked (6 MB)  — person/object detection (PII + Tracking)
├── craft_mlt_25k.pth     # ✅ git-tracked (79 MB) — CRAFT text detection (PII OCR)
├── english_g2.pth        # ✅ git-tracked (14 MB) — G2P phoneme model (Kokoro TTS)
│
├── tessdata/             # ✅ git-tracked — Tesseract OCR language data
│   ├── eng.traineddata   #    English OCR model (22 MB)
│   └── osd.traineddata   #    Orientation + script detection (10 MB)
│
├── tesseract/            # ⛔ git-ignored — portable Tesseract 5.4 binary
│   └── tesseract.exe     #    Auto-extracted at startup via scripts/setup_tesseract.py
│                         #    Requires 7-Zip: winget install 7zip.7zip
│
├── whisper/              # ⛔ git-ignored — Whisper speech-to-text models
│   ├── small.pt          #    OpenAI Whisper small (461 MB) — auto-downloaded
│   ├── small/            #    faster-whisper CTranslate2 format — auto-downloaded
│   └── ...               #    Other sizes: tiny / base / medium / large
│
└── kokoro/               # ⛔ git-ignored — Kokoro local TTS (ONNX)
    ├── kokoro-v1.0.int8.onnx   # INT8 model (109 MB) — auto-downloaded
    ├── kokoro-v1.0.fp16.onnx   # FP16 model (156 MB) — higher quality
    └── voices-v1.0.bin         # Voice embeddings (27 MB) — auto-downloaded
```

---

## Model Details

### 1. YOLOv8n — Object / Person Detection

| Property | Value |
|---|---|
| **File** | `yolov8n.pt` (6 MB) — **git-tracked** |
| **Library** | `ultralytics` |
| **Code** | `backend/pii/detector.py`, `backend/tracking/` |
| **Used for** | PII person blurring, object tracking workspace |
| **Fallback** | `ultralytics` auto-downloads if file missing |

---

### 2. CRAFT — Scene Text Detection

| Property | Value |
|---|---|
| **File** | `craft_mlt_25k.pth` (79 MB) — **git-tracked** |
| **Library** | `craft-text-detector` |
| **Code** | `pii/detector.py` |
| **Used for** | Detecting text regions in images/frames for PII redaction |

---

### 3. G2P — Grapheme-to-Phoneme

| Property | Value |
|---|---|
| **File** | `english_g2.pth` (14 MB) — **git-tracked** |
| **Library** | `g2p_en` |
| **Code** | `backend/tools/generators/tts_generator.py` |
| **Used for** | English phonemization for Kokoro TTS voiceovers |

---

### 4. Tesseract OCR — Optical Character Recognition

| Property | Value |
|---|---|
| **tessdata** | `tessdata/eng+osd.traineddata` — **git-tracked** |
| **Binary** | `tesseract/tesseract.exe` — **git-ignored, auto-extracted** |
| **Code** | `pii/scrubber.py`, `scripts/setup_tesseract.py` |
| **Used for** | OCR text scanning in images/video for PII detection |
| **Requirement** | 7-Zip: `winget install 7zip.7zip` |
| **Auto-setup** | Runs at backend startup automatically |

---

### 5. Whisper — Speech-to-Text

| Property | Value |
|---|---|
| **Location** | `whisper/` — **git-ignored, auto-downloaded** |
| **Library** | `faster-whisper` (CTranslate2) or `openai-whisper` (fallback) |
| **Default** | `small` — override with `FADE_WHISPER_MODEL=tiny\|base\|medium` in `.env` |
| **Code** | `backend/ai/whisper_tool.py` |
| **GPU** | Auto-detects CUDA, falls back to CPU |
| **Used for** | Transcription, captions, speech detection |

---

### 6. Kokoro TTS — Local Text-to-Speech

| Property | Value |
|---|---|
| **Location** | `kokoro/` — **git-ignored, auto-downloaded** |
| **Library** | `kokoro-onnx` (ONNX Runtime, CPU-only) |
| **Config** | `generators.tts_provider = "kokoro"` in Settings |
| **Code** | `backend/tools/generators/tts_generator.py` |
| **Windows extra** | `espeak-ng` for multilingual voices — [download MSI](https://github.com/espeak-ng/espeak-ng/releases/download/1.52.0/espeak-ng.msi) |
| **Voices** | 54+ — American/British English, Hindi, Japanese, Spanish, French, Italian, Portuguese, Mandarin |

---

## External Services (no local files needed)

| Service | Purpose | Config |
|---|---|---|
| **Ollama** | LLM agent (local) | `ECHO_AI_PROVIDER=ollama` + `ollama pull llama3.2` |
| **Google Gemini** | LLM agent, video indexing, image gen | `GOOGLE_API_KEY` in `.env` |
| **ChromaDB** | Vector DB for semantic search | Auto-created at `~/.fade/chroma_db` |
| **fastembed** | ONNX text embeddings (no GPU required) | Auto-downloaded by `fastembed` package |

---

## After a Fresh Clone

All git-ignored models **auto-download on first use** — just run `npm run dev`.

To pre-download everything manually:

```powershell
# 1. Tesseract binary (needs 7-Zip)
winget install 7zip.7zip
python scripts/setup_tesseract.py

# 2. Kokoro TTS model + voices
curl -L -o AIModels\kokoro\kokoro-v1.0.int8.onnx `
  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.int8.onnx
curl -L -o AIModels\kokoro\voices-v1.0.bin `
  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin

# 3. Whisper small (or auto-downloads on first transcription)
python -c "import whisper; whisper.load_model('small', download_root='AIModels/whisper')"
```
