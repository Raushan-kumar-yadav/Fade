# tools/ffmpeg

This folder should contain the FFmpeg binaries for Fade.

The binaries are **not committed to git** (too large, listed in `.gitignore`).

## How to populate

### Option A — copy from your existing install
```powershell
$src = "C:\...\ffmpeg-9.0-full_build\bin"   # adjust to your path
Copy-Item "$src\ffmpeg.exe"  tools\ffmpeg\
Copy-Item "$src\ffprobe.exe" tools\ffmpeg\
Copy-Item "$src\ffplay.exe"  tools\ffmpeg\
```

### Option B — WinGet
```powershell
winget install Gyan.FFmpeg
# Then copy from the WinGet install location above
```

### Option C — direct download
Download the **full** build from https://www.gyan.dev/ffmpeg/builds/ and place
`ffmpeg.exe`, `ffprobe.exe`, and `ffplay.exe` in this folder.

---

The backend (`backend/main.py`) will automatically add this folder to `PATH` at
startup if the binaries are present. System-wide installs are used as a fallback.
