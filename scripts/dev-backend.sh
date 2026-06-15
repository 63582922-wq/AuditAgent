#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../backend"

VENV="${FXPG_VENV:-$HOME/.local/fxpg-venv}"
PY=("$VENV/bin/python")

if [ ! -x "${PY[0]}" ]; then
  echo "未找到 $VENV，正在重建…"
  "$(dirname "$0")/repair-backend-venv.sh"
fi
source "$VENV/bin/activate"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "已创建 backend/.env（SQLite 本地库，可直接开发）"
fi

if curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then
  echo "后端已在运行: http://127.0.0.1:8000/docs"
  exit 0
fi

if lsof -t -i :8000 >/dev/null 2>&1; then
  echo "端口 8000 被非 health 进程占用，请先运行: ./scripts/stop-dev.sh"
  exit 1
fi

echo "==> 启动 FastAPI http://127.0.0.1:8000 (venv: $VENV)"
echo "    文档: http://127.0.0.1:8000/docs"
echo "    若出现 bus error，请运行: ./scripts/repair-backend-venv.sh"
# 默认 uvicorn 事件循环；仅在 bus error 时手动加 --loop asyncio
exec "${PY[@]}" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
