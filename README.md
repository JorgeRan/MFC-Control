# MFC-Control - Direct Python API Architecture

![Status](https://img.shields.io/badge/status-active-brightgreen)
![Python](https://img.shields.io/badge/python-3.9+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.105-green)
![React](https://img.shields.io/badge/React-18+-blue)

## Overview

MFC-Control is a complete system for controlling Bronkhorst Mass Flow Controllers directly via Python. It replaces the previous LoRaWAN-based architecture with a **direct serial connection** to MFCs and a **FastAPI backend** for HTTP/WebSocket control.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    React Web UI (Port 5173)                 │
│              (Vite + React + Tailwind CSS)                  │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP/WebSocket
                           ↓
┌─────────────────────────────────────────────────────────────┐
│       FastAPI Backend (Port 5000)                           │
│   ├─ REST API Endpoints                                     │
│   ├─ WebSocket Real-time Updates                           │
│   ├─ Session Management                                     │
│   └─ Calibration Handler                                    │
└──────────────────────────┬──────────────────────────────────┘
                           │ Serial Protocol
                           ↓
┌─────────────────────────────────────────────────────────────┐
│      Bronkhorst ProPar Library                              │
│           (USB/Serial Connection)                           │
└──────────────────────────┬──────────────────────────────────┘
                           │ Serial (Modbus)
                           ↓
┌──────────┐    ┌──────────┐    ┌──────────┐
│  MFC-BL  │    │  MFC-BK  │    │   ...    │
│ Address  │    │ Address  │    │          │
│   0x1D   │    │   0xXX   │    │          │
└──────────┘    └──────────┘    └──────────┘
```

## Quick Start

### Prerequisites

- Python 3.9+
- Node.js 16+ (for React development)
- USB serial connection to Bronkhorst MFC device(s)
- Linux/macOS/WSL (Windows requires USB driver setup)

### Installation

1. **Clone and navigate to project**
   ```bash
   cd /home/mfc/Desktop/MFC-Control
   ```

2. **Set up Python environment** (if not already done)
   ```bash
   cd mass-flow-controller
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   cd ..
   ```

3. **Install React dependencies**
   ```bash
   cd app
   npm install
   cd ..
   ```

### Running the System

#### Option 1: Using the startup script (recommended)
```bash
chmod +x start-services.sh
./start-services.sh
```

This will start both services automatically:
- **FastAPI Backend**: http://localhost:5000
- **React Frontend**: http://localhost:5173

#### Option 2: Manual startup

**Terminal 1 - Start Python API:**
```bash
cd mass-flow-controller
source .venv/bin/activate
python api_server.py
```

**Terminal 2 - Start React frontend:**
```bash
cd app
npm run dev
```

Then open: **http://localhost:5173**

## File Structure

```
MFC-Control/
├── start-services.sh              # Startup script (starts both services)
├── README.md                      # This file
├── API_INTEGRATION_GUIDE.md       # Detailed API documentation
│
├── app/                           # React Frontend (Vite)
│   ├── src/
│   │   ├── components/            # React components
│   │   ├── services/
│   │   │   └── api.js            # API client (calls localhost:5000)
│   │   └── App.jsx
│   ├── package.json
│   └── vite.config.ts
│
└── mass-flow-controller/          # Python Backend (FastAPI)
    ├── api_server.py             # Main FastAPI server
    ├── mfc_read.py               # Serial communication + parsing
    ├── shared_resources.py        # Shared MFC bus connection
    ├── calibration_loader.py      # Load MFC calibrations
    ├── requirements.txt           # Python dependencies
    ├── session_state.json         # Persistent session state
    └── MFCCalibrations-*.txt      # Calibration data files
```

## API Endpoints

### REST API (FastAPI on port 5000)

#### Device Management
- `GET /health` - Health check
- `GET /nodes` - Get all connected MFC devices
- `GET /device/{device_id}/metrics` - Get flow/setpoint for device
- `GET /device/{device_name}/fetch-gas` - Get available calibrated gases

#### Session Management
- `POST /start-session` - Start a measurement session
- `GET /session/state` - Get current session state
- `POST /session/state` - Update session state
- `POST /session/state/selected-gas` - Set selected gas for device
- `POST /reset` - Reset/stop all devices

#### Control
- `POST /setpoint-0` - Set MFC-0 setpoint (body: `{"value": 50.5}`)
- `POST /setpoint-1` - Set MFC-1 setpoint
- `POST /refresh` - Refresh all device data

#### WebSocket Events
- `connect` - Client connects, receives initial state
- `device_status` - Real-time device status updates (every 5 seconds)
- `session_updated` - Session state changes
- `setpoint_updated` - After setpoint change
- `session_started` / `session_reset` - Session lifecycle events

## Configuration

### Serial Port & Baud Rate
Edit `mass-flow-controller/api_server.py`:
```python
SERIAL_PORT = '/dev/ttyUSB0'      # Change if using different USB port
SERIAL_BAUD = 38400                # ProPar standard baud rate
```

### API Port
Change in `api_server.py`:
```python
PORT = 5000  # Change to desired port
```

Update React API client in `app/src/services/api.js` if port changes:
```javascript
return `${protocol}//${window.location.hostname}:5000`;
```

### Calibration File
Default: `mass-flow-controller/MFCCalibrations-ReadDirectlyByFlareCode.txt`

## Development

### React Frontend Development
```bash
cd app
npm run dev      # Start with Vite dev server (hot reload)
npm run build    # Production build
npm run preview  # Preview production build
```

### Python Backend Development
```bash
cd mass-flow-controller
source .venv/bin/activate
python api_server.py     # Direct run (debug-friendly)
```

For development with auto-reload:
```bash
pip install uvicorn[standard]
uvicorn api_server:app --reload --port 5000
```

## Troubleshooting

### "No MFC nodes found"
- Check USB cable connection
- Verify device is powered on
- Confirm `SERIAL_PORT` setting matches your device (`/dev/ttyUSB0` vs `COM3`, etc.)
- Test with: `ls /dev/ttyUSB*`

### "module 'propar' has no attribute 'instrument'"
- Ensure `bronkhorst-propar` is installed: `pip install bronkhorst-propar==1.2.0`
- Remove wrong package: `pip uninstall propar`

### API connection refused (5000)
- Make sure FastAPI server is running
- Check if port 5000 is available: `lsof -i :5000`
- Set environment variable: `export VITE_API_BASE_URL=http://localhost:5000`

### React can't connect to API
- Verify both services are running
- Check browser console for CORS errors
- Ensure firewalls allow localhost connections

## Dependencies

### Python
- **fastapi** - Web framework
- **uvicorn** - ASGI server
- **python-socketio** - WebSocket support  
- **bronkhorst-propar** - MFC control library
- **pyserial** - Serial communication

### Node.js/React
- **react** - UI framework
- **vite** - Build tool
- **socket.io-client** - WebSocket client
- **axios** - HTTP client
- **tailwindcss** - Styling

## Performance & Specifications

- **Status Update Rate**: 5 seconds (configurable in `api_server.py`)
- **Setpoint Response Time**: < 1 second
- **Max Setpoint Range**: Device-dependent (typically 0-1000 LN/min)
- **Setpoint Precision**: 0.01 LN/min (calibration-dependent)
- **Serial Baudrate**: 38400 bps (ProPar standard)

## Notes

- The system reads device calibrations from `MFCCalibrations-ReadDirectlyByFlareCode.txt`
- Calibration data is critical for accurate setpoint and flow reading
- WebSocket updates allow real-time monitoring without polling
- Session state persists to `session_state.json` for recovery

## Version History

- **v2.0** - Direct Python API (FastAPI) replaces LoRaWAN broker
- **v1.0** - Original LoRaWAN-based architecture

## License

See LICENSE file in repository root.

## Support

For issues or questions:
1. Check the API_INTEGRATION_GUIDE.md
2. Review error messages in server logs
3. Verify serial connection and MFC power status
4. Check calibration file is present and valid
