#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../frontend"

NODE20="$HOME/.local/node20/bin"
if [ -x "$NODE20/node" ]; then
  export PATH="$NODE20:$PATH"
else
  echo "警告: 未找到 $NODE20/node，当前 Node: $(node -v 2>/dev/null || echo missing)"
  echo "Next.js 需要 Node 20。可运行: scripts/install-node20.sh"
fi

if [ ! -d node_modules/next ]; then
  npm install
fi

# 避免多实例同时占用 :3000 与 .next（卡死的首要原因）
if lsof -t -i :3000 >/dev/null 2>&1; then
  echo "端口 3000 已被占用，先停止旧进程…"
  "$(dirname "$0")/stop-dev.sh"
fi

clean_next() {
  [ -d .next ] || return 0
  echo "清理损坏的 .next 缓存…"
  rm -rf .next
}

# 仅在 dev 缓存明确损坏时清理；不要用 main-app.js 判断（Turbopack dev 不会生成该文件）
NEED_CLEAN=0
if [ -d .next/server ]; then
  if [ -f .next/server/server-reference-manifest.json ] && ! node -e "JSON.parse(require('fs').readFileSync('.next/server/server-reference-manifest.json','utf8'))" 2>/dev/null; then
    NEED_CLEAN=1
  fi
fi
if [ "$NEED_CLEAN" = "1" ]; then
  clean_next
fi

echo "==> 启动 Next.js (Turbopack) http://127.0.0.1:3000"
echo "    若仍卡死，请运行: ./scripts/dev-clean.sh 后重试"
exec npm run dev:turbo -- -H 127.0.0.1 -p 3000
