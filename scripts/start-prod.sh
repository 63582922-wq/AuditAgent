#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> 生成测试样例"
cd backend && source .venv/bin/activate 2>/dev/null || true
python ../scripts/create_fixtures.py

echo "==> Docker Compose 生产模式启动"
export API_KEY="${API_KEY:-fxpg-dev-key}"
docker compose up -d --build

echo ""
echo "前端: http://localhost:3000"
echo "后端: http://localhost:8000/docs"
echo "API Key: $API_KEY"
