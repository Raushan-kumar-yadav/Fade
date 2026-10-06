# Fade Full Build Script
#
#   npm run build:full                      full build (backend + UI + Electron + native libs)
#   npm run build:full -- -Native           also recompile the C++ renderer first
#   npm run build:full -- -SkipBackend      reuse the existing pyinstaller-dist (fast UI-only rebuild)
#   npm run build:backend-only              rebuild ONLY the Python backend and update it inside
#                                           the existing dist-app build (no Vite / Electron / models)
#
# For a change to backend .py files only, no build is needed at all:
#   npm run hotfix                          copies the changed .py files into dist-app (seconds)
# (backend\main.py is the exception - it is compiled into backend.exe.)
#
# Output: dist-app\win-unpacked\Fade.exe
param(
    [switch]$Native,
    [switch]$SkipBackend,
    [switch]$BackendOnly,
    [switch]$UiOnly       # npm run build:ui-only - rebuild the UI + Electron code and update only those files
)
if ($UiOnly) { $SkipBackend = $true }

Set-StrictMode -Version Latest
$ROOT = Split-Path $PSScriptRoot -Parent
$started = Get-Date

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " FADE FULL BUILD" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 0. Preflight - fail early with a clear message instead of half-way through
Write-Host "[0/6] Preflight checks..." -ForegroundColor Yellow
$ErrorActionPreference = "Stop"
# PyInstaller is started as "python -m PyInstaller", NOT through
# .venv\Scripts\pyinstaller.exe: that launcher has the absolute path of the Python
# it was created with baked in. This .venv was copied from another folder, so the
# launcher silently ran a DIFFERENT project's environment and packaged its libraries.
$venvPython  = Join-Path $ROOT ".venv\Scripts\python.exe"
$nativeDir   = Join-Path $ROOT "renderer\build\Release"
$nativeAddon = Join-Path $nativeDir "render_engine.node"

if (-not (Test-Path $venvPython)) {
    throw "Python environment not found at $venvPython"
}
if (-not $SkipBackend) {
    if (-not (Test-Path (Join-Path $ROOT ".venv\Lib\site-packages\PyInstaller\__main__.py"))) {
        throw "PyInstaller is not installed in .venv - run: .venv\Scripts\python.exe -m pip install pyinstaller"
    }
    # Packages behind optional features. The backend imports them lazily, so a
    # missing one does not break the build - the feature is just absent from it.
    $featureCheck = @'
import importlib.util as u
features = {
    "rembg": "background removal", "lap": "object tracking (ByteTrack)",
    "kokoro_onnx": "text-to-speech", "mediapipe": "face detection",
    "whisper": "captions (openai-whisper)", "faster_whisper": "captions (faster-whisper)",
    "easyocr": "text tracking / OCR", "ultralytics": "person tracking (YOLO)",
    "reportlab": "PDF export", "yt_dlp": "video / music download",
    "scipy": "OCR + perceptual hashing", "pdfplumber": "prompt-injection shield (PDF scan)",
}
for mod, what in features.items():
    try:
        found = u.find_spec(mod) is not None
    except Exception:
        found = False
    if not found:
        print(f"{mod}|{what}")
'@
    $missingFeatures = @($featureCheck | & $venvPython - 2>$null | Where-Object { $_ -match '\|' })
    foreach ($m in $missingFeatures) {
        $parts = $m.Split('|')
        Write-Host "  [WARN] '$($parts[0])' is not installed in .venv -> $($parts[1]) will NOT work in this build" -ForegroundColor Yellow
    }
}
if (-not $BackendOnly -and -not (Test-Path (Join-Path $ROOT "node_modules\electron-builder"))) {
    throw "node_modules is missing or incomplete - run: npm install"
}
if ($BackendOnly -and -not (Test-Path (Join-Path $ROOT "dist-app\win-unpacked\Fade.exe"))) {
    throw "-BackendOnly updates an existing build, but dist-app\win-unpacked\Fade.exe does not exist. Run: npm run build:full"
}
if ($SkipBackend -and -not (Test-Path (Join-Path $ROOT "pyinstaller-dist\backend\backend.exe"))) {
    throw "-SkipBackend was given but pyinstaller-dist\backend\backend.exe does not exist"
}

