#!/bin/bash
set -e
cd /app

# Render / 云平台注入 PORT；本地默认 8000
PORT="${PORT:-8000}"

alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
