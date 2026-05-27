import asyncio
import csv
import json
import os
import sys
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import serial
from socketio import AsyncServer, ASGIApp

from shared_resources import get_bus, get_instrument, close_all, serial_bus_lock
from calibration_loader import CalibrationLoader, Calibration
from LED_indicator import LEDController
from mfc_status_publisher import append_status_rows_to_csv, resolve_csv_timestamps

led_ctrl = LEDController()

PORT = 5000
SESSION_STATE_FILE = Path(__file__).parent / "session_state.json"
CAL_FILE = Path(__file__).parent / "MFCCalibrations-ReadDirectlyByFlareCode.txt"
SERIAL_PORT = '/dev/ttyUSB0'
SERIAL_BAUD = 38400

app = FastAPI(title="MFC-Control API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sio = AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',
    engineio_logger=False,
    logger=False
)
asgi_app = None  

# Global state
mfc_devices = {}
session_state = {"sessionActive": False, "selectedGases": {}, "updatedAt": None}
calibration_loader = None
ser = None
status_update_task = None
logging_task = None
connected_clients = set()
STATUS_UPDATE_INTERVAL_SECONDS = 30
LOG_INTERVAL_SECONDS = 1.0
DISCOVERY_RETRY_SECONDS = 5
MAX_MFC_DEVICES = 6
DISCOVERY_SCAN_ATTEMPTS = 6
DISCOVERY_SCAN_PAUSE_SECONDS = 0.2
DEVICE_STALE_MISS_THRESHOLD = 12
SERIAL_LOCK_TIMEOUT_SECONDS = 8.0
SERIAL_LOCK_TIMEOUT_DISCOVERY_SECONDS = 10.0
device_absence_counts = {}
device_read_fail_counts = {}


def _fallback_calibration(serial_key: str, device_label: str = "UNKNOWN") -> Calibration:
    return Calibration(
        device=device_label,
        gas="UNKNOWN",
        slope=1.0,
        offset=0.0,
        cal_min=0.0,
        cal_max=100.0,
        max_flow=100.0,
    )


def _resolve_calibration_or_fallback(serial_key: str, device_label: str = "UNKNOWN") -> tuple[Calibration, bool]:
    try:
        cal = calibration_loader.get(serial=serial_key)
        return cal, True
    except Exception:
        print(
            f"[MFC] No calibration found for serial {serial_key}; using fallback slope=1.0",
            flush=True,
        )
        return _fallback_calibration(serial_key, device_label), False


def _mark_device_calibration(device: dict):
    serial_key = str(device.get("serial", "")).strip()
    _, found = _resolve_calibration_or_fallback(serial_key, str(device.get("name", "UNKNOWN")))
    device["calibrationFound"] = found
    device["calibrationMode"] = "FOUND" if found else "NO_CAL_SLOPE_1"
    device["calibrationSlope"] = 1.0 if not found else None

GAS_CODE_BY_NAME = {
    "AIR": 0x00,
    "NITROGEN": 0x01,
    "METHANE": 0x02,
    "CARBON DIOXIDE": 0x03,
    "PROPANE": 0x04,
    "BUTANE": 0x05,
    "ETHANE": 0x06,
    "HYDROGEN": 0x07,
    "CARBON MONOXIDE": 0x08,
    "ACETYLENE": 0x09,
    "ETHYLENE": 0x0A,
    "PROPYLENE": 0x0B,
    "BUTYLENE": 0x0C,
    "NITROUS OXIDE": 0x0D,
}


def _device_id_to_mfc_index(device_id: str) -> Optional[int]:
    try:
        if not device_id:
            return None
        if device_id.startswith("dev_"):
            idx = int(device_id.split("_")[1]) - 1
            if 0 <= idx < MAX_MFC_DEVICES:
                return idx
            return None
        return None
    except Exception:
        return None


def _mfc_index_to_device_id(mfc_index: int) -> Optional[str]:
    try:
        idx = int(mfc_index)
        if 0 <= idx < MAX_MFC_DEVICES:
            return f"dev_{idx + 1:02d}"
        return None
    except Exception:
        return None


def _gas_name_to_code(gas_name: str) -> Optional[int]:
    if not gas_name:
        return None
    normalized = str(gas_name).strip().upper().replace("_", " ")
    return GAS_CODE_BY_NAME.get(normalized)


def _sync_selected_gases_to_logger(selected_gases: dict):
    """Preserved call site for local-only gas state in the API process."""
    return


async def _delayed_startup_gas_sync(delay_seconds: float = 2.0):
    """Retain startup sequencing for local gas state initialization."""
    await asyncio.sleep(delay_seconds)
    _sync_selected_gases_to_logger(session_state.get("selectedGases", {}))


def _read_mfc_setpoint_raw(device_id: str) -> Optional[int]:
    try:
        device = mfc_devices.get(device_id)
        if not device:
            return None
        inst = get_instrument(device["address"])
        with serial_bus_lock(timeout=SERIAL_LOCK_TIMEOUT_SECONDS):
            value = inst.readParameter(9)
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _csv_log_mfc_id(device: dict, device_id: str) -> str:
    serial = str(device.get("serial", "")).strip()
    calibration_mode = str(device.get("calibrationMode", "")).strip().upper()
    calibration_found = bool(device.get("calibrationFound", False))

    if calibration_mode != "FOUND" or not calibration_found:
        return serial or str(device_id)

    name_value = str(device.get("name", "")).strip()
    if name_value.startswith("MFC-"):
        short_code = name_value[4:].strip()
        if short_code:
            return short_code

    return serial or str(device_id)


