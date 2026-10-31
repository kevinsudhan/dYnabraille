# One-time setup on Windows: Python env for the server, web UI build, server/.env.
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
#   add -NoVision to skip PyTorch/YOLO (~1 GB); the camera still streams, nothing is detected.
param([switch]$NoVision)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "== Server (Python 3.10+)" -ForegroundColor Cyan
$python = if (Get-Command py -ErrorAction SilentlyContinue) { 'py' } else { 'python' }
if (-not (Test-Path server\.venv)) { & $python -m venv server\.venv }
$pip = 'server\.venv\Scripts\python.exe'
& $pip -m pip install --upgrade pip --quiet
$req = if ($NoVision) { 'server\requirements.txt' } else { 'server\requirements-vision.txt' }
& $pip -m pip install -r $req -r server\requirements-dev.txt --quiet
if ($LASTEXITCODE) { throw 'pip install failed' }

if (-not (Test-Path server\.env)) {
    $token = 'db-' + -join ((48..57) + (97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
    $text = (Get-Content server\.env.example -Raw) -replace '(?m)^DEVICE_TOKEN=.*$', "DEVICE_TOKEN=$token"
    # No byte-order mark: Python would read it as part of the first line.
    [IO.File]::WriteAllText((Join-Path $root 'server\.env'), $text, (New-Object Text.UTF8Encoding $false))
    Write-Host "Created server\.env with a new DEVICE_TOKEN" -ForegroundColor Green
}

Write-Host "== Web UI (Node 18+)" -ForegroundColor Cyan
Push-Location web
npm install --no-audit --no-fund
if ($LASTEXITCODE) { throw 'npm install failed' }
npm run build
if ($LASTEXITCODE) { throw 'web build failed' }
Pop-Location

Write-Host ""
Write-Host "Done. Next:" -ForegroundColor Green
Write-Host "  1. Put ELEVENLABS_API_KEY (starts with sk_) in server\.env"
Write-Host "  2. server\.venv\Scripts\python server\scripts\provision_agent.py"
Write-Host "  3. scripts\start.ps1"
