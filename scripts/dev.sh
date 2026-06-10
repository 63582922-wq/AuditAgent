#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

cd backend
python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate
if [ ! -f .env ]; then cp .env.example .env; fi

if ! curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then
  echo "==> 启动 FastAPI (8000)"
  uvicorn app.main:app --host 127.0.0.1 --port 8000 &
  BACKEND_PID=$!
  sleep 2
else
  echo "==> 后端已在运行 (8000)"
  BACKEND_PID=""
fi

cd ..
bash scripts/dev-frontend.sh