def _build_logging_rows() -> list[dict]:
    rows = []
    selected_gases = session_state.get("selectedGases", {}) if isinstance(session_state, dict) else {}

    for device_id in list(mfc_devices.keys()):
        status = read_mfc_status(device_id)
        device = mfc_devices.get(device_id, {})
        setpoint_raw = _read_mfc_setpoint_raw(device_id)
        gas_name = selected_gases.get(device_id, "UNKNOWN")
        log_mfc_id = _csv_log_mfc_id(device, device_id)

        rows.append({
            "id": log_mfc_id,
            "name": device.get("name"),
            "serial": device.get("serial"),
            "address": device.get("address"),
            "gas": gas_name,
            "setpoint": device.get("lastSetpoint"),
            "flow": status.get("flow", device.get("lastFlow")),
            "setpoint_raw": setpoint_raw,
            "flow_raw": status.get("flowRaw"),
            "calibration_status": device.get("calibrationMode", "FOUND"),
        })

    return rows


def log_status_snapshot():
    rows = _build_logging_rows()
    timestamp_utc, timestamp_local, gps_coords = resolve_csv_timestamps(datetime.now().isoformat())
    append_status_rows_to_csv(timestamp_utc, timestamp_local, rows, gps_coords)


async def logging_loop():
    while True:
        try:
            if mfc_devices:
                log_status_snapshot()
            await asyncio.sleep(LOG_INTERVAL_SECONDS)
        except Exception as e:
            print(f"[logging-loop] Error: {e}")
            await asyncio.sleep(LOG_INTERVAL_SECONDS)


def _check_gps_fix() -> bool:
    """Return True if the GPS module has an active position fix."""
    try:
        import pynmea2 as _pynmea2
        gps_ser = serial.Serial('/dev/serial0', 9600, timeout=0.3)
        deadline = time.time() + 1.5
        result = False
        while time.time() < deadline:
            try:
                line = gps_ser.readline().decode('ascii', errors='replace').strip()
            except Exception:
                break
            if line.startswith(('$GPRMC', '$GNRMC')):
                try:
                    msg = _pynmea2.parse(line)
                    if getattr(msg, 'status', '') == 'A':
                        result = True
                        break
                except Exception:
                    pass
        try:
            gps_ser.close()
        except Exception:
            pass
        return result
    except Exception:
        return False


def normalize_selected_gases(raw) -> dict:
    """Normalize selected gases payload to {deviceId: gas} map."""
    if isinstance(raw, dict):
        return {str(k): v for k, v in raw.items() if v}

    if isinstance(raw, list):
        normalized = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            device_id = item.get("deviceId")
            gas = item.get("gas")
            if device_id and gas:
                normalized[str(device_id)] = gas
        return normalized

    return {}


def build_nodes_payload() -> list:
    """Build nodes payload in the format expected by the frontend."""
    return [
        {
            "id": "node_01",
            "name": "MFC-1",
            "status": "online",
            "type": "Gas Meter",
            "devices": list(mfc_devices.values()),
        }
    ]


def build_metrics_payload() -> dict:
    """Build metrics payload for all known devices."""
    payload = {}
    for device_id, device in mfc_devices.items():
        payload[device_id] = {
            "device_id": device_id,
            "name": device.get("name"),
            "serial": device.get("serial"),
            "flow": device.get("lastFlow", 0),
            "setpoint": device.get("lastSetpoint", 0),
            "status": device.get("status", "offline"),
            "calibrationFound": device.get("calibrationFound", True),
            "calibrationMode": device.get("calibrationMode", "FOUND"),
            "timestamp": datetime.now().isoformat(),
        }
    return payload


async def emit_state_sync(to_sid: Optional[str] = None):
    """Emit unified state snapshot to all clients or a single client."""
    payload = {
        "nodes": build_nodes_payload(),
        "metrics": build_metrics_payload(),
        "session": session_state,
        "timestamp": datetime.now().isoformat(),
    }
    await sio.emit("state-sync", payload, to=to_sid, skip_sid=[])



def load_session_state():
    """Load session state from file"""
    global session_state
    try:
        if SESSION_STATE_FILE.exists():
            with open(SESSION_STATE_FILE, 'r') as f:
                data = json.load(f)
                session_state.update(data)
                session_state["selectedGases"] = normalize_selected_gases(
                    session_state.get("selectedGases", {}),
                )
                _sync_selected_gases_to_logger(session_state.get("selectedGases", {}))
    except Exception as e:
        print(f"[session-state] Failed to load: {e}")


def save_session_state():
    """Save session state to file"""
    try:
        session_state["updatedAt"] = datetime.now().isoformat()
        with open(SESSION_STATE_FILE, 'w') as f:
            json.dump(session_state, f, indent=2)
    except Exception as e:
        print(f"[session-state] Failed to save: {e}")


