# Fade Full Build Script - Usage: .\scripts\build_full.ps1
Set-StrictMode -Version Latest
$ROOT = Split-Path $PSScriptRoot -Parent

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " FADE FULL BUILD" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. PyInstaller backend (handles compiled deps: skia, torch, cv2, etc.)
Write-Host "[1/5] Building Python backend (PyInstaller)..." -ForegroundColor Yellow
Push-Location $ROOT
# PyInstaller writes INFO logs to stderr - we pipe both streams to the log file
# and check exit code manually (do not use $ErrorActionPreference = Stop here)
$ErrorActionPreference = "Continue"
& ".venv\Scripts\pyinstaller.exe" backend.spec --distpath pyinstaller-dist --workpath pyinstaller-build --noconfirm *>&1 | Tee-Object -FilePath "pyinstaller-build.log"
$pyExit = $LASTEXITCODE
$ErrorActionPreference = "Stop"
Pop-Location
if ($pyExit -ne 0) { throw "PyInstaller failed (exit $pyExit)! See pyinstaller-build.log" }
Write-Host "  [OK] Backend built" -ForegroundColor Green

# 2. Electron + Vite
Write-Host ""
Write-Host "[2/5] Building Electron + Vite..." -ForegroundColor Yellow
Push-Location $ROOT
$ErrorActionPreference = "Continue"
& npm run dist *>&1
$npmExit = $LASTEXITCODE
$ErrorActionPreference = "Stop"
Pop-Location
if ($npmExit -ne 0) { throw "npm run dist failed (exit $npmExit)!" }
Write-Host "  [OK] Electron built -> dist-app\win-unpacked" -ForegroundColor Green

# 3. Copy backend bundle to dist-app
Write-Host ""
Write-Host "[3/5] Copying backend bundle to dist-app..." -ForegroundColor Yellow
$dst_backend = Join-Path $ROOT "dist-app\win-unpacked\resources\backend"
if (Test-Path $dst_backend) { Remove-Item $dst_backend -Recurse -Force }
Copy-Item (Join-Path $ROOT "pyinstaller-dist\backend") $dst_backend -Recurse -Force
Write-Host "  [OK] Backend bundle copied" -ForegroundColor Green

# 4. Overlay FULL backend Python source as loose .py files
#    This ensures no module is ever missed by PyInstaller's analysis.
#    Compiled deps (torch, skia, etc.) still come from the PYZ/DLLs.
Write-Host ""
Write-Host "[4/5] Overlaying backend source (.py files)..." -ForegroundColor Yellow
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

$pyCount = (Get-ChildItem $dstBackendSrc -Recurse -Filter "*.py").Count
Write-Host "  [OK] $pyCount .py files overlaid into _internal/" -ForegroundColor Green

# 5. Post-build patch - applies ALL known fixes in one pass
Write-Host ""
Write-Host "[5/5] Running post-build patch..." -ForegroundColor Yellow
& "$ROOT\scripts\post_build_patch.ps1" -DistName "win-unpacked"
if ($LASTEXITCODE -ne 0) { throw "Post-build patch reported failures - see output above." }