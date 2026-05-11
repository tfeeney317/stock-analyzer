#!/bin/bash

echo "========================================="
echo "   Starting Stock Analyzer Dashboard"
echo "========================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "Stopping servers..."
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    exit 0
}

trap cleanup SIGINT

# Start backend
echo -e "${YELLOW}[1/2]${NC} Starting Backend (FastAPI)..."
cd /Users/feeneyfam/stock-analyzer/backend
PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
echo "   Backend running on http://localhost:8000 (PID: $BACKEND_PID)"

# Wait for backend to start
sleep 3

# Get local IP address
LOCAL_IP=$(ifconfig | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | head -1)

# Start frontend with custom port binding
echo -e "${YELLOW}[2/2]${NC} Starting Frontend (Next.js)..."
cd /Users/feeneyfam/stock-analyzer/frontend
export PATH="/tmp/node-v20.11.0-darwin-arm64/bin:$PATH"
export NEXT_PUBLIC_API_URL="http://${LOCAL_IP}:8000"
npm run dev -- -p 3000 > /dev/null 2>&1 &
FRONTEND_PID=$!
echo "   Frontend running on http://${LOCAL_IP}:3000 (PID: $FRONTEND_PID)"

echo ""
echo "========================================="
echo -e "${GREEN}✓ Dashboard is ready!${NC}"
echo ""
echo "   Local:   http://localhost:3000"
echo "   Network: http://${LOCAL_IP}:3000"
echo ""
echo "   API:     http://${LOCAL_IP}:8000"
echo ""
echo "Press Ctrl+C to stop both servers"
echo "========================================="

# Wait forever (until Ctrl+C)
wait