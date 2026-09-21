<#
.SYNOPSIS
    Hotfix-deploy Python source changes to the production build without a full rebuild.
    Run after any .py edit to instantly sync changes to dist-app.

.USAGE
    .\scripts\hotfix_deploy.ps1
    .\scripts\hotfix_deploy.ps1 -Files "routers\project.py","ai\agent.py"
#>
param([string[]]$Files = @())

$SRC = "E:\Echo\backend"
$DST = "E:\Echo\dist-app\win-unpacked\resources\backend\_internal\backend"

if (-not (Test-Path $DST)) {
    Write-Host "ERROR: Build not found at $DST" -ForegroundColor Red; exit 1
}

taskkill /F /IM backend.exe /T 2>$null | Out-Null; Start-Sleep 1

$list = if ($Files.Count -eq 0) {
    Get-ChildItem $SRC -Recurse -Filter "*.py" | ForEach-Object {
        $_.FullName.Substring($SRC.Length + 1) }
} else { $Files }

foreach ($f in $list) {
    $s = Join-Path $SRC $f; $d = Join-Path $DST $f
    if (-not (Test-Path $s)) { continue }
    New-Item -ItemType Directory -Force (Split-Path $d) | Out-Null
    Copy-Item $s $d -Force
    $cache = Join-Path (Split-Path $d) "__pycache__"
    $stem = [System.IO.Path]::GetFileNameWithoutExtension($d)
    if (Test-Path $cache) { Get-ChildItem $cache -Filter "$stem*.pyc" | Remove-Item -Force }
    Write-Host "  ✓ $f"
}
Write-Host "Hotfix deployed — reopen Echo.exe" -ForegroundColor Green
