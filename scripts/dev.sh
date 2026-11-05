#!/usr/bin/env bash
set -e

echo "=========================================================="
echo " Starting Hypothesis Autonomous Simulation Web Suite"
echo "=========================================================="
echo " [API] Launching FastAPI streaming backend on http://127.0.0.1:8000..."
uv run --no-sync uvicorn web.app:app --host 127.0.0.1 --port 8000 --reload &
BACKEND_PID=$!

echo " [UI]  Launching Next.js frontend on http://localhost:3000..."
(cd web && npm run dev) &
FRONTEND_PID=$!

cleanup() {
    echo ""
    echo "Shutting down Hypothesis servers..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
}

trap cleanup INT TERM EXIT
wait
