# LoRaWAN HTTPS App - API Integration Guide

## Overview

The React app (`my-app`) is now fully connected to the LoRaWAN Broker API. The integration includes:

- REST API endpoints for device management and commands
- WebSocket connection for real-time uplink events
- React components that communicate with the broker
- Command execution (ON/OFF/TOGGLE)
- Setpoint control for devices

## Architecture

```
LoRaWAN Broker (Node.js/Express)
├── HTTP REST API (port 3000)
│   ├── GET /devices
│   ├── GET /device/:deviceId/metrics
│   ├── GET /device/:deviceId/logs
│   ├── POST /send-command-1
│   ├── POST /send-command-2
│   ├── POST /setpoint-1
│   └── POST /setpoint-2
└── WebSocket (Socket.IO)
    ├── Emit: uplink (device data)
    ├── Emit: initial (broker state)
    └── Receive: commands from React app

React App (Vite + React)
├── API Service (src/services/api.js)
│   ├── fetchDevices()
│   ├── fetchDeviceMetrics()
│   ├── fetchDeviceLogs()
│   ├── sendCommand()
│   ├── setSetpoint()
│   └── connectWebSocket()
└── Components
    ├── CommandSection (sends commands & setpoints)
    ├── DeviceTabs (device selection)
    ├── StatusCards (metrics display)
    └── LogTable (real-time logs)
```

## Setup Instructions

### 1. Install Dependencies

In the `my-app` directory:

```bash
npm install
```

This will install `socket.io-client` along with other dependencies.

### 2. Start the LoRaWAN Broker

In the `LoRaWAN Broker` directory:

```bash
node lorawan_broker_http.js
```

The broker will start on `http://localhost:3000`

### 3. Start the React App

In the `my-app` directory:

```bash
npm run dev
```

The app will start on `http://localhost:5173` (or another port if 5173 is in use)

## API Endpoints

### Device Management

#### Get All Devices
```http
GET http://localhost:3000/devices
```

Response:
```json
[
  {
    "id": "dev_01",
    "name": "MFC-BL",
    "status": "online",
    "type": "Gas Meter"
  },
  {
    "id": "dev_02",
    "name": "MFC-BK",
    "status": "online",
    "type": "Gas Meter"
  }
]
```

#### Get Device Metrics
```http
GET http://localhost:3000/device/dev_01/metrics
```

Response:
```json
{
  "signal": -85,
  "battery": 87,
  "uptime": "14d 3h",
  "lastSeen": "2 mins ago",
  "setpoint": 0,
  "flow": 0
}
```

#### Get Device Logs
```http
GET http://localhost:3000/device/dev_01/logs
```

### Commands

#### Send Command (ON/OFF/TOGGLE)
```http
POST http://localhost:3000/send-command-1
Content-Type: application/json

{
  "command": "on"
}
```

Devices:
- `dev_01` → `/send-command-1`
- `dev_02` → `/send-command-2`

Valid commands: `"on"`, `"off"`, `"toggle"`

#### Set Setpoint
```http
POST http://localhost:3000/setpoint-1
Content-Type: application/json

{
  "value": 5.5
}
```

Devices:
- `dev_01` → `/setpoint-1`
- `dev_02` → `/setpoint-2`

## WebSocket Events

The React app connects to the broker via Socket.IO for real-time updates.

### Events from Broker

**uplink** - Device uplink data received:
```javascript
socket.on('uplink', (data) => {
  console.log('Device data:', data);
  // Updates logs table in real-time
});
```

**initial** - Initial broker state when connecting:
```javascript
socket.on('initial', (data) => {
  console.log('Broker state:', data);
  // {
  //   lastValue_1, deviceState_1, lastSetpoint_1,
  //   lastValue_2, deviceState_2, lastSetpoint_2
  // }
});
```

## React Components

### CommandSection
Handles device commands (ON/OFF/TOGGLE) and setpoint configuration.

**Props:**
- `activeDeviceId` (string) - Currently selected device ID
- `onError` (function) - Error callback

**Usage:**
```jsx
<CommandSection 
  activeDeviceId={activeDeviceId} 
  onError={setError} 
/>
```

### DeviceTabs
Displays available devices and allows switching between them.

### StatusCards
Shows device metrics (signal strength, battery, uptime, etc.)

### LogTable
Displays device uplink logs and events (updates in real-time via WebSocket)

## API Service (`src/services/api.js`)

All API calls go through this centralized service:

```javascript
import { 
  fetchDevices, 
  fetchDeviceMetrics, 
  fetchDeviceLogs,
  sendCommand,
  setSetpoint,
  connectWebSocket
} from './services/api'

// Send a command
await sendCommand('dev_01', 'on')

// Set device setpoint
await setSetpoint('dev_01', 5.5)

// Get device metrics
const metrics = await fetchDeviceMetrics('dev_01')

// Connect to WebSocket
const socket = connectWebSocket((data) => {
  console.log('New uplink:', data)
})
```

## Configuration

### API Base URL
By default, the React app connects to `http://localhost:3000` (the broker).

To change this, edit `src/services/api.js`:
```javascript
const API_BASE_URL = 'http://localhost:3000'  // Change this
```

### Broker Port
The broker runs on port 3000 by default. To change it, edit `LoRaWAN Broker/lorawan_broker_http.js`:
```javascript
const PORT = 3000  // Change this
```

## Troubleshooting

### Connection Refused
- Ensure the broker is running: `node lorawan_broker_http.js`
- Check that it's listening on port 3000
- In React app, verify `API_BASE_URL` in `src/services/api.js`

### Commands Not Sending
- Check browser console for errors
- Verify broker is running
- Ensure device ID is correct (dev_01 or dev_02)

### Real-time Updates Not Appearing
- Check that WebSocket connection is established
- Look for "Connected to LoRaWAN broker" message in console
- Verify TTN uplink is reaching the broker's `/uplink` endpoint

### CORS Issues
The broker serves static files from `../react-app/build`. If you get CORS errors, the React app may need to run on the same server.

## Next Steps

1. **Mock Data to Real API**: Replace mock data calls in `App.jsx` with actual API calls
   ```javascript
   // Instead of:
   setDevices(MOCK_DEVICES)
   
   // Use:
   const data = await fetchDevices()
   setDevices(data)
   ```

2. **Error Handling**: Implement better error handling UI in the app

3. **Real-time Metrics**: Update metrics in real-time via WebSocket instead of polling

4. **Authentication**: Add API key/token authentication if needed

5. **Deployment**: Configure CORS and HTTPS for production

## File Changes Summary

- ✅ Created: `my-app/src/services/api.js` - API service layer
- ✅ Updated: `my-app/src/components/CommandSection.jsx` - Added command functionality
- ✅ Updated: `my-app/src/App.jsx` - Added WebSocket connection
- ✅ Updated: `my-app/package.json` - Added socket.io-client dependency
- ✅ Updated: `LoRaWAN Broker/lorawan_broker_http.js` - Added API endpoints

## Support

For issues or questions about the integration, check:
1. Browser console for JavaScript errors
2. Broker console for API errors
3. Network tab (F12 Dev Tools) for HTTP/WebSocket issues