# A running packaged app locks its DLLs and makes the copy steps fail.
$distRoot = Join-Path $ROOT "dist-app\win-unpacked"
function Assert-AppClosed([string]$retryHint, [switch]$AllowExited) {
    $procs = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
        try { $_.Path -and $_.Path.StartsWith($distRoot, [System.StringComparison]::OrdinalIgnoreCase) } catch { $false }
    })
    $running = @($procs | Where-Object { -not $_.HasExited })
    $exited  = @($procs | Where-Object { $_.HasExited })
    if ($running.Count -gt 0) {
        $names = ($running | ForEach-Object { "$($_.Name) (PID $($_.Id))" }) -join ", "
        throw "The packaged app is running from dist-app\win-unpacked: $names. Close it, then run: $retryHint"
    }
    # A Fade.exe that has already exited but is still listed: its GPU thread is stuck
    # in the driver, so Windows keeps Fade.exe and the renderer DLLs locked. It cannot
    # be closed or killed - only signing out or restarting Windows clears it.
    if ($exited.Count -gt 0) {
        $names = ($exited | ForEach-Object { "$($_.Name) (PID $($_.Id))" }) -join ", "
        if ($AllowExited) {
            Write-Host "  [WARN] Leftover exited process still holds Fade.exe / renderer DLLs: $names" -ForegroundColor Yellow
            Write-Host "         Backend and UI files are not locked, so this update continues." -ForegroundColor Yellow
        } else {
            throw "A leftover Fade.exe that has already exited still locks Fade.exe and the renderer DLLs: $names. Sign out of Windows or restart, then run: $retryHint"
        }
    }
}
if ($BackendOnly) {
    # PyInstaller does not touch dist-app, so the app only has to be closed for the
    # copy step - it is checked again right before that.
    Write-Host "  [OK] Tools present (backend-only build)" -ForegroundColor Green
} elseif ($UiOnly) {
    Write-Host "  [OK] Tools present (UI-only build)" -ForegroundColor Green
} else {
    Assert-AppClosed "npm run build:full"
    Write-Host "  [OK] Tools present, packaged app not running" -ForegroundColor Green
}

# UI-only: compile the React UI (Vite) and the Electron main/preload (tsc), then
# mirror just those two folders into the existing build. The build is not an asar
# archive, so resources\app\dist and resources\app\dist-electron are plain files.
if ($UiOnly) {
    $appDir = Join-Path $distRoot "resources\app"
    if (-not (Test-Path $appDir)) { throw "-UiOnly updates an existing build, but $appDir does not exist. Run: npm run build:full" }
    Write-Host ""
    Write-Host "[UI] Building Vite UI + Electron main..." -ForegroundColor Yellow
    Push-Location $ROOT
    $ErrorActionPreference = "Continue"
    & npm run build *>&1
    $uiExit = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    Pop-Location
    if ($uiExit -ne 0) { throw "npm run build failed (exit $uiExit)!" }
    Assert-AppClosed "npm run build:ui-only" -AllowExited
    foreach ($dir in @("dist", "dist-electron")) {
        $ErrorActionPreference = "Continue"
        & robocopy (Join-Path $ROOT $dir) (Join-Path $appDir $dir) /MIR /R:2 /W:2 /NFL /NDL /NJH /NJS /NP | Out-Null
        $roboExit = $LASTEXITCODE
        $ErrorActionPreference = "Stop"
        if ($roboExit -ge 8) { throw "robocopy failed (exit $roboExit) while updating $dir" }
        Write-Host "  [OK] $dir -> resources\app\$dir" -ForegroundColor Green
    }
    $mins = [math]::Round(((Get-Date) - $started).TotalMinutes, 1)
    Write-Host ""
    Write-Host " UI UPDATE OK in $mins min -> $distRoot\Fade.exe" -ForegroundColor Green
    exit 0
}

