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

exec npm run dev -- -H 127.0.0.1 -p 3000
