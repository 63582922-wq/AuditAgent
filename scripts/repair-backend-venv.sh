#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../backend"

# 项目内 .venv 在 Desktop 上易被同步/工具链破坏；固定用用户目录
VENV="${FXPG_VENV:-$HOME/.local/fxpg-venv}"

echo "==> 重建 Python 虚拟环境（修复 bus error / 损坏依赖）"
echo "    路径: $VENV"

PYTHON="/usr/bin/python3"
if [ ! -x "$PYTHON" ]; then
  PYTHON="python3"
fi
echo "    使用: $($PYTHON -V 2>&1)"

# Xcode pip 在 Desktop 项目内常因 CA bundle 路径失效
if [ -z "${SSL_CERT_FILE:-}" ]; then
  for cert in \
    "$HOME/Library/Python/3.9/lib/python/site-packages/certifi/cacert.pem" \
    "$(python3 -c 'import certifi; print(certifi.where())' 2>/dev/null)"; do
    if [ -f "$cert" ]; then
      export SSL_CERT_FILE="$cert"
      break
    fi
  done
fi

rm -rf "$VENV"
"$PYTHON" -m venv "$VENV"
source "$VENV/bin/activate"

pip install -U pip wheel setuptools \
  --trusted-host pypi.org --trusted-host files.pythonhosted.org
pip install -r requirements.txt \
  --trusted-host pypi.org --trusted-host files.pythonhosted.org

if [ ! -f .env ]; then
  cp .env.example .env
  echo "    已创建 .env（默认 SQLite，无需 Docker）"
fi

echo "==> 验证导入..."
(cd "$(dirname "$0")/../backend" && python -c "from app.main import app; print('app import ok')")

echo ""
echo "完成。请运行: ./scripts/dev-backend.sh"
echo "（venv: $VENV）"
