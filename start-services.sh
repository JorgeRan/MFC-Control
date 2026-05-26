#!/bin/bash
# Start MFC-Control with Python FastAPI backend and React frontend

set -e

echo "==================== MFC-Control Startup Script ===================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check for virtual environment
if [ ! -d "mass-flow-controller/.venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    cd mass-flow-controller
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    cd ..
else
    echo -e "${GREEN}Virtual environment found${NC}"
    source mass-flow-controller/.venv/bin/activate
fi

echo ""
echo "==================== Starting Services ===================="
echo ""

# Start Python API server in background
echo -e "${GREEN}Starting FastAPI server on port 5000...${NC}"
cd mass-flow-controller
python api_server.py &
API_PID=$!
echo "FastAPI PID: $API_PID"
cd ..

# Give API time to start
sleep 2

# Start React frontend in another terminal or background
echo -e "${GREEN}Starting React frontend on port 5173...${NC}"
cd app
npm install > /dev/null 2>&1 || true
npm run dev &
FRONTEND_PID=$!
echo "Frontend PID: $FRONTEND_PID"
cd ..

echo ""
echo "==================== Services Started ===================="
echo ""
echo -e "${GREEN}✓ FastAPI API Server: http://localhost:5000${NC}"
echo -e "${GREEN}✓ React Frontend: http://localhost:5173${NC}"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "Shutting down services..."
    kill $API_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    wait $API_PID 2>/dev/null || true
    wait $FRONTEND_PID 2>/dev/null || true
    echo "Services stopped."
    exit 0
}

# Trap Ctrl+C
trap cleanup SIGINT SIGTERM

# Wait for processes
wait $API_PID $FRONTEND_PID 2>/dev/null || true
