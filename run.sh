#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"

echo "Starting Vigilinx on http://localhost:8000"
cd "$BACKEND_DIR"
exec .venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
