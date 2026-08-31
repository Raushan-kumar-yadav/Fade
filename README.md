# Fade — AI Video Editor 🎬✨

Fade is a next-generation, AI-first video editing platform built with Electron, React, and Python. It moves beyond traditional timeline editing to introduce an "AI Director" pipeline, designed to automate complex editing tasks, analyze video retention hooks, and apply dynamic motion graphics seamlessly.

![Fade Interface](https://img.shields.io/badge/UI-Glassmorphism-6c63ff?style=for-the-badge)
![Electron](https://img.shields.io/badge/Electron-191970?style=for-the-badge&logo=Electron&logoColor=white)
![React](https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)

## 🚀 Features

- **AI-Powered Workspaces:** Dedicated environments for specific tasks:
  - 🏠 **Home:** AI-powered analytics and video indexing.
  - 🤖 **AI:** Chat-based interface to instruct the AI Director to make edits, apply effects, and analyze frames.
  - 🎥 **Video:** A highly flexible, dockable non-linear editing (NLE) interface built with `react-resizable-panels`.
  - 🎵 **Audio:** Specialized audio editing and mixing (coming soon).
  - 📤 **Export:** Smart rendering presets for Shorts, Reels, 4K, and more.
- **Modern Architecture:**
  - **Frontend:** React + TypeScript + Vite for lightning-fast UI rendering.
  - **Backend:** Python + FastAPI to handle heavy video processing, frame analysis, and Skia/ffmpeg rendering.
  - **Container:** Electron for deep OS integration and native window controls.
- **Dynamic Layout:** Fully resizable, customizable dockable panels in the Video workspace for Library, Viewport, Timeline, Effects, and Properties.
- **Premium Aesthetics:** Custom glassmorphism UI, floating pill navigation, and tailored dark mode.

## 🛠️ Tech Stack

- **UI Framework:** React 18, TypeScript, Vite
- **Desktop Runtime:** Electron
- **Styling:** Vanilla CSS, custom CSS Variables, `react-resizable-panels`
- **Backend Services:** Python (FastAPI) _[Processing pipeline WIP]_

## 📦 Installation & Setup

1. **Clone the repository:**

   ```bash
   git clone https://github.com/Raushan-kumar-yadav/Fade.git
   cd Fade
   ```

2. **Install dependencies:**

   ```bash
   npm install
   ```

3. **Set up the Python Environment:**
   Ensure you have Python installed (3.10+ recommended).

   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   pip install fastapi uvicorn
   ```

4. **Run in Development Mode:**
   This will concurrently start Vite, compile the Electron main process via TypeScript, spin up the Python backend, and launch the Electron app.
   ```bash
   npm run dev
   ```

## 🏗️ Project Structure

```text
Fade/
├── backend/               # Python processing, AI models, Skia/FFmpeg logic
│   └── main.py            # FastAPI entry point
├── electron/              # Electron main process & preload scripts
│   ├── main.ts
│   └── preload.ts
├── src/                   # React frontend
│   ├── components/        # Reusable UI elements (TitleBar, TopTabBar)
│   ├── workspaces/        # Major app views (Home, AI, Video, Export)
│   ├── App.tsx            # Main application router
│   └── main.tsx           # React DOM entry
├── index.html             # Electron window template
└── vite.config.js         # Vite bundler config
```

## Kokoro audio genration

"kokoro-onnx is not installed.\n"
"Run: pip install kokoro-onnx soundfile\n"
"Windows also needs espeak-ng for multilingual support:\n"
" https://github.com/espeak-ng/espeak-ng/releases/download/1.52.0/espeak-ng.msi"

## 🗺️ Roadmap

- [x] Initial React/Electron scaffolding
- [x] UI/UX Overhaul (Floating tabs, TitleBar integration)
- [x] Dockable/Resizable Workspace System
- [ ] Implement Python AI Director agent
- [ ] Connect Python backend for timeline/ffmpeg execution
- [ ] Implement C++/Skia motion graphics easing bindings
- [ ] Real-time Viewport rendering

## 📝 License

MIT
