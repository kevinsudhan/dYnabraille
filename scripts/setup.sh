#!/usr/bin/env bash
# One-time setup on macOS / Linux / Raspberry Pi. Add --no-vision to skip PyTorch/YOLO.
set -euo pipefail
cd "$(dirname "$0")/.."
req=server/requirements-vision.txt
[[ "${1:-}" == "--no-vision" ]] && req=server/requirements.txt
[[ -d server/.venv ]] || python3 -m venv server/.venv
server/.venv/bin/pip install --upgrade pip -q
server/.venv/bin/pip install -r "$req" -r server/requirements-dev.txt -q
if [[ ! -f server/.env ]]; then
  token="db-$(python3 -c 'import secrets; print(secrets.token_hex(12))')"
  sed "s/^DEVICE_TOKEN=.*/DEVICE_TOKEN=$token/" server/.env.example > server/.env
  echo "Created server/.env with a new DEVICE_TOKEN"
fi
(cd web && npm install --no-audit --no-fund && npm run build)
echo "Done. Put ELEVENLABS_API_KEY in server/.env, run server/.venv/bin/python server/scripts/provision_agent.py, then scripts/start.sh"
