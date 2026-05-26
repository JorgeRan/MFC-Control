# Setpoint Fetch Error - FIXED ✅

## Problem
When sending a write setpoint command from the React app, the fetch was failing.

## Root Causes Identified & Fixed

### 1. **Incorrect Device ID to Endpoint Mapping**

**Issue:** The API service was mapping device IDs incorrectly:
- `dev_01` was mapped to `/setpoint-1` but should be `/setpoint-0`
- `dev_02` was mapped to `/setpoint-2` but should be `/setpoint-1`

**Fix Applied:**
```javascript
// BEFORE (incorrect)
const deviceNum = deviceId === 'dev_01' ? 1 : deviceId === 'dev_02' ? 2 : null;
const response = await fetch(`${API_BASE_URL}/setpoint-${deviceNum}`, {

// AFTER (correct)
let endpoint;
if (deviceId === 'dev_01') {
  endpoint = '/setpoint-0';
} else if (deviceId === 'dev_02') {
  endpoint = '/setpoint-1';
}
const response = await fetch(`${API_BASE_URL}${endpoint}`, {
```

**File Updated:** `my-app/src/services/api.js` (setSetpoint function)

---

### 2. **Same Mapping Issue in sendCommand Function**

**Fix Applied:** Applied the same fix to `sendCommand`:
- `dev_01` → `/send-command-0`
- `dev_02` → `/send-command-1`

**File Updated:** `my-app/src/services/api.js` (sendCommand function)

---

### 3. **Missing Error Handling in Broker Endpoints**

**Issue:** When `sendDownlink` failed (e.g., TTN not connected), the error wasn't properly caught and returned to the client.

**Fix Applied:** Added try-catch blocks to all command and setpoint endpoints:

```javascript
// BEFORE (no error handling)
app.post("/setpoint-0", async (req, res) => {
  await sendDownlink([...buf], 15, 1);
  res.json({ ok: true });
});

// AFTER (with error handling)
app.post("/setpoint-0", async (req, res) => {
  try {
    await sendDownlink([...buf], 15, 1);
    res.json({ ok: true });
  } catch (err) {
    console.error("Setpoint error:", err);
    res.status(400).json({ error: err.message });
  }
});
```

**Files Updated:**
- `/setpoint-0` endpoint
- `/setpoint-1` endpoint
- `/send-command-0` endpoint
- `/send-command-1` endpoint

---

### 4. **Fixed Device State Updates**

**Issue:** In `/send-command-1`, it was updating `deviceState_1` instead of `deviceState_2`.

**Before:**
```javascript
if (command === "on") deviceState_1 = true;  // ❌ Wrong state var
```

**After:**
```javascript
if (command === "on") deviceState_2 = true;  // ✅ Correct state var
```

---

## Device ID Mapping Reference

| React Device ID | Broker Command | Broker Setpoint | Internal ID |
|---|---|---|---|
| `dev_01` | `/send-command-0` | `/setpoint-0` | MFC ID 0 |
| `dev_02` | `/send-command-1` | `/setpoint-1` | MFC ID 1 |

---

## Files Modified

1. ✅ `my-app/src/services/api.js`
   - Fixed `sendCommand()` device ID mapping
   - Fixed `setSetpoint()` device ID mapping

2. ✅ `LoRaWAN Broker/lorawan_broker_http.js`
   - Added try-catch error handling to all POST endpoints
   - Fixed `deviceState_2` update in `/send-command-1`

---

## How to Test

1. Start the broker:
   ```bash
   cd LoRaWAN\ Broker && node lorawan_broker_http.js
   ```

2. Start the React app:
   ```bash
   cd my-app && npm run dev
   ```

3. In the React app:
   - Enter a setpoint value (e.g., 5.5)
   - Click "Write Setpoint"
   - Check browser console for success message
   - Check broker console to see the downlink being sent

4. Try the commands (ON/OFF/TOGGLE) - they should now work without fetch errors

---

## Error Messages You Should See Now

### Success Response:
```json
{
  "ok": true
}
```

### Error Response (if TTN is not connected):
```json
{
  "error": "Failed to fetch from TTN API"
}
```

The error will now be properly caught and returned to the client instead of silently failing.

---

## Next Steps (Optional)

If you want to test without TTN connection, you can mock the `sendDownlink` function:

```javascript
// Add this check in sendDownlink function
if (!url) {
  console.log("Skipping downlink (TTN not configured)");
  return { ok: true };
}
```

This will allow testing the UI without requiring TTN to be connected.