# 1. C++ renderer (Vulkan + Skia + FFmpeg node addon)
Write-Host ""
if ($BackendOnly) {
    Write-Host "[1/6] C++ renderer: skipped (-BackendOnly)" -ForegroundColor DarkGray
} else {
Write-Host "[1/6] C++ renderer..." -ForegroundColor Yellow
if ($Native) {
    Push-Location $ROOT
    $ErrorActionPreference = "Continue"
    & npm run build:native *>&1
    $nativeExit = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    Pop-Location
    if ($nativeExit -ne 0) { throw "npm run build:native failed (exit $nativeExit)!" }
    Write-Host "  [OK] render_engine.node rebuilt" -ForegroundColor Green
}
if (-not (Test-Path $nativeAddon)) {
    throw "renderer\build\Release\render_engine.node is missing - run: npm run build:full -- -Native"
}
# The addon is prebuilt and not recompiled by default: warn when sources are newer.
$addonTime = (Get-Item $nativeAddon).LastWriteTime
$newerSrc = @(Get-ChildItem (Join-Path $ROOT "renderer\src") -Recurse -File -ErrorAction SilentlyContinue |
              Where-Object { $_.LastWriteTime -gt $addonTime })
if ($newerSrc.Count -gt 0) {
    Write-Host "  [WARN] $($newerSrc.Count) renderer source file(s) are newer than render_engine.node" -ForegroundColor Yellow
    Write-Host "         (e.g. $($newerSrc[0].Name)). Rebuild with: npm run build:full -- -Native" -ForegroundColor Yellow
} elseif (-not $Native) {
    Write-Host "  [OK] Prebuilt render_engine.node is up to date ($addonTime)" -ForegroundColor Green
}
$ffmpegDlls = @(Get-ChildItem $nativeDir -Filter "av*.dll" -ErrorAction SilentlyContinue)
if ($ffmpegDlls.Count -lt 5 -or -not (Test-Path (Join-Path $nativeDir "ffmpeg.exe"))) {
    throw "FFmpeg DLLs / ffmpeg.exe are missing from renderer\build\Release - the renderer and exports cannot work without them."
}
Write-Host "  [OK] FFmpeg libraries present ($($ffmpegDlls.Count) av*.dll + ffmpeg.exe)" -ForegroundColor Green
}

# 2. PyInstaller backend (handles compiled deps: skia, torch, cv2, etc.)
Write-Host ""
if ($SkipBackend) {
    Write-Host "[2/6] Python backend: reusing existing pyinstaller-dist (-SkipBackend)" -ForegroundColor Yellow
} else {
    Write-Host "[2/6] Building Python backend (PyInstaller)..." -ForegroundColor Yellow
    Push-Location $ROOT
    # PyInstaller writes INFO logs to stderr - we pipe both streams to the log file
    # and check exit code manually (do not use $ErrorActionPreference = Stop here)
    $ErrorActionPreference = "Continue"
    & $venvPython -m PyInstaller backend.spec --distpath pyinstaller-dist --workpath pyinstaller-build --noconfirm *>&1 | Tee-Object -FilePath "pyinstaller-build.log"
    $pyExit = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    Pop-Location
    if ($pyExit -ne 0) { throw "PyInstaller failed (exit $pyExit)! See pyinstaller-build.log" }
    Write-Host "  [OK] Backend built" -ForegroundColor Green
}

# 3. Electron + Vite
Write-Host ""
if ($BackendOnly) {
    Write-Host "[3/6] Electron + Vite: skipped (-BackendOnly)" -ForegroundColor DarkGray
} else {
    Write-Host "[3/6] Building Electron + Vite..." -ForegroundColor Yellow
    Push-Location $ROOT
    $ErrorActionPreference = "Continue"
    & npm run dist *>&1
    $npmExit = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    Pop-Location
    if ($npmExit -ne 0) { throw "npm run dist failed (exit $npmExit)!" }
    Write-Host "  [OK] Electron built -> dist-app\win-unpacked" -ForegroundColor Green
}