def load_mfc_name_map_from_calibration(cal_file: Path) -> dict[str, str]:
    """Build serial -> short MFC code map from calibration file first column.

    Example MFC column value: "BK-20N2O-M24200697A"
    We extract:
      short code = "BK"
      serial     = "M24200697A"
    """
    name_map: dict[str, str] = {}

    try:
        with open(cal_file, newline="") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                mfc_col = str(row.get("MFC", "")).strip()
                if not mfc_col:
                    continue

                parts = mfc_col.split("-")
                if len(parts) < 2:
                    continue

                short_code = parts[0].strip().upper()
                serial_key = parts[-1].split("\x00")[0].strip()

                if not serial_key or not short_code:
                    continue

                # Keep first mapping for deterministic naming.
                name_map.setdefault(serial_key, short_code)
    except Exception as e:
        print(f"[MFC] Failed to load calibration name map: {e}")

    return name_map


def _normalize_bus_nodes(raw_nodes) -> list[dict]:
    """Deduplicate and stabilize raw bus node discovery results.

    ProPar discovery can occasionally return duplicate entries for the same
    physical device during transient bus noise. We collapse duplicates by
    serial/address and sort by address so device IDs remain stable.
    """
    normalized: list[dict] = []
    seen_keys = set()

    for node in raw_nodes or []:
        if not isinstance(node, dict):
            continue

        address = node.get("address")
        serial_num = str(node.get("serial", "")).split("\x00")[0].strip()
        dedupe_key = serial_num or f"addr:{address}"

        if dedupe_key in seen_keys:
            print(
                f"[MFC] Ignoring duplicate bus node: address={address}, serial={serial_num or 'UNKNOWN'}",
                flush=True,
            )
            continue

        seen_keys.add(dedupe_key)
        normalized.append({
            **node,
            "serial": serial_num,
        })

    normalized.sort(key=lambda node: (
        int(node.get("address", 10**9)) if str(node.get("address", "")).isdigit() else 10**9,
        str(node.get("serial", "")),
    ))
    return normalized


def _scan_bus_nodes() -> list[dict]:
    """Run several discovery scans and merge unique results.

    A single `get_nodes()` call is not reliable on this bus. Different scans can
    surface different subsets of the attached controllers, so we merge several
    attempts into one stable inventory snapshot.
    """
    bus = get_bus()
    merged_by_key: dict[str, dict] = {}
    best_scan: list[dict] = []

    for attempt in range(DISCOVERY_SCAN_ATTEMPTS):
        try:
            with serial_bus_lock(timeout=SERIAL_LOCK_TIMEOUT_DISCOVERY_SECONDS):
                nodes = _normalize_bus_nodes(bus.master.get_nodes() or [])
        except Exception as e:
            print(f"[MFC] Discovery scan {attempt + 1}/{DISCOVERY_SCAN_ATTEMPTS} failed: {e}")
            nodes = []

        if len(nodes) > len(best_scan):
            best_scan = list(nodes)

        for node in nodes:
            serial_key = str(node.get("serial", "")).strip()
            address = node.get("address")
            dedupe_key = serial_key or f"addr:{address}"
            merged_by_key.setdefault(dedupe_key, node)

        if len(merged_by_key) >= MAX_MFC_DEVICES:
            break

        if attempt < DISCOVERY_SCAN_ATTEMPTS - 1:
            time.sleep(DISCOVERY_SCAN_PAUSE_SECONDS)

    merged_nodes = list(merged_by_key.values()) if merged_by_key else best_scan
    merged_nodes = _normalize_bus_nodes(merged_nodes)

    if len(merged_nodes) > len(best_scan):
        print(
            f"[MFC] Discovery merged {len(merged_nodes)} unique nodes across {DISCOVERY_SCAN_ATTEMPTS} scans",
            flush=True,
        )

    return merged_nodes



def discover_mfc_devices():
    """Discover connected MFC devices"""
    global mfc_devices
    try:
        print("[MFC] Starting device discovery")
        
        nodes = _scan_bus_nodes()
        
        if not nodes:
            print("[MFC] No MFC nodes found")
            return {}
        
        name_map = load_mfc_name_map_from_calibration(CAL_FILE)
        devices = {}
        if len(nodes) > MAX_MFC_DEVICES:
            print(
                f"[MFC] Found {len(nodes)} nodes; limiting to first {MAX_MFC_DEVICES}",
                flush=True,
            )

        for i, node in enumerate(nodes[:MAX_MFC_DEVICES]):
            address = node["address"]
            serial_key = str(node["serial"]).strip()
            
            device_id = f"dev_{i + 1:02d}"
            short_code = name_map.get(serial_key)

            if short_code:
                mfc_name = f"MFC-{short_code}"
            else:
                # Fallback when serial has no calibration row.
                mfc_name = f"MFC-{chr(65 + i)}"
                print(
                    f"[MFC] No calibration short name for serial {serial_key}, "
                    f"using fallback name {mfc_name}"
                )
            
            devices[device_id] = {
                "id": device_id,
                "name": mfc_name,
                "address": address,
                "serial": serial_key,
                "status": "online",
                "lastFlow": 0.0,
                "lastSetpoint": 0.0,
            }
            _mark_device_calibration(devices[device_id])
            
            print(f"[MFC] Discovered: {mfc_name} (address={address}, serial={serial_key})")
        
        return devices
        
    except Exception as e:
        print(f"[MFC] Discovery failed: {e}")
        return {}


