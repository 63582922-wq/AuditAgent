#!/usr/bin/env bash
# 停止本地前后端 dev 进程，避免多实例争抢 .next / 端口
set -euo pipefail

stop_port() {
  local port="$1"
  local pids
  pids=$(lsof -t -i ":$port" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "停止端口 :$port 上的进程: $pids"
    kill $pids 2>/dev/null || kill -9 $pids 2>/dev/null || true
  fi
}

stop_port 3000
stop_port 8000

# 清理遗留 next build（常见死锁来源）
pkill -f "next build" 2>/dev/null || true
pkill -f "jest-worker/processChild" 2>/dev/null || true

echo "已停止本地 dev 服务"
