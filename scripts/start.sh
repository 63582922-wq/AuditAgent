#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> 启动 PostgreSQL (docker compose)"
docker compose up -d postgres

echo "==> 等待数据库就绪..."
sleep 3

echo "==> 安装后端依赖"
cd backend
python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate
pip install -r requirements.txt -q

if [ ! -f .env ]; then
  cp .env.example .env
fi

echo "==> 启动 FastAPI (8000)"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

cd ../frontend
echo "==> 安装前端依赖"
npm install -q

echo "==> 启动 Next.js (3000)"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "后端: http://localhost:8000/docs"
echo "前端: http://localhost:3000"
echo "按 Ctrl+C 停止"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
