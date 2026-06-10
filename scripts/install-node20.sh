#!/usr/bin/env bash
set -euo pipefail

ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ]; then
  NODE_PKG=node-v20.18.3-darwin-arm64
else
  NODE_PKG=node-v20.18.3-darwin-x64
fi

NODE_DIR="$HOME/.local/node20"
TAR="/tmp/${NODE_PKG}.tar.gz"

echo "==> 安装 Node 20 到 $NODE_DIR"
mkdir -p "$NODE_DIR"
curl -fsSL "https://nodejs.org/dist/v20.18.3/${NODE_PKG}.tar.gz" -o "$TAR"
tar -xzf "$TAR" -C "$NODE_DIR" --strip-components=1
"$NODE_DIR/bin/node" -v
echo "完成。启动前端: ./scripts/dev-frontend.sh"
