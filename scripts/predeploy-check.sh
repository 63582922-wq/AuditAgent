#!/usr/bin/env bash
# 部署前本地自检（不连外网 API）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Backend config import"
cd "$ROOT/backend"
python3 -c "from app.config import settings; print('DB:', settings.database_url[:32], '...')"

echo "==> Backend tests (quick)"
python3 -m pytest tests/test_orchestrator.py tests/test_pdf_ingest_splitter.py -q --tb=no

echo "==> Frontend typecheck"
cd "$ROOT/frontend"
npx tsc --noEmit

echo "OK — 可推送到 Render Blueprint"
