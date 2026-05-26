# Quick Start Guide - MFC-Control v2.0

## 🚀 Get Running in 5 Minutes

### Prerequisites
- Python 3.9+
- Node.js 16+
- USB connection to MFC device
- Linux/macOS/WSL

### Installation (One Time)
```bash
cd /home/mfc/Desktop/MFC-Control
chmod +x setup.sh
./setup.sh
```
This will:
- ✓ Create Python venv
- ✓ Install all dependencies
- ✓ Verify setup

### Start the System
```bash
chmod +x start-services.sh
./start-services.sh
```

Open: **http://localhost:5173**

### That's It! 🎉

Your system is running:
- **API Backend**: http://localhost:5000
- **Web UI**: http://localhost:5173
- **WebSocket**: Ready for real-time updates

---

## Manual Startup (If Needed)

### Terminal 1 - Start Python API
```bash
cd mass-flow-controller
source .venv/bin/activate
python api_server.py
```

### Terminal 2 - Start React Frontend
```bash
cd app
npm run dev
```

Then open: http://localhost:5173

---

## Configuration

### Change Serial Port
Edit `mass-flow-controller/api_server.py`:
```python
SERIAL_PORT = '/dev/ttyUSB0'  # Change this
```

### Change API Port
Edit `mass-flow-controller/api_server.py`:
```python
PORT = 5000  # Change to desired port
```

Then update `app/src/services/api.js`:
```javascript
return `${protocol}//${window.location.hostname}:5000`;  // Update this
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "No MFC nodes found" | Check USB connection, verify `/dev/ttyUSB0` exists |
| "Port 5000 in use" | Run `lsof -i :5000` and `kill -9 <PID>` |
| "API not responding" | Ensure FastAPI server is running |
| "React console errors" | Check browser console (F12), verify port 5000 alive |

---

## Next Steps

- Read [README.md](README.md) for detailed documentation
- See [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) for v1.0 → v2.0 info
- Check [REFACTORING_SUMMARY.md](REFACTORING_SUMMARY.md) for technical details

---

## API Examples

### Get Device Status
```bash
curl http://localhost:5000/health
```

### List All Devices
```bash
curl http://localhost:5000/nodes
```

### Set Device Setpoint
```bash
curl -X POST http://localhost:5000/setpoint-1 \
  -H "Content-Type: application/json" \
  -d '{"value": 50.5}'
```

---

## Stop Services

Press `Ctrl+C` in the terminal running `start-services.sh`

Or manually:
```bash
pkill -f "python api_server"
pkill -f "npm run dev"
```

---

## Need Help?

1. Check README.md troubleshooting section
2. Look at server console output for error messages
3. Test USB connection: `ls /dev/ttyUSB*`
4. Verify calibration file exists

Happy controlling! 🎯
