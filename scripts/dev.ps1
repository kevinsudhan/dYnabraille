# Development: Python server in its own window + Vite dev server (hot reload) here.
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
# Dashboard with hot reload: http://localhost:5173  (proxies /api and /ws to :8000)
# The iPhone camera page still needs the HTTPS server: https://<this-pc>:8443/camera
$root = Split-Path -Parent $PSScriptRoot
Start-Process powershell -ArgumentList '-NoExit', '-Command',
    "Set-Location '$root\server'; .\.venv\Scripts\python.exe -m dynabraille"
Set-Location "$root\web"
npm run dev
