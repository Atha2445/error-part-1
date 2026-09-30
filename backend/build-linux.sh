#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
DIST="$BACKEND/dist/Vigilinx"

echo "=== Vigilinx Linux Build ==="
echo ""

# ── System dependencies ──
echo "[1/5] Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
  python3.11 python3.11-venv python3.11-dev \
  build-essential libgl1-mesa-glx libglib2.0-0 \
  nodejs npm

# ── Python venv ──
echo "[2/5] Creating Python virtual environment..."
cd "$BACKEND"
python3.11 -m venv .venv
source .venv/bin/activate
pip install --quiet --upgrade pip setuptools wheel
pip install --quiet pyinstaller
pip install --quiet -r requirements.txt

# ── Frontend build ──
echo "[3/5] Building frontend..."
cd "$FRONTEND"
npm install --silent
npm run build

# ── PyInstaller ──
echo "[4/5] Running PyInstaller..."
cd "$BACKEND"
pyinstaller --clean vigilinx_linux.spec

echo "[5/5] Build complete!"
echo ""
echo "=== Deployable artifact ==="
echo "  $DIST"
echo ""
echo "Copy the Vigilinx folder to your target VM and run:"
echo "  ./Vigilinx"
echo ""
echo "The app will be available at http://0.0.0.0:8000"
