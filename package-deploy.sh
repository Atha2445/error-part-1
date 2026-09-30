#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
OUTDIR="$ROOT/vigilinx-deploy"
ARCHIVE="$ROOT/vigilinx-deploy.tar.gz"

echo "=== Packaging Vigilinx for VM deploy ==="
rm -rf "$OUTDIR"
mkdir -p "$OUTDIR/backend"
mkdir -p "$OUTDIR/frontend"

# Backend — only runtime files, no .venv, no __pycache__, no build tools
cp "$ROOT/backend/main.py" "$OUTDIR/backend/"
cp "$ROOT/backend/requirements.txt" "$OUTDIR/backend/"
cp "$ROOT/backend/.env" "$OUTDIR/backend/" 2>/dev/null || true

mkdir -p "$OUTDIR/backend/services"
cp "$ROOT/backend/services"/*.py "$OUTDIR/backend/services/"

mkdir -p "$OUTDIR/backend/reusable_auth"
cp "$ROOT/backend/reusable_auth"/*.py "$OUTDIR/backend/reusable_auth/"

# Frontend — production build only
cp -r "$ROOT/frontend/build" "$OUTDIR/frontend/build"

# Run script for the VM
cat > "$OUTDIR/run.sh" << 'SCRIPT'
#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR/backend"

echo "Setting up Python environment..."
python3 -m venv .venv
source .venv/bin/activate
pip install -q --upgrade pip setuptools wheel
pip install -q -r requirements.txt

echo "Starting Vigilinx on http://0.0.0.0:8000"
exec python -m uvicorn main:app --host 0.0.0.0 --port 8000
SCRIPT
chmod +x "$OUTDIR/run.sh"

# Create archive
tar -czf "$ARCHIVE" -C "$ROOT" vigilinx-deploy

echo ""
echo "=== Done ==="
du -sh "$ARCHIVE"
echo ""
echo "Copy to your VM and run:"
echo "  scp $ARCHIVE user@<vm-ip>:~/"
echo "  ssh user@<vm-ip>"
echo "  tar -xzf vigilinx-deploy.tar.gz"
echo "  cd vigilinx-deploy && bash run.sh"
