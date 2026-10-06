# ============================================================
#  Fade Post-Build Patch Script
#  Applies all known fixes that PyInstaller / electron-builder
#  miss during packaging. Run automatically by build_full.ps1,
#  or manually:
#    .\scripts\post_build_patch.ps1
#    .\scripts\post_build_patch.ps1 -DistName "Fade-V1.0"
# ============================================================
param(
    [string]$DistName = "win-unpacked"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ROOT     = Split-Path $PSScriptRoot -Parent
$res      = "$ROOT\dist-app\$DistName\resources"
$backend  = "$res\backend"
$internal = "$backend\_internal"
$venv     = "$ROOT\.venv\Lib\site-packages"

function Ok($msg)   { Write-Host "  [OK]   $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "  [FAIL] $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " FADE POST-BUILD PATCH" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ---- 1. SKSL shaders --------------------------------------------------------
# Needed in TWO places:
#   (a) _internal/backend/timeline/effects/sksl/  -> Python compositor (export)
#   (b) backend/timeline/effects/sksl/            -> C++ renderer (live viewport)
Write-Host "[1] SKSL shaders..." -ForegroundColor Yellow
$skslSrc = "$ROOT\backend\timeline\effects\sksl"
if (Test-Path $skslSrc) {
    $dst_a = "$internal\backend\timeline\effects\sksl"
    $dst_b = "$backend\timeline\effects\sksl"
    foreach ($dst in @($dst_a, $dst_b)) {
        New-Item $dst -ItemType Directory -Force | Out-Null
        Copy-Item "$skslSrc\*" $dst -Recurse -Force
    }
    $count = (Get-ChildItem $skslSrc -Recurse -File).Count
    Ok "SKSL shaders ($count files) -> both renderer paths"
} else { Warn "sksl source not found: $skslSrc" }

# ---- 2. torchvision C extensions (NMS operator) ----------------------------
# PyInstaller bundles the pure-Python torchvision files but silently drops
# _C_stable.pyd which registers torchvision::nms with PyTorch's dispatcher.
# Without it person tracking crashes: "operator torchvision::nms does not exist"
Write-Host ""
Write-Host "[2] torchvision C extensions..." -ForegroundColor Yellow
$tvSrc = "$venv\torchvision"
$tvDst = "$internal\torchvision"
if (Test-Path $tvSrc) {
    $tvFiles = @("_C_stable.pyd", "image_stable.pyd",
                 "jpeg8.dll", "libpng16.dll", "libsharpyuv.dll", "libwebp.dll", "zlib.dll")
    $copied = 0
    foreach ($f in $tvFiles) {
        if (Test-Path "$tvSrc\$f") {
            Copy-Item "$tvSrc\$f" "$tvDst\$f" -Force
            $copied++
        }
    }
    Ok "torchvision extensions ($copied files)"
} else { Warn "torchvision venv not found: $tvSrc" }

# ---- 2.5 Matplotlib (MediaPipe Face dependency) -----------------------------
# MediaPipe's FaceDetector imports matplotlib, which PyInstaller misses because
# it is dynamically loaded. Without it, FaceDetector falls back to OpenCV.
Write-Host ""
Write-Host "[2.5] Matplotlib dependencies..." -ForegroundColor Yellow
if (Test-Path $venv) {
    $mplDeps = @("matplotlib", "mpl_toolkits", "cycler", "kiwisolver", "fontTools", "contourpy", "pyparsing", "dateutil", "packaging")
    $mplCopied = 0
    foreach ($dep in $mplDeps) {
        $depSrc = "$venv\$dep"
        $depDst = "$internal\$dep"
        if (Test-Path $depSrc) {
            # Some dependencies might just be single files, e.g. cycler.py
            Copy-Item $depSrc $depDst -Recurse -Force
            $mplCopied++
        }
    }
    Ok "Matplotlib dependencies ($mplCopied folders)"
} else { Warn "venv site-packages not found" }

# ---- 3. Backend Python source overlay ---------------------------------------
# Copy the full backend/ source on top of PyInstaller's _internal so that
# any source-only changes (no rebuild needed) are always reflected.
Write-Host ""
Write-Host "[3] Backend Python source overlay..." -ForegroundColor Yellow
$srcBackend = "$ROOT\backend"
$dstBackend = "$internal\backend"
if (Test-Path $srcBackend) {
    if (-not (Test-Path $dstBackend)) { New-Item $dstBackend -ItemType Directory -Force | Out-Null }
    Get-ChildItem $srcBackend -Recurse -Filter "*.py" | ForEach-Object {
        $rel = $_.FullName.Substring($srcBackend.Length + 1)
        $target = "$dstBackend\$rel"
        $targetDir = Split-Path $target
        if (-not (Test-Path $targetDir)) { New-Item $targetDir -ItemType Directory -Force | Out-Null }
        Copy-Item $_.FullName $target -Force
    }
    $count = (Get-ChildItem $srcBackend -Recurse -Filter "*.py").Count
    Ok "Backend source ($count .py files overlaid)"
} else { Warn "backend/ source not found" }

# ---- 4. AI skills -----------------------------------------------------------
Write-Host ""
Write-Host "[4] AI skills..." -ForegroundColor Yellow
$skillsSrc = "$ROOT\backend\ai\skills"
$skillsDst = "$internal\backend\ai\skills"
if (Test-Path $skillsSrc) {
    New-Item $skillsDst -ItemType Directory -Force | Out-Null
    Copy-Item "$skillsSrc\*" $skillsDst -Recurse -Force
    $count = (Get-ChildItem $skillsSrc -Recurse -File).Count
    Ok "AI skills ($count files)"
} else { Warn "skills/ not found" }

# ---- 4.5. pii/ scripts -------------------------------------------------------
# pii/scrubber.py must be reachable at BOTH:
#   resources/pii/           <- when FADE_RESOURCES_PATH is set (Electron packaged)
#   resources/backend/_internal/pii/ <- when accessed via _MEIPASS (PyInstaller)
Write-Host ""
Write-Host "[4.5] pii/ scripts..." -ForegroundColor Yellow
$piiSrc = "$ROOT\pii"
if (Test-Path $piiSrc) {
    # Copy to resources/pii/ (FADE_RESOURCES_PATH path)
    $piiDst1 = "$res\pii"
    New-Item $piiDst1 -ItemType Directory -Force | Out-Null
    Copy-Item "$piiSrc\*" $piiDst1 -Recurse -Force
    # Copy to _internal/pii/ (_MEIPASS path)
    $piiDst2 = "$internal\pii"
    New-Item $piiDst2 -ItemType Directory -Force | Out-Null
    Copy-Item "$piiSrc\*" $piiDst2 -Recurse -Force
    $count = (Get-ChildItem $piiSrc -Filter "*.py").Count
    Ok "pii/ scripts ($count files to both locations)"
} else { Warn "pii/ source not found" }

# ---- 5. Electron splash screen ----------------------------------------------
Write-Host ""
Write-Host "[5] Electron splash screen..." -ForegroundColor Yellow
$splashSrc = "$ROOT\electron\splash.html"
$splashDst = "$ROOT\dist-app\$DistName\resources\app\dist-electron\splash.html"
$splashDir = Split-Path $splashDst
if (Test-Path $splashSrc) {
    if (Test-Path $splashDir) {
        Copy-Item $splashSrc $splashDst -Force
        Ok "splash.html"
    } else { Warn "dist-electron/ not found - splash not copied" }
} else { Warn "electron/splash.html not found" }

# ---- 6. .env ----------------------------------------------------------------
Write-Host ""
Write-Host "[6] .env files..." -ForegroundColor Yellow
$envSrc = "$ROOT\.env"
if (Test-Path $envSrc) {
    Copy-Item $envSrc "$res\.env"     -Force
    Copy-Item $envSrc "$backend\.env" -Force
    Ok ".env copied to resources/ and backend/"
} else { Warn ".env not found in project root" }

# ---- 7. AIModels ------------------------------------------------------------
Write-Host ""
Write-Host "[7] AIModels..." -ForegroundColor Yellow
$modelsSrc = "$ROOT\AIModels"
$modelsDst = "$res\AIModels"
if (Test-Path $modelsSrc) {
    New-Item $modelsDst -ItemType Directory -Force | Out-Null
    Copy-Item "$modelsSrc\*" $modelsDst -Recurse -Force
    $count = (Get-ChildItem $modelsSrc -Recurse -File).Count
    Ok "AIModels ($count files)"
} else { Warn "AIModels/ not found" }

# ---- 8. Renderer build (C++ node addon + ffmpeg) ----------------------------
Write-Host ""
Write-Host "[8] Renderer build..." -ForegroundColor Yellow
$rendererSrc = "$ROOT\renderer\build\Release"
$rendererDst = "$res\renderer\build\Release"
if (Test-Path $rendererSrc) {
    New-Item $rendererDst -ItemType Directory -Force | Out-Null
    try {
        Copy-Item "$rendererSrc\*" $rendererDst -Recurse -Force
        Ok "renderer/build/Release"
    } catch {
        Warn "renderer copy skipped (Fade.exe may be running and locking DLLs - close it first)"
    }
} else { Warn "renderer/build/Release not found" }

# ---- 9. Verify critical files -----------------------------------------------
Write-Host ""
Write-Host "[9] Verifying critical files..." -ForegroundColor Yellow
$checks = [ordered]@{
    "Fade.exe"              = "$ROOT\dist-app\$DistName\Fade.exe"
    "backend.exe"           = "$backend\backend.exe"
    ".env"                  = "$backend\.env"
    "_root.py"              = "$internal\backend\_root.py"
    "render_engine.node"    = "$res\renderer\build\Release\render_engine.node"
    "sksl/gaussian (C++)"   = "$backend\timeline\effects\sksl\gaussian_blur.sksl"
    "sksl/gaussian (py)"    = "$internal\backend\timeline\effects\sksl\gaussian_blur.sksl"
    "torchvision/_C_stable" = "$internal\torchvision\_C_stable.pyd"
    "yolov8n.pt"            = "$res\AIModels\yolov8n.pt"
    "splash.html"           = "$splashDst"
    "pii/scrubber.py"       = "$res\pii\scrubber.py"
}

$ok = 0; $fail = 0
foreach ($kv in $checks.GetEnumerator()) {
    if (Test-Path $kv.Value) { Ok $kv.Key; $ok++ }
    else                     { Fail $kv.Key; $fail++ }
}

$col = if ($fail -eq 0) { "Green" } else { "Yellow" }
Write-Host ""
Write-Host "============================================" -ForegroundColor $col
Write-Host " PATCH COMPLETE  OK:$ok  FAIL:$fail" -ForegroundColor $col
Write-Host "============================================" -ForegroundColor $col
Write-Host ""

if ($fail -gt 0) {
    Write-Host "Some files are missing - see [FAIL] items above." -ForegroundColor Red
    exit 1
}
