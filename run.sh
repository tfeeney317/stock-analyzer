#!/bin/bash

echo "Starting Stock Analyzer Dashboard..."
echo ""

echo "Starting Backend (FastAPI)..."
cd /Users/feeneyfam/stock-analyzer/backend
PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
echo "Backend started (PID: $BACKEND_PID)"

sleep 3

echo ""
echo "Starting Frontend (Next.js)..."
cd /Users/feeneyfam/stock-analyzer/frontend
export PATH="/tmp/node-v20.11.0-darwin-arm64/bin:$PATH"
npm run dev &
FRONTEND_PID=$!
echo "Frontend started (PID: $FRONTEND_PID)"

echo ""
echo "=================================="
echo "Dashboard is running!"
echo "Backend: http://localhost:8000"
echo "Frontend: http://localhost:3000"
echo "=================================="
echo ""
echo "Press Ctrl+C to stop both servers"

wait