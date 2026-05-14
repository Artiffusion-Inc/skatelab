#!/usr/bin/env bash
set -euo pipefail

LOG_FILE="${MODEL_LOG_FILE:-/tmp/skatelab-server.log}"

# Ensure log file exists
touch "$LOG_FILE"

# Start FastAPI model server in background
# PYTHONUNBUFFERED=1 ensures logs flush immediately for PyWorker tailing
PYTHONUNBUFFERED=1 python -m uvicorn gpu_server.server:app --host 0.0.0.0 --port 8000 >> "$LOG_FILE" 2>&1 &

# Wait until port 8000 is accepting connections
for i in $(seq 1 120); do
    if python -c "import socket; s=socket.socket(); s.settimeout(1); s.connect(('127.0.0.1', 8000)); s.close()" 2>/dev/null; then
        echo "Model server ready on port 8000"
        break
    fi
    sleep 1
done

# Start PyWorker — monitors log file, proxies requests, reports to Vast.ai
exec python -m gpu_server.worker