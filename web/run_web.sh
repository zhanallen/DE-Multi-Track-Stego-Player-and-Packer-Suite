#!/usr/bin/env bash
# StegoPlayer Web API launcher (macOS, secondary platform).
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
HOST="${STEGO_WEB_HOST:-127.0.0.1}"
PORT="${STEGO_WEB_PORT:-8765}"
PYTHON_EXE="python3"
if [ -x ".venv/bin/python" ]; then
  PYTHON_EXE=".venv/bin/python"
fi
echo "[StegoPlayer Web] http://${HOST}:${PORT}  (Ctrl+C to stop)"
exec "$PYTHON_EXE" -m uvicorn web.backend.main:app --host "$HOST" --port "$PORT"