def sync_devices_from_bus() -> dict:
    """Refresh device serial/name metadata from live bus nodes.

    This keeps names in sync with the connected MFC serials by re-checking the
    calibration file mapping each time refresh is requested.
    """
    global mfc_devices, device_absence_counts

    summary = {
        "changed": False,
        "added": [],
        "removed": [],
        "updated": [],
    }

    try:
        nodes = _scan_bus_nodes()
        name_map = load_mfc_name_map_from_calibration(CAL_FILE)

        latest_ids = set()

        if len(nodes) > MAX_MFC_DEVICES:
            print(
                f"[MFC] Sync found {len(nodes)} nodes; limiting to first {MAX_MFC_DEVICES}",
                flush=True,
            )

        for i, node in enumerate(nodes[:MAX_MFC_DEVICES]):
            device_id = f"dev_{i + 1:02d}"
            latest_ids.add(device_id)
            device_absence_counts[device_id] = 0

            address = node["address"]
            serial_key = str(node["serial"]).strip()

            short_code = name_map.get(serial_key)
            if short_code:
                resolved_name = f"MFC-{short_code}"
            else:
                resolved_name = f"MFC-{chr(65 + i)}"

            existing = mfc_devices.get(device_id)
            if not existing:
                mfc_devices[device_id] = {
                    "id": device_id,
                    "name": resolved_name,
                    "address": address,
                    "serial": serial_key,
                    "status": "online",
                    "lastFlow": 0.0,
                    "lastSetpoint": 0.0,
                }
                _mark_device_calibration(mfc_devices[device_id])
                device_absence_counts[device_id] = 0
                summary["changed"] = True
                summary["added"].append(device_id)
                print(
                    f"[MFC] Added {device_id}: serial={serial_key}, name={resolved_name}"
                )
                continue

            old_serial = str(existing.get("serial", "")).strip()
            old_name = str(existing.get("name", "")).strip()
            old_address = existing.get("address")

            existing["address"] = address
            existing["serial"] = serial_key
            existing["name"] = resolved_name
            _mark_device_calibration(existing)

            if old_serial != serial_key or old_name != resolved_name or old_address != address:
                summary["changed"] = True
                summary["updated"].append(device_id)
                print(
                    f"[MFC] Updated {device_id}: "
                    f"serial {old_serial} -> {serial_key}, "
                    f"name {old_name} -> {resolved_name}, "
                    f"address {old_address} -> {address}"
                )

        # Remove stale devices only after repeated misses to avoid churn from
        # transient serial/bus glitches.
        for device_id in list(mfc_devices.keys()):
            if device_id not in latest_ids:
                miss_count = int(device_absence_counts.get(device_id, 0)) + 1
                device_absence_counts[device_id] = miss_count
                if miss_count >= DEVICE_STALE_MISS_THRESHOLD:
                    del mfc_devices[device_id]
                    device_absence_counts.pop(device_id, None)
                    summary["changed"] = True
                    summary["removed"].append(device_id)
                    print(
                        f"[MFC] Removed stale device after {miss_count} misses: {device_id}"
                    )
                else:
                    print(
                        f"[MFC] Keeping {device_id}; missing from bus ({miss_count}/{DEVICE_STALE_MISS_THRESHOLD})"
                    )

        # Drop counters for device IDs that are no longer tracked.
        for device_id in list(device_absence_counts.keys()):
            if device_id not in mfc_devices:
                device_absence_counts.pop(device_id, None)

        return summary

    except Exception as e:
        print(f"[MFC] Device sync failed: {e}")
        return summary


