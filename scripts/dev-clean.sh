#!/usr/bin/env bash
# 深度清理前端构建缓存（仅在异常/卡死时使用，日常 dev 不必跑）
set -euo pipefail
cd "$(dirname "$0")/../frontend"

"$(dirname "$0")/stop-dev.sh"

echo "==> 清理 .next / 备份 / trash"
rm -rf .next .next.bak .next.trash.* tsconfig.tsbuildinfo

echo "完成。请运行: ./scripts/dev-frontend.sh"
