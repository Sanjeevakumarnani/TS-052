#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ ! -d "$ROOT/backend/.venv" ]; then echo "Missing backend/.venv. See README.md setup instructions."; exit 1; fi
if [ ! -d "$ROOT/frontend/node_modules" ]; then echo "Missing frontend/node_modules. Run npm install in frontend/ first."; exit 1; fi
cd "$ROOT/backend"
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000 & API_PID=$!
cd "$ROOT/frontend"
npm run dev & WEB_PID=$!
cleanup(){ kill "$API_PID" "$WEB_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
wait
