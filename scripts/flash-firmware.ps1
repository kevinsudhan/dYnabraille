# Build and flash the ESP32 over USB with PlatformIO (installed locally on first run).
#   powershell -ExecutionPolicy Bypass -File scripts\flash-firmware.ps1                 main firmware
#   powershell -ExecutionPolicy Bypass -File scripts\flash-firmware.ps1 -PinFinder      wiring finder
#   ... -Port COM5      pick the port (default: PlatformIO auto-detects)
#   ... -Monitor        open the serial monitor afterwards (Ctrl+C to leave)
# Close anything else using the port first (Arduino Serial Monitor, the server's USB link).
param([switch]$PinFinder, [string]$Port, [switch]$Monitor)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$fw = Join-Path $root 'firmware'
$pio = Join-Path $fw '.pio-venv\Scripts\pio.exe'

if (-not (Test-Path $pio)) {
    Write-Host 'Installing PlatformIO (one time)...' -ForegroundColor Cyan
    $python = if (Get-Command py -ErrorAction SilentlyContinue) { 'py' } else { 'python' }
    & $python -m venv (Join-Path $fw '.pio-venv')
    & (Join-Path $fw '.pio-venv\Scripts\python.exe') -m pip install --quiet platformio
}

$project = $fw
if ($PinFinder) {
    $project = Join-Path $fw 'tools'
} else {
    $config = Join-Path $fw 'dynabraille_esp32\config.h'
    if (-not (Test-Path $config)) {
        Copy-Item (Join-Path $fw 'dynabraille_esp32\config.example.h') $config
        Write-Host "Created $config" -ForegroundColor Yellow
    }
    # Keep the firmware's DEVICE_TOKEN in step with the server's.
    $envFile = Join-Path $root 'server\.env'
    if (Test-Path $envFile) {
        $token = (Select-String -Path $envFile -Pattern '^DEVICE_TOKEN=(.+)$').Matches.Groups[1].Value.Trim()
        if ($token) {
            $text = Get-Content $config -Raw
            $updated = $text -replace '#define DEVICE_TOKEN ".*"', "#define DEVICE_TOKEN `"$token`""
            if ($updated -ne $text) {
                [IO.File]::WriteAllText($config, $updated, (New-Object Text.UTF8Encoding $false))
                Write-Host 'Synced DEVICE_TOKEN from server\.env'
            }
        }
    }
    if ((Get-Content $config -Raw) -match 'your-wifi-name') {
        Write-Warning "Set WIFI_SSID_1 / WIFI_PASS_1 in $config - the cell can't join WiFi with the placeholders (USB serial still works)."
    }
}

$uploadArgs = @('run', '-d', $project, '-t', 'upload')
if ($Port) { $uploadArgs += @('--upload-port', $Port) }
& $pio @uploadArgs
if ($LASTEXITCODE) { throw 'Upload failed. If it stopped at "Connecting...", hold the BOOT button and try again.' }

if ($Monitor) {
    $monitorArgs = @('device', 'monitor', '-d', $project)
    if ($Port) { $monitorArgs += @('--port', $Port) }
    & $pio @monitorArgs
}
