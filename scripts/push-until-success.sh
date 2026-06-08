#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

REMOTE="${1:-origin}"
BRANCH="${2:-main}"
INTERVAL="${3:-30}"

echo "==> 推送到 ${REMOTE}/${BRANCH}，失败每 ${INTERVAL}s 重试…"
echo "==> 远程: $(git remote get-url "$REMOTE" 2>/dev/null || echo '?')"

attempt=0
while true; do
  attempt=$((attempt + 1))
  echo ""
  echo "[$(date '+%H:%M:%S')] 第 ${attempt} 次尝试…"
  if git push -u "$REMOTE" "$BRANCH"; then
    echo ""
    echo "✓ 推送成功: $(git remote get-url "$REMOTE") ($BRANCH @ $(git rev-parse --short HEAD))"
    exit 0
  fi
  echo "× 失败，${INTERVAL}s 后重试…"
  sleep "$INTERVAL"
done
