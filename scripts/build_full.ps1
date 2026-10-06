# Fade Full Build Script â€” Usage: .\scripts\build_full.ps1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ROOT = Split-Path $PSScriptRoot -Parent

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host " FADE FULL BUILD" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# 1. PyInstaller backend (handles compiled deps: skia, torch, cv2, etc.)
Write-Host "[1/6] Building Python backend (PyInstaller)..." -ForegroundColor Yellow
Push-Location $ROOT
& ".venv\Scripts\pyinstaller.exe" backend.spec --distpath pyinstaller-dist --workpath pyinstaller-build --noconfirm 2>&1 | Tee-Object -FilePath "pyinstaller-build.log"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed! See pyinstaller-build.log" }
Pop-Location
Write-Host "  [OK] Backend built" -ForegroundColor Green

# 2. Electron + Vite
Write-Host "`n[2/6] Building Electron + Vite..." -ForegroundColor Yellow
Push-Location $ROOT
& npm run dist 2>&1
if ($LASTEXITCODE -ne 0) { throw "npm run dist failed!" }
Pop-Location
Write-Host "  [OK] Electron built -> dist-app\win-unpacked" -ForegroundColor Green

# 3. Copy backend bundle to dist-app
Write-Host "`n[3/6] Copying backend bundle to dist-app..." -ForegroundColor Yellow
$dst_backend = Join-Path $ROOT "dist-app\win-unpacked\resources\backend"
if (Test-Path $dst_backend) { Remove-Item $dst_backend -Recurse -Force }
Copy-Item (Join-Path $ROOT "pyinstaller-dist\backend") $dst_backend -Recurse -Force
Write-Host "  [OK] Backend bundle copied" -ForegroundColor Green

# 4. Overlay FULL backend Python source as loose .py files
#    This ensures no module is ever missed by PyInstaller's analysis.
#    Compiled deps (torch, skia, etc.) still come from the PYZ/DLLs.
Write-Host "`n[4/6] Overlaying backend source (.py files)..." -ForegroundColor Yellow
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

# 5. Copy extra resources
Write-Host "`n[5/6] Copying resources..." -ForegroundColor Yellow
$res = "dist-app\win-unpacked\resources"

# .env to both locations
Copy-Item ".env" "$res\.env" -Force
Copy-Item ".env" "$dst_backend\.env" -Force
Write-Host "  [OK] .env" -ForegroundColor Green

$copies = @{
    "AIModels"                      = "$res\AIModels"
    "renderer\build\Release"        = "$res\renderer\build\Release"
    "templates"                     = "$res\templates"
    "backend\timeline\effects\sksl" = "$internal\backend\timeline\effects\sksl"
    "backend\ai\skills"             = "$internal\backend\ai\skills"
}
foreach ($kv in $copies.GetEnumerator()) {
    $s = Join-Path $ROOT $kv.Key
    if (Test-Path $s) {
        New-Item $kv.Value -ItemType Directory -Force | Out-Null
        Copy-Item "$s\*" $kv.Value -Recurse -Force
        Write-Host "  [OK] $($kv.Key)" -ForegroundColor Green
    }
}

# 6. Verify
Write-Host "`n[6/6] Verifying key files..." -ForegroundColor Yellow
$checks = @(
    "dist-app\win-unpacked\Fade.exe",
    "$dst_backend\backend.exe",
    "$dstBackendSrc\_root.py",
    "$dst_backend\.env",
    "$internal\pii\scrubber.py",
    "$res\renderer\build\Release\render_engine.node"
)
foreach ($f in $checks) {
    if (Test-Path $f) { Write-Host "  [OK]      $f" -ForegroundColor Green }
    else              { Write-Host "  [MISSING] $f" -ForegroundColor Red }
}

$total = (Get-ChildItem "dist-app\win-unpacked" -Recurse -File -EA SilentlyContinue | Measure-Object -Property Length -Sum).Sum
Write-Host "`n========================================" -ForegroundColor Green
Write-Host " BUILD COMPLETE!  $([math]::Round($total/1GB,2)) GB" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green