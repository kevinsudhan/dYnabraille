#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -f web/dist/index.html ]] || (cd web && npm run build)
cd server && exec .venv/bin/python -m dynabraille
