#!/bin/bash
# Setup script for MFC-Control

set -e

echo "============================================"
echo "MFC-Control - Setup & Installation"
echo "============================================"
echo ""

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Setup Python environment
echo "[1/3] Setting up Python environment..."
cd mass-flow-controller

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip setuptools wheel
    pip install -r requirements.txt
    echo "      ✓ Virtual environment created and dependencies installed"
else
    source .venv/bin/activate
    echo "      ✓ Virtual environment already exists"
fi

cd ..

# Setup React environment  
echo ""
echo "[2/3] Setting up React environment..."
cd app

if [ ! -d "node_modules" ]; then
    npm install > /dev/null 2>&1
    echo "      ✓ Node dependencies installed"
else
    echo "      ✓ Node dependencies already installed"
fi

cd ..

# Final checks
echo ""
echo "[3/3] Verifying installation..."

# Test Python imports
if source mass-flow-controller/.venv/bin/activate 2>/dev/null; then
    python3 -c "
import fastapi
import uvicorn
import socketio
import propar
print('      ✓ Python dependencies verified')
" 2>/dev/null || echo "      ⚠ Some Python packages may need attention"
fi

echo ""
echo "============================================"
echo "Setup Complete!"
echo "============================================"
echo ""
echo "Next steps:"
echo ""
echo "1. Start services with:"
echo "   ./start-services.sh"
echo ""
echo "2. Or manually in separate terminals:"
echo ""
echo "   Terminal 1 (API):"
echo "   cd mass-flow-controller"
echo "   source .venv/bin/activate"
echo "   python api_server.py"
echo ""
echo "   Terminal 2 (Frontend):"
echo "   cd app"
echo "   npm run dev"
echo ""
echo "3. Open http://localhost:5173 in your browser"
echo ""
echo "For more information, see README.md"
echo ""
