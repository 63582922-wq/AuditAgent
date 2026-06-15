#!/usr/bin/env bash
# next dev 首屏编译易挂死；生产 build+start 更稳
set -euo pipefail
cd "$(dirname "$0")/../frontend"

NODE20="$HOME/.local/node20/bin"
if [ -x "$NODE20/node" ]; then
  export PATH="$NODE20:$PATH"
fi

if lsof -t -i :3000 >/dev/null 2>&1; then
  echo "端口 3000 已被占用，先运行: ./scripts/stop-dev.sh"
  exit 1
fi

if [ ! -f .next/BUILD_ID ]; then
  echo "==> 首次构建（约 3–5 分钟）…"
  npm run build
fi

echo "==> 启动 Next.js (production) http://127.0.0.1:3000"
exec npm run start -- -H 127.0.0.1 -p 3000
