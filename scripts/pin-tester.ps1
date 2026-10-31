# Clickable pin tester: press the ESP32's pins in a browser and see which solenoid moves.
#   powershell -ExecutionPolicy Bypass -File scripts\pin-tester.ps1 -Port COM5
# Needs the pin finder on the board (scripts\flash-firmware.ps1 -PinFinder) and COM5 free.
# Ctrl+C stops it and frees the port.
param([string]$Port)
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root 'server\.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'Run scripts\setup.ps1 first.' }
$toolArgs = @((Join-Path $root 'firmware\tools\pin_tester.py'))
if ($Port) { $toolArgs += @('--port', $Port) }
& $python @toolArgs