def read_mfc_status(device_id: str):
    """Read current status from an MFC device using ProPar"""
    try:
        if device_id not in mfc_devices:
            raise ValueError(f"Unknown device: {device_id}")
        
        device = mfc_devices[device_id]
        address = device["address"]
        serial_key = device["serial"]
        
        cal, cal_found = _resolve_calibration_or_fallback(serial_key, str(device.get("name", "UNKNOWN")))
        device["calibrationFound"] = cal_found
        device["calibrationMode"] = "FOUND" if cal_found else "NO_CAL_SLOPE_1"
        device["calibrationSlope"] = 1.0 if not cal_found else None
        cal_slope = float(cal.slope)
        cal_offset = float(cal.offset)
        
        # Get instrument from propar with retries to tolerate transient bus noise.
        try:
            inst = get_instrument(address)
            last_error = None
            for _ in range(3):
                try:
                    with serial_bus_lock(timeout=SERIAL_LOCK_TIMEOUT_SECONDS):
                        flow_raw = inst.readParameter(8)  # Returns 0-32000
                    if flow_raw is None:
                        raise ValueError("readParameter(8) returned None")

                    raw_percent = float(flow_raw) * 100.0 / 32000.0
                    flow = cal_slope * raw_percent + cal_offset

                    device_read_fail_counts[device_id] = 0
                    device["lastFlow"] = round(flow, 4)
                    device["lastValue"] = flow_raw
                    device["status"] = "online"

                    return {
                        "flow": round(flow, 4),
                        "flowRaw": int(flow_raw),
                        "serial": serial_key,
                        "calibrationFound": cal_found,
                        "calibrationMode": ("FOUND" if cal_found else "NO_CAL_SLOPE_1"),
                        "status": "online",
                        "timestamp": datetime.now().isoformat()
                    }
                except Exception as e:
                    last_error = e

            print(f"[MFC] ProPar read error for {device_id}: {last_error}")
            fail_count = int(device_read_fail_counts.get(device_id, 0)) + 1
            device_read_fail_counts[device_id] = fail_count

            if fail_count >= 3:
                device["status"] = "offline"

            return {
                "flow": device.get("lastFlow", 0.0),
                "flowRaw": int(device.get("lastValue", 0) or 0),
                "serial": serial_key,
                "calibrationFound": cal_found,
                "calibrationMode": ("FOUND" if cal_found else "NO_CAL_SLOPE_1"),
                "status": device.get("status", "offline"),
                "timestamp": datetime.now().isoformat(),
                "error": str(last_error),
            }
        except Exception as e:
            print(f"[MFC] ProPar read error for {device_id}: {e}")
            device["status"] = "offline"
            return {
                "flow": device.get("lastFlow", 0.0),
                "flowRaw": int(device.get("lastValue", 0) or 0),
                "serial": serial_key,
                "calibrationFound": cal_found,
                "calibrationMode": ("FOUND" if cal_found else "NO_CAL_SLOPE_1"),
                "status": "offline",
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
            }
        
    except Exception as e:
        print(f"[MFC] Status read failed for {device_id}: {e}")
        if device_id in mfc_devices:
            mfc_devices[device_id]["status"] = "offline"
        return {"status": "offline", "error": str(e)}


def set_mfc_setpoint(device_id: str, value_ln_min: float):
    """Set setpoint for an MFC device using ProPar"""
    try:
        if device_id not in mfc_devices:
            raise ValueError(f"Unknown device: {device_id}")
        
        device = mfc_devices[device_id]
        address = device["address"]
        serial_key = device["serial"]
        
        cal, cal_found = _resolve_calibration_or_fallback(serial_key, str(device.get("name", "UNKNOWN")))
        device["calibrationFound"] = cal_found
        device["calibrationMode"] = "FOUND" if cal_found else "NO_CAL_SLOPE_1"
        device["calibrationSlope"] = 1.0 if not cal_found else None
        cal_min = float(cal.cal_min)
        cal_max = float(cal.cal_max)
        cal_slope = float(cal.slope)
        cal_offset = float(cal.offset)
        
        # Clamp to calibration range
        desired_flow = max(0.0, min(cal_max, value_ln_min))
        
        if desired_flow <= 0:
            register = 0
        else:
            raw_percent = (desired_flow - cal_offset) / cal_slope
            register = int(raw_percent * 32000 / 100)
        
        if not (0 <= register <= 32000):
            raise ValueError(f"Setpoint {desired_flow} exceeds device limits (register={register})")
        
        try:
            led_ctrl.set_state(LEDController.STATE_UPDATING)
            inst = get_instrument(address)
            with serial_bus_lock(timeout=SERIAL_LOCK_TIMEOUT_SECONDS):
                inst.writeParameter(9, register)
            print(f"[MFC] Set {device_id} to register={register} ({desired_flow:.4f} LN/min)")
            
            time.sleep(0.5)
            setpoint_raw = None
            for _ in range(3):
                try:
                    with serial_bus_lock(timeout=SERIAL_LOCK_TIMEOUT_SECONDS):
                        setpoint_raw = inst.readParameter(9)
                    if setpoint_raw is not None:
                        break
                except Exception:
                    pass
                time.sleep(0.2)

            if setpoint_raw is None:
        
                applied_flow = float(desired_flow)
                register_out = int(register)
            elif int(setpoint_raw) <= 0:
                applied_flow = 0.0
                register_out = int(setpoint_raw)
            else:
                applied_raw_percent = float(setpoint_raw) * 100.0 / 32000.0
                applied_flow = cal_slope * applied_raw_percent + cal_offset
                register_out = int(setpoint_raw)
            
            device["lastSetpoint"] = round(applied_flow, 4)
            led_ctrl.set_state(LEDController.STATE_OK)
            return {
                "requested": value_ln_min,
                "applied": round(applied_flow, 4),
                "setpoint": round(applied_flow, 4),
                "register": register_out,
                "serial": serial_key,
                "calibrationFound": cal_found,
                "calibrationMode": ("FOUND" if cal_found else "NO_CAL_SLOPE_1"),
                "status": "success"
            }
        except Exception as e:
            print(f"[MFC] ProPar write error for {device_id}: {e}")
            led_ctrl.set_state(LEDController.STATE_OK)
            return {"status": "error", "error": str(e)}
        
    except Exception as e:
        print(f"[MFC] Setpoint failed for {device_id}: {e}")
        return {"status": "error", "error": str(e)}


# ==================== Background Status Updates ====================

