# Run the DynaBraille server (dashboard, iPhone camera page, ESP32 link).
#   powershell -ExecutionPolicy Bypass -File scripts\start.ps1
# The first time Windows asks, allow Python through the firewall on Private networks,
# otherwise the iPhone and the ESP32 can't reach this computer.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path server\.venv)) { throw 'Run scripts\setup.ps1 first.' }
if (-not (Test-Path web\dist\index.html)) {
    Push-Location web; npm run build; Pop-Location
}
Set-Location server
& .\.venv\Scripts\python.exe -m dynabraille
