# Debug Guide - Setpoint Control Issue

## Problem Statement
Both setpoint buttons appear to control MFC-BL (dev_01).

## Debugging Instructions

### Step 1: Check Browser Console Logs
When you click the "Write Setpoint" button:

1. Open browser DevTools (F12)
2. Go to Console tab
3. Select a device (dev_02 - MFC-BK)
4. Enter a setpoint value
5. Click "Write Setpoint"

**Look for logs like:**
```
[CommandSection] Sending setpoint to device: dev_02, value: 5.5
[setSetpoint] Device: dev_02, Endpoint: /setpoint-1, Value: 5.5
[setSetpoint] Success for dev_02
```

### Step 2: Check Broker Console Logs
Look at the broker terminal output when you click the button:

**For dev_01 (should see):**
```
[/setpoint-0] Setting setpoint for dev_01 (MFC-BL) to 5.5
[/setpoint-0] Updated lastSetpoint_1 to 5.5
```

**For dev_02 (should see):**
```
[/setpoint-1] Setting setpoint for dev_02 (MFC-BK) to 5.5
[/setpoint-1] Updated lastSetpoint_2 to 5.5
```

### Step 3: Check Network Tab
1. Open DevTools Network tab
2. Click setpoint button
3. Look for POST request to:
   - `/setpoint-0` for dev_01
   - `/setpoint-1` for dev_02

### Step 4: Verify Device Tabs
Make sure device tabs work correctly:
1. Click "MFC-BK" tab - should show dev_02
2. Click "MFC-BL" tab - should show dev_01

## Possible Issues & Solutions

### Issue 1: Both buttons always send to /setpoint-0
**Cause:** `activeDeviceId` is not being updated when switching devices

**Check:** 
- Open DevTools console
- Switch to dev_02
- Check if `[CommandSection] Sending setpoint to device: dev_02` appears
- If it shows `dev_01`, then the device tab switch isn't working

**Fix:** Check DeviceTabs component - `onSelectDevice` callback

### Issue 2: Logs show correct endpoint but wrong device is controlled
**Cause:** Broker endpoints are mixed up

**Check:**
- /setpoint-0 should update lastSetpoint_1 (dev_01)
- /setpoint-1 should update lastSetpoint_2 (dev_02)

**Look for:** The console logs from broker after clicking button

### Issue 3: No logs appear in browser or broker
**Cause:** Request never reached the server or JavaScript error

**Check:**
- Is broker running? (check `http://localhost:3000/devices`)
- Are there JavaScript errors in browser console?
- Check Network tab - is request being sent?

## Data Flow Diagram

```
User clicks "Write Setpoint" for dev_02
           ↓
CommandSection.handleSetpoint()
  - logs: [CommandSection] Sending setpoint to device: dev_02
           ↓
api.setSetpoint('dev_02', value)
  - determines endpoint = '/setpoint-1'
  - logs: [setSetpoint] Device: dev_02, Endpoint: /setpoint-1
           ↓
fetch('http://localhost:3000/setpoint-1', POST)
           ↓
Broker receives POST /setpoint-1
  - logs: [/setpoint-1] Setting setpoint for dev_02 (MFC-BK) to 5.5
  - updates lastSetpoint_2 = value
  - logs: [/setpoint-1] Updated lastSetpoint_2 to 5.5
           ↓
Returns: { ok: true }
           ↓
Browser console: Setpoint set to 5.5
```

## Quick Checklist

- [ ] Device tabs switch between dev_01 and dev_02
- [ ] Browser console shows correct device ID in logs
- [ ] Broker console shows correct endpoint being called
- [ ] Network tab shows POST to correct endpoint
- [ ] lastSetpoint_1 and lastSetpoint_2 are different values
- [ ] StatusCards display correct setpoint for selected device

## Next Step
Once you've identified which log is missing or incorrect, share the console output and we can pinpoint the exact issue.