async def update_status_loop():
    """Periodically update device status and emit via WebSocket"""
    while True:
        try:
            if mfc_devices:
                led_ctrl.set_state(LEDController.STATE_UPDATING)
            else:
                discovered = discover_mfc_devices()
                if discovered:
                    mfc_devices.clear()
                    mfc_devices.update(discovered)
                    print(f"[status-loop] Discovered {len(mfc_devices)} MFC(s) after retry")
                    await emit_state_sync()
                else:
                    led_ctrl.set_state(LEDController.STATE_ERROR)
                    await asyncio.sleep(DISCOVERY_RETRY_SECONDS)
                    continue

            any_online = False
            for device_id in list(mfc_devices.keys()):
                status = read_mfc_status(device_id)
                device = mfc_devices.get(device_id, {})
                if status.get("status") == "online":
                    any_online = True
                mfc_id = _device_id_to_mfc_index(device_id)

                await sio.emit("device_status", {
                    "device_id": device_id,
                    "data": status
                }, skip_sid=[])  

                await sio.emit("uplink", {
                    "type": "status",
                    "deviceId": device_id,
                    "mfcId": mfc_id,
                    "device": str(device.get("name", "")).replace("MFC-", ""),
                    "serial": device.get("serial"),
                    "calibrationFound": device.get("calibrationFound", True),
                    "calibrationMode": device.get("calibrationMode", "FOUND"),
                    "flow": status.get("flow", device.get("lastFlow", 0)),
                    "setpoint": device.get("lastSetpoint", 0),
                    "timestamp": status.get("timestamp", datetime.now().isoformat()),
                }, skip_sid=[])

          
            sync_summary = sync_devices_from_bus()
            if sync_summary.get("changed"):
                await emit_state_sync()

            if not any_online:
                # Communication looks down for all known devices; retry bus sync fast.
                led_ctrl.set_state(LEDController.STATE_ERROR)
                await asyncio.sleep(DISCOVERY_RETRY_SECONDS)
                continue

            # Determine LED state based on MFC and GPS health.
            if not mfc_devices:
                led_ctrl.set_state(LEDController.STATE_ERROR)
            elif not _check_gps_fix():
                led_ctrl.set_state(LEDController.STATE_GPS_SEARCHING)
            else:
                led_ctrl.set_state(LEDController.STATE_OK)

            await asyncio.sleep(STATUS_UPDATE_INTERVAL_SECONDS)
        except Exception as e:
            print(f"[status-loop] Error: {e}")
            led_ctrl.set_state(LEDController.STATE_ERROR)
            await asyncio.sleep(STATUS_UPDATE_INTERVAL_SECONDS)


def start_status_loop():
    """Start the status update loop in background"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(update_status_loop())


def start_logging_loop():
    """Start CSV logging in-process so the API is the only serial-bus owner."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(logging_loop())


async def emit_flow_after_setpoint(device_id: str, mfc_id: int, delay_s: float = 3.0):
    """Wait `delay_s` seconds then read actual flow and push to all clients."""
    await asyncio.sleep(delay_s)
    try:
        status = read_mfc_status(device_id)
        device = mfc_devices.get(device_id, {})
        device_code = str(device.get("name", "")).replace("MFC-", "")
        await sio.emit("device_status", {
            "device_id": device_id,
            "data": status,
        }, skip_sid=[])
        await sio.emit("uplink", {
            "type": "status",
            "deviceId": device_id,
            "mfcId": mfc_id,
            "device": device_code,
            "serial": device.get("serial"),
            "calibrationFound": device.get("calibrationFound", True),
            "calibrationMode": device.get("calibrationMode", "FOUND"),
            "flow": status.get("flow", device.get("lastFlow", 0)),
            "setpoint": device.get("lastSetpoint", 0),
            "timestamp": status.get("timestamp", datetime.now().isoformat()),
        }, skip_sid=[])
        print(f"[MFC] Post-setpoint flow readback {device_id}: {status.get('flow')} LN/min")
    except Exception as e:
        print(f"[MFC] Post-setpoint readback failed for {device_id}: {e}")


def _resolve_device_id_for_gas_lookup(device_name: str) -> Optional[str]:
    lookup = str(device_name).strip().upper()
    if not lookup:
        return None

    alias_to_device_id = {}
    for dev_id, dev_data in mfc_devices.items():
        normalized_dev_id = str(dev_id).upper()
        normalized_name = str(dev_data.get("name", "")).strip().upper()
        name_suffix = normalized_name.replace("MFC-", "") if normalized_name else ""

        candidates = {normalized_dev_id}
        if normalized_name:
            candidates.add(normalized_name)
        if name_suffix:
            candidates.add(name_suffix)

        mfc_idx = _device_id_to_mfc_index(str(dev_id))
        if mfc_idx is not None:
            # Support A/B/C... shorthand aliases.
            candidates.add(chr(65 + mfc_idx))

        for candidate in candidates:
            alias_to_device_id.setdefault(candidate, dev_id)

    if lookup in alias_to_device_id:
        return alias_to_device_id[lookup]

    for alias, dev_id in alias_to_device_id.items():
        if lookup in alias:
            return dev_id

    return None