# 4. Copy backend bundle to dist-app
Write-Host ""
$dst_backend = Join-Path $ROOT "dist-app\win-unpacked\resources\backend"
if ($BackendOnly) {
    Write-Host "[4/6] Updating changed backend files in dist-app..." -ForegroundColor Yellow
    Assert-AppClosed "npm run build:backend-only -- -SkipBackend   (reuses the backend that was just built)" -AllowExited
    # robocopy skips files whose size and timestamp are unchanged, so only what the
    # rebuild actually changed is copied (the multi-GB library folders are left alone).
    $ErrorActionPreference = "Continue"
    $roboOut = & robocopy (Join-Path $ROOT "pyinstaller-dist\backend") $dst_backend /E /R:2 /W:2 /NFL /NDL /NJH /NP
    $roboExit = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($roboExit -ge 8) { $roboOut | Write-Host; throw "robocopy failed (exit $roboExit) while updating the backend" }
    $filesLine = @($roboOut | Where-Object { $_ -match '^\s*Files\s*:' }) | Select-Object -First 1
    if ($filesLine -and ($filesLine -match 'Files\s*:\s*(\d+)\s+(\d+)')) {
        Write-Host "  [OK] $($Matches[2]) of $($Matches[1]) backend files were new or changed and were copied" -ForegroundColor Green
    } else {
        Write-Host "  [OK] Backend files updated" -ForegroundColor Green
    }
} else {
    Write-Host "[4/6] Copying backend bundle to dist-app..." -ForegroundColor Yellow
    if (Test-Path $dst_backend) { Remove-Item $dst_backend -Recurse -Force }
    Copy-Item (Join-Path $ROOT "pyinstaller-dist\backend") $dst_backend -Recurse -Force
    Write-Host "  [OK] Backend bundle copied" -ForegroundColor Green
}

# 5. Overlay FULL backend Python source as loose .py files
#    This ensures no module is ever missed by PyInstaller's analysis.
#    Compiled deps (torch, skia, etc.) still come from the PYZ/DLLs.
Write-Host ""
Write-Host "[5/6] Overlaying backend source (.py files)..." -ForegroundColor Yellow
$enc = [System.Text.UTF8Encoding]::new($false)
$internal = "$dst_backend\_internal"

# backend/ source
$srcBackend = Join-Path $ROOT "backend"
$dstBackendSrc = "$internal\backend"
if (Test-Path $dstBackendSrc) { Remove-Item $dstBackendSrc -Recurse -Force }
Copy-Item $srcBackend $dstBackendSrc -Recurse -Force

# Fix _root.py: strip BOM if present
$rawBytes = [System.IO.File]::ReadAllBytes((Join-Path $ROOT "backend\_root.py"))
if ($rawBytes.Length -ge 3 -and $rawBytes[0] -eq 0xEF -and $rawBytes[1] -eq 0xBB -and $rawBytes[2] -eq 0xBF) {
    $rawBytes = $rawBytes[3..($rawBytes.Length-1)]
}
[System.IO.File]::WriteAllText("$dstBackendSrc\_root.py", $enc.GetString($rawBytes), $enc)

# pii/ local scripts (imported via sys.path manipulation)
$srcPii = Join-Path $ROOT "pii"
if (Test-Path $srcPii) {
    $dstPii = "$internal\pii"
    if (Test-Path $dstPii) { Remove-Item $dstPii -Recurse -Force }
    Copy-Item $srcPii $dstPii -Recurse -Force
    Write-Host "  [OK] pii/ scripts overlaid" -ForegroundColor Green
}

$pyCount = @(Get-ChildItem $dstBackendSrc -Recurse -Filter "*.py").Count
Write-Host "  [OK] $pyCount .py files overlaid into _internal/" -ForegroundColor Green

# 6. Post-build patch - copies native libraries / models and verifies the result
Write-Host ""
Write-Host "[6/6] Running post-build patch..." -ForegroundColor Yellow
# The patch script only sets an exit code when it fails, so clear any stale one
# first (robocopy above returns 1-7 for SUCCESS).
$global:LASTEXITCODE = 0
& "$ROOT\scripts\post_build_patch.ps1" -DistName "win-unpacked"
if ($LASTEXITCODE -ne 0) { throw "Post-build patch reported failures - see output above." }

$mins = [math]::Round(((Get-Date) - $started).TotalMinutes, 1)
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " BUILD OK in $mins min" -ForegroundColor Green
Write-Host " $distRoot\Fade.exe" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