async def _setpoint_for_device_id(device_id: str, value: float):
    if device_id not in mfc_devices:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")

    mfc_id = _device_id_to_mfc_index(device_id)
    if mfc_id is None:
        raise HTTPException(status_code=400, detail=f"Invalid device ID {device_id}")

    result = set_mfc_setpoint(device_id, value)
    await sio.emit("setpoint_updated", {"device_id": device_id, "value": value}, skip_sid=[])
    await sio.emit("uplink", {
        "type": "status",
        "deviceId": device_id,
        "mfcId": mfc_id,
        "device": str(mfc_devices.get(device_id, {}).get("name", f"MFC-{mfc_id + 1}")).replace("MFC-", ""),
        "flow": mfc_devices.get(device_id, {}).get("lastFlow", 0),
        "setpoint": mfc_devices.get(device_id, {}).get("lastSetpoint", value),
        "timestamp": datetime.now().isoformat(),
    }, skip_sid=[])
    await emit_state_sync()
    asyncio.create_task(emit_flow_after_setpoint(device_id, mfc_id))
    return result


# ==================== REST API Endpoints ====================

@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    global mfc_devices, calibration_loader, status_update_task, logging_task
    
    # Load calibrations
    try:
        calibration_loader = CalibrationLoader(str(CAL_FILE))
        print("[API] Calibration loader initialized")
    except Exception as e:
        print(f"[API] Failed to load calibrations: {e}")
    
    # Discover devices
    mfc_devices = discover_mfc_devices()

    # Set initial LED state based on discovery result.
    if mfc_devices:
        led_ctrl.set_state(LEDController.STATE_OK)
    else:
        led_ctrl.set_state(LEDController.STATE_ERROR)
    
    # Load session state
    load_session_state()
    asyncio.create_task(_delayed_startup_gas_sync())
    
    # Start status update loop even with no initial devices, so hot-plugged
    # MFCs are discovered automatically.
    status_update_task = threading.Thread(
        target=start_status_loop,
        daemon=True
    )
    status_update_task.start()
    print("[API] Status update loop started")

    logging_task = threading.Thread(
        target=start_logging_loop,
        daemon=True
    )
    logging_task.start()
    print("[API] CSV logging loop started")
    
    print("[API] Server started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global ser
    led_ctrl.stop()
    close_all()
    if ser:
        try:
            ser.close()
        except:
            pass
    print("[API] Server shutdown")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "devices": list(mfc_devices.keys()),
        "timestamp": datetime.now().isoformat()
    }


@app.get("/")
async def root():
    """Simple root endpoint for frontend reachability checks."""
    return {
        "status": "ok",
        "service": "mfc-control-api",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/nodes")
async def get_nodes():
    """Get all nodes and devices (matches original API)"""
    return build_nodes_payload()


@app.post("/start-session")
async def start_session(body: dict):
    """Start a measurement session"""
    session_state["sessionActive"] = True
    session_state["selectedGases"] = normalize_selected_gases(body.get("selections", {}))
    save_session_state()
    _sync_selected_gases_to_logger(session_state.get("selectedGases", {}))
    
    await sio.emit("session_started", session_state, skip_sid=[])
    await emit_state_sync()
    return {"status": "success", "data": session_state}


@app.get("/session/state")
async def get_session_state():
    """Get current session state"""
    return session_state


@app.post("/session/state")
async def update_session_state(body: dict):
    """Update session state"""
    global session_state
    incoming = dict(body or {})
    if "selectedGases" in incoming:
        incoming["selectedGases"] = normalize_selected_gases(incoming.get("selectedGases"))
    session_state.update(incoming)
    save_session_state()
    if "selectedGases" in incoming:
        _sync_selected_gases_to_logger(session_state.get("selectedGases", {}))
    
    await sio.emit("session_updated", session_state, skip_sid=[])
    await emit_state_sync()
    return session_state


@app.post("/session/state/selected-gas")
async def set_selected_gas(body: dict):
    """Set selected gas for a device"""
    device_id = body.get("deviceId")
    gas = body.get("gas")
    
    if not device_id or not gas:
        raise HTTPException(status_code=400, detail="Missing deviceId or gas")
    
    session_state["selectedGases"][device_id] = gas
    save_session_state()
    _sync_selected_gases_to_logger(session_state.get("selectedGases", {}))
    
    await sio.emit("gas_selected", {
        "deviceId": device_id,
        "gas": gas
    }, skip_sid=[])
    await emit_state_sync()
    
    return {"status": "success"}


@app.get("/device/{device_id}/metrics")
async def get_device_metrics(device_id: str):
    """Get metrics for a device"""
    if device_id not in mfc_devices:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")
    
    status = read_mfc_status(device_id)
    device = mfc_devices[device_id]
    
    return {
        "device_id": device_id,
        "name": device["name"],
        "flow": device["lastFlow"],
        "setpoint": device["lastSetpoint"],
        "raw_value": device.get("lastValue", 0),
        "status": device["status"],
        "timestamp": datetime.now().isoformat()
    }


@app.get("/device/{device_name}/fetch-gas")
async def fetch_device_gases(device_name: str):
    """Fetch available gases for a device based on its serial number"""
    try:
        # Find device by ID, full name, short name, or A/B/C... alias.
        device_id = _resolve_device_id_for_gas_lookup(device_name)
        
        if not device_id:
            raise HTTPException(status_code=404, detail=f"Device {device_name} not found")
        
        device = mfc_devices[device_id]
        serial_key = device["serial"]
        
        # Get gases for this serial using correct method name
        gases = calibration_loader.available_gases(serial_key)
        
        return {
            "device": device_name,
            "serial": serial_key,
            "gases": gases
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[fetch-gas] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/device/{device_id}/logs")
async def get_device_logs(device_id: str):
    """Get logs for a device (placeholder)"""
    if device_id not in mfc_devices:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")
    
    return {
        "device_id": device_id,
        "logs": []  # Implement log persistence as needed
    }


@app.post("/setpoint-{mfc_id}")
async def set_setpoint_by_mfc_id(mfc_id: int, body: dict):
    """Set setpoint by MFC index, e.g. /setpoint-0 ... /setpoint-5."""
    value = body.get("value")
    if value is None:
        raise HTTPException(status_code=400, detail="Missing value")

    try:
        numeric_value = float(value)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid value {value}")

    device_id = _mfc_index_to_device_id(mfc_id)
    if device_id is None:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid MFC ID {mfc_id}. Supported range: 0-{MAX_MFC_DEVICES - 1}",
        )

    return await _setpoint_for_device_id(device_id, numeric_value)


@app.post("/send-command-{mfc_id}")
async def send_command_by_mfc_id(mfc_id: int, body: dict):
    """Send command by MFC index, e.g. /send-command-0 ... /send-command-5."""
    device_id = _mfc_index_to_device_id(mfc_id)
    if device_id is None:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid MFC ID {mfc_id}. Supported range: 0-{MAX_MFC_DEVICES - 1}",
        )

    return {
        "status": "success",
        "device": device_id,
        "mfcId": mfc_id,
        "command": body.get("command"),
    }


@app.post("/refresh")
async def refresh_data():
    """Refresh all device data"""
    sync_summary = sync_devices_from_bus()
    updated_devices = {}
    for device_id in mfc_devices.keys():
        status = read_mfc_status(device_id)
        device = mfc_devices.get(device_id, {})
        updated_devices[device_id] = {
            **status,
            "name": device.get("name"),
            "serial": device.get("serial"),
            "address": device.get("address"),
        }
    
    payload = {
        "status": "success",
        "sync": sync_summary,
        "devices": updated_devices,
        "timestamp": datetime.now().isoformat()
    }

    await sio.emit("data_refreshed", payload, skip_sid=[])
    await emit_state_sync()

    return payload


@app.post("/reset")
async def reset_session(body: dict = None):
    """Reset session and optionally specific MFC"""
    if body and body.get("mfc"):
        # Reset specific device
        device_id = body["mfc"]
        if device_id in mfc_devices:
            set_mfc_setpoint(device_id, 0.0)
    else:
        # Reset all devices
        for device_id in mfc_devices.keys():
            set_mfc_setpoint(device_id, 0.0)
    
    session_state["sessionActive"] = False
    save_session_state()
    
    await sio.emit("session_reset", {}, skip_sid=[])
    await emit_state_sync()
    return {"status": "success"}


# ==================== WebSocket Events ====================

@sio.event
async def connect(sid, environ):
    """Handle client connection"""
    print(f"[WebSocket] Client connected: {sid}")
    connected_clients.add(sid)
    
    # Send current state to new client
    await sio.emit("initial", {
        "session": session_state,
        "devices": mfc_devices
    }, to=sid)
    await emit_state_sync(to_sid=sid)


@sio.event
async def disconnect(sid):
    """Handle client disconnection"""
    print(f"[WebSocket] Client disconnected: {sid}")
    connected_clients.discard(sid)


@sio.event
async def request_refresh(sid):
    """Handle manual refresh request from client"""
    sync_summary = sync_devices_from_bus()
    updated_devices = {}
    for device_id in mfc_devices.keys():
        status = read_mfc_status(device_id)
        device = mfc_devices.get(device_id, {})
        updated_devices[device_id] = {
            **status,
            "name": device.get("name"),
            "serial": device.get("serial"),
            "address": device.get("address"),
        }
    
    await sio.emit("data_refreshed", {
        "sync": sync_summary,
        "devices": updated_devices,
        "timestamp": datetime.now().isoformat()
    }, skip_sid=[])


@sio.event
async def set_setpoint(sid, data):
    """Handle setpoint request from client"""
    device_id = data.get("deviceId")
    value = data.get("value")
    
    result = set_mfc_setpoint(device_id, value)
    
    await sio.emit("setpoint_response", {
        "device_id": device_id,
        "data": result
    }, skip_sid=[])


# ==================== Mount Socket.IO ====================

# Wrap FastAPI app with Socket.IO
asgi_app = ASGIApp(
    sio,
    app
)


# ==================== Main ====================

if __name__ == "__main__":
    print("[API] Starting MFC-Control API Server...")
    print(f"[API] Listening on http://localhost:{PORT}")
    
    uvicorn.run(
        asgi_app,
        host="0.0.0.0",
        port=PORT,
        log_level="info"
    )
