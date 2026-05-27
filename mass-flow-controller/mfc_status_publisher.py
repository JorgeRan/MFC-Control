import time
import sys
import json
import os
import csv
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from calibration_loader import CalibrationLoader, Calibration
import gps
from shared_resources import get_serial, get_bus, get_instrument, serial_bus_lock
from socket_commands import SocketServer
from timezonefinder import TimezoneFinder

PORT = '/dev/ttyUSB0'
BAUD = 38400
TIMEOUT = 1
MFC_CAL_DEBUG = os.getenv("MFC_CAL_DEBUG", "0") == "1"
LOG_INTERVAL_SECONDS = 1.0
SOCKET_POLL_SLEEP_SECONDS = 0.05
SERIAL_LOCK_TIMEOUT_SECONDS = 8.0
SERIAL_LOCK_TIMEOUT_DISCOVERY_SECONDS = 10.0
SERIAL_LOCK_TIMEOUT_STATUS_SECONDS = 0.6
NODE_DISCOVERY_INTERVAL_SECONDS = 15.0
NODE_DISCOVERY_INTERVAL_WHEN_EMPTY_SECONDS = 1.0
CSV_LOG_PATH = os.getenv(
    "MFC_STATUS_CSV",
    "/home/mfc/data/mfc_status_log.csv",
)
MFC_STATUS_PER_RUN_FILE = os.getenv("MFC_STATUS_PER_RUN_FILE", "1") == "1"
CALIBRATION_FILE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "MFCCalibrations-ReadDirectlyByFlareCode.txt",
)


def build_run_log_file(base_path: str) -> str:
    startup_stamp = time.strftime("%d-%m-%Y_%H-%M-%S", time.localtime())
    directory = os.path.dirname(base_path) or "."
    filename = os.path.basename(base_path)
    stem, ext = os.path.splitext(filename)
    if not ext:
        ext = ".csv"
    return os.path.join(directory, f"{stem}_{startup_stamp}{ext}")


CSV_LOG_FILE = build_run_log_file(CSV_LOG_PATH) if MFC_STATUS_PER_RUN_FILE else CSV_LOG_PATH

GAS_NAME_BY_CODE = {
    0x00: "AIR",
    0x01: "NITROGEN",
    0x02: "METHANE",
    0x03: "CARBON DIOXIDE",
    0x04: "PROPANE",
    0x05: "BUTANE",
    0x06: "ETHANE",
    0x07: "HYDROGEN",
    0x08: "CARBON MONOXIDE",
    0x09: "ACETYLENE",
    0x0A: "ETHYLENE",
    0x0B: "PROPYLENE",
    0x0C: "BUTYLENE",
    0x0D: "NITROUS OXIDE",
}

selected_gas_by_mfc = {}
gps_coordinates_logged = False
calibration_loader = None
last_status_row_by_node = {}
csv_slot_keys = []
last_csv_block_by_slot = {}
CSV_INITIAL_MFC_SLOT_COUNT = 2
CSV_TIMESTAMP_COLUMN_COUNT = 2
CSV_BLOCK_WIDTH = 9
timezone_finder = TimezoneFinder()
latched_timezone_name = None
latched_gps_coords = None
timezone_latched_logged = False


def _other_process_has_cmd_fragment(fragment: str) -> bool:
    current_pid = os.getpid()
    proc_dir = Path("/proc")
    if not proc_dir.exists():
        return False

    for pid_dir in proc_dir.iterdir():
        if not pid_dir.name.isdigit():
            continue
        pid = int(pid_dir.name)
        if pid == current_pid:
            continue
        cmdline_path = pid_dir / "cmdline"
        try:
            raw = cmdline_path.read_bytes()
        except Exception:
            continue
        if not raw:
            continue
        cmdline = raw.replace(b"\x00", b" ").decode(errors="ignore")
        if fragment in cmdline:
            return True
    return False


def get_calibration_loader() -> CalibrationLoader:
    global calibration_loader
    if calibration_loader is None:
        calibration_loader = CalibrationLoader(CALIBRATION_FILE_PATH)
    return calibration_loader


def fallback_calibration(serial_key: str, address) -> Calibration:
    return Calibration(
        device=str(address),
        gas="UNKNOWN",
        slope=1.0,
        offset=0.0,
        cal_min=0.0,
        cal_max=100.0,
        max_flow=100.0,
    )


def resolve_runtime_calibration(loader: CalibrationLoader, serial_num: str, gas_code):
    serial_key = normalize_serial(serial_num)
    if gas_code in GAS_NAME_BY_CODE:
        gas_name = GAS_NAME_BY_CODE[gas_code]
        try:
            cal = loader.get_for_gas(serial_num, gas_name)
            return cal, True, gas_name
        except Exception:
            pass

    try:
        cal = loader.get(serial=serial_num)
        return cal, True, cal.gas
    except Exception:
        return fallback_calibration(serial_key, serial_key), False, "UNKNOWN"


def csv_row_sort_key(row):
    name_key = str(row.get("name", "")).strip().upper()
    id_key = str(row.get("id", "")).strip().upper()
    serial_key = normalize_serial(str(row.get("serial", ""))).strip().upper()
    address_key = str(row.get("address", "")).strip().upper()
    primary = name_key if name_key else id_key
    return (primary, id_key, serial_key, address_key)


def csv_row_slot_key(row):
    return (
        normalize_serial(str(row.get("serial", ""))).strip().upper(),
        str(row.get("address", "")).strip().upper(),
    )


def csv_slot_key_from_columns(row, offset):
    serial = row[offset + 1].strip() if len(row) > offset + 1 else ""
    address = row[offset + 2].strip() if len(row) > offset + 2 else ""
    if not any((serial, address)):
        return None
    return (
        normalize_serial(serial).strip().upper(),
        address.strip().upper(),
    )


def load_last_csv_data_row(csv_path: str):
    if not os.path.exists(csv_path):
        return None

    last_data_row = None
    try:
        with open(csv_path, "r", newline="") as infile:
            reader = csv.reader(infile)
            for row in reader:
                if not row:
                    continue
                first_cell = row[0].strip()
                if first_cell in ("Timestamp UTC", "GPS Coordinates"):
                    continue
                last_data_row = row
    except Exception:
        return None

    return last_data_row


def load_csv_slot_keys(csv_path: str):
    if not os.path.exists(csv_path):
        return []

    last_data_row = None
    try:
        with open(csv_path, "r", newline="") as infile:
            reader = csv.reader(infile)
            for row in reader:
                if not row:
                    continue
                first_cell = row[0].strip()
                if first_cell in ("Timestamp UTC", "GPS Coordinates"):
                    continue
                last_data_row = row
    except Exception:
        return []

    if last_data_row is None:
        return []

    loaded_keys = []
    max_offset = max(CSV_TIMESTAMP_COLUMN_COUNT, len(last_data_row))
    for offset in range(CSV_TIMESTAMP_COLUMN_COUNT, max_offset, CSV_BLOCK_WIDTH):
        slot_key = csv_slot_key_from_columns(last_data_row, offset)
        if slot_key is not None:
            loaded_keys.append(slot_key)
    return loaded_keys


def ensure_csv_slot_capacity(csv_path: str, slot_count: int):
    """Expand an existing CSV file to the requested number of MFC blocks."""
    if not os.path.exists(csv_path):
        return

    target_slot_count = max(CSV_INITIAL_MFC_SLOT_COUNT, int(slot_count or 0))
    target_width = CSV_TIMESTAMP_COLUMN_COUNT + (target_slot_count * CSV_BLOCK_WIDTH)

    with open(csv_path, "r", newline="") as infile:
        rows = list(csv.reader(infile))

    if not rows:
        return

    current_width = max((len(row) for row in rows), default=0)
    if current_width >= target_width:
        return

    mfc_block_header = [
        "MFC Id",
        "Serial",
        "Address",
        "Gas",
        "Setpoint",
        "Flow",
        "Raw Setpoint",
        "Raw Flow",
        "Calibration",
    ]

    rows[0] = ["Timestamp UTC", "Timestamp Local"] + (mfc_block_header * target_slot_count)

    for row_index in range(1, len(rows)):
        padding = target_width - len(rows[row_index])
        if padding > 0:
            rows[row_index].extend([""] * padding)

    with open(csv_path, "w", newline="") as outfile:
        writer = csv.writer(outfile)
        writer.writerows(rows)


def format_csv_timestamp(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def resolve_csv_timestamps(utc_timestamp: str):
    global latched_timezone_name, latched_gps_coords, timezone_latched_logged

    try:
        utc_dt = datetime.fromisoformat(str(utc_timestamp).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        utc_dt = datetime.now(timezone.utc).replace(microsecond=0)

    utc_display = format_csv_timestamp(utc_dt)

    if latched_timezone_name:
        try:
            local_dt = utc_dt.astimezone(ZoneInfo(latched_timezone_name))
            return utc_display, format_csv_timestamp(local_dt), latched_gps_coords
        except Exception:
            # If cached timezone becomes invalid, drop cache and retry GPS lookup.
            latched_timezone_name = None

    coords = gps.get_locked_coordinates(timeout=0.5)
    if not coords:
        return utc_display, "NO GPS", None

    latitude, longitude = coords
    timezone_name = timezone_finder.timezone_at(lng=longitude, lat=latitude)
    if not timezone_name:
        timezone_name = timezone_finder.certain_timezone_at(lng=longitude, lat=latitude)
    if not timezone_name:
        return utc_display, "NO GPS", None

    latched_timezone_name = timezone_name
    latched_gps_coords = coords
    if not timezone_latched_logged:
        print(
            f"INFO: GPS lock acquired, timezone latched: {latched_timezone_name} "
            f"(lat={latitude:.6f}, lon={longitude:.6f})",
            flush=True,
        )
        timezone_latched_logged = True

    try:
        local_dt = utc_dt.astimezone(ZoneInfo(latched_timezone_name))
        return utc_display, format_csv_timestamp(local_dt), latched_gps_coords
    except Exception:
        return utc_display, "NO GPS", coords


def insert_gps_row_after_header(csv_path: str, latitude: float, longitude: float):
    if not os.path.exists(csv_path):
        return

    with open(csv_path, "r", newline="") as infile:
        rows = list(csv.reader(infile))

    if not rows:
        return

    gps_marker = "GPS Coordinates"
    for row in rows[1:]:
        if row and row[0] == gps_marker:
            return

    gps_row = [gps_marker, f"{latitude:.8f}", f"{longitude:.8f}"]
    rows.insert(1, gps_row)

    with open(csv_path, "w", newline="") as outfile:
        writer = csv.writer(outfile)
        writer.writerows(rows)


def append_status_rows_to_csv(timestamp_utc: str, timestamp_local: str, node_rows, gps_coords=None):
    global gps_coordinates_logged, csv_slot_keys, last_csv_block_by_slot

    mfc_block_header = [
        "MFC Id",
        "Serial",
        "Address",
        "Gas",
        "Setpoint",
        "Flow",
        "Raw Setpoint",
        "Raw Flow",
        "Calibration",
    ]

    file_exists = os.path.exists(CSV_LOG_FILE)
    log_dir = os.path.dirname(CSV_LOG_FILE)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    if not file_exists:
        csv_slot_keys = []
        last_csv_block_by_slot = {}
    elif not csv_slot_keys:
        csv_slot_keys = load_csv_slot_keys(CSV_LOG_FILE)

    if file_exists and csv_slot_keys and not last_csv_block_by_slot:
        last_data_row = load_last_csv_data_row(CSV_LOG_FILE)
        if last_data_row:
            for slot_index, slot_key in enumerate(csv_slot_keys):
                offset = CSV_TIMESTAMP_COLUMN_COUNT + (slot_index * CSV_BLOCK_WIDTH)
                padded = list(last_data_row) + [""] * max(0, (offset + CSV_BLOCK_WIDTH) - len(last_data_row))
                block = padded[offset : offset + CSV_BLOCK_WIDTH]
                if any(cell not in (None, "") for cell in block):
                    last_csv_block_by_slot[slot_key] = block

    gps_row = None
    if not gps_coordinates_logged:
        coords = gps_coords
        if coords:
            latitude, longitude = coords
            if file_exists:
                insert_gps_row_after_header(CSV_LOG_FILE, latitude, longitude)
            else:
                gps_row = ["GPS Coordinates", f"{latitude:.8f}", f"{longitude:.8f}"]
            gps_coordinates_logged = True

    if node_rows:
        for row in sorted(node_rows, key=csv_row_sort_key):
            slot_key = csv_row_slot_key(row)
            if slot_key in csv_slot_keys:
                continue
            csv_slot_keys.append(slot_key)

    target_slot_count = max(CSV_INITIAL_MFC_SLOT_COUNT, len(csv_slot_keys))

    if not file_exists:
        with open(CSV_LOG_FILE, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                "Timestamp UTC",
                "Timestamp Local",
            ] + mfc_block_header + mfc_block_header)
            if gps_row is not None:
                writer.writerow(gps_row)
        file_exists = True

    ensure_csv_slot_capacity(CSV_LOG_FILE, target_slot_count)

    if not node_rows:
        return

    with open(CSV_LOG_FILE, "a", newline="") as csvfile:
        writer = csv.writer(csvfile)

        def row_to_block(row, slot_key):
            if row is None:
                return ["", "", "", "", "", "", "", "", ""]
            return [
                row.get("id"),
                row.get("serial"),
                row.get("address"),
                row.get("gas"),
                row.get("setpoint"),
                row.get("flow"),
                row.get("setpoint_raw"),
                row.get("flow_raw"),
                row.get("calibration_status"),
            ]

        def fill_missing_from_last(slot_key, block):
            last_block = last_csv_block_by_slot.get(slot_key)
            if last_block is None:
                return ["" if value is None else value for value in block]
            merged = []
            for idx, value in enumerate(block):
                if value in (None, ""):
                    merged.append(last_block[idx])
                else:
                    merged.append(value)
            return merged

        rows_by_key = {csv_row_slot_key(row): row for row in node_rows}

        blocks = []
        for slot_index in range(target_slot_count):
            slot_key = csv_slot_keys[slot_index] if slot_index < len(csv_slot_keys) else None
            raw_block = row_to_block(rows_by_key.get(slot_key) if slot_key is not None else None, slot_key)
            block = fill_missing_from_last(slot_key, raw_block)
            if slot_key is not None and any(cell not in (None, "") for cell in block):
                last_csv_block_by_slot[slot_key] = list(block)
            blocks.extend(block)

        writer.writerow([timestamp_utc, timestamp_local] + blocks)




def normalize_serial(serial: str) -> str:
    return serial.split("\x00")[0]


def parse_raw_value(reply: bytes) -> int:
    body = reply.decode(errors="ignore").strip()
    if len(body) < 15:
        raise ValueError("Short frame")
    value_hex = body[11:]
    if not value_hex:
        raise ValueError("Empty data")
    return int(value_hex, 16)


def raw_to_calibrated_flow(raw_value: int, cal) -> float:
    raw_percent = float(raw_value) * 100.0 / 32000.0
    corrected = float(cal.slope) * raw_percent + float(cal.offset)
    return corrected


def flow_to_register(desired_flow: float, cal) -> tuple[int, float, float]:
    if desired_flow <= 0:
        return 0, 0.0, 0.0

    raw_percent = (desired_flow - float(cal.offset)) / float(cal.slope)
    register = int(raw_percent * 32000 / 100)
    applied_raw_percent = float(register) * 100.0 / 32000.0
    applied_flow = float(cal.slope) * applied_raw_percent + float(cal.offset)
    return register, raw_percent, applied_flow


def debug_log(message: str):
    if MFC_CAL_DEBUG:
        print(f"DEBUG_CAL:{message}", flush=True)


def node_to_protocol(node_dec):
    if not (0 <= node_dec <= 255):
        raise ValueError("Node must be 0-255")
    return format(node_dec, "02X")


def read_status(address) -> bytes:
    node = node_to_protocol(address)
    return f':06{node}0401210120\r\n'.encode()
    


def read_setpoint(address) -> bytes:
    node = node_to_protocol(address)
    return f':06{node}0401210121\r\n'.encode()


def parse_flow(reply: bytes, max_flow: float) -> float:
    body = reply.decode(errors="ignore").strip()
    if len(body) < 15:
        raise ValueError("Short frame")
    value_hex = body[11:]
    if not value_hex:
        raise ValueError("Empty data")
    value_int = int(value_hex, 16)
    return value_int * max_flow / 32000


def send_command(ser, cmd: bytes) -> bytes:
    # Keep status polling responsive: skip this sample quickly if bus is busy.
    with serial_bus_lock(timeout=SERIAL_LOCK_TIMEOUT_STATUS_SECONDS):
        ser.reset_input_buffer()
        ser.write(cmd)
        reply = ser.read(100)
    if not reply:
        raise RuntimeError("No response")
    return reply


def handle_setpoint_command(mfc_id: int, setpoint: float) -> bool:
    """Handler for socket commands to set MFC setpoint."""
    try:
        nodes = handle_setpoint_command.nodes
        if mfc_id < 0 or mfc_id >= len(nodes):
            print(f"ERROR: Invalid MFC ID {mfc_id}", flush=True)
            return False
        
        nodeinfo = nodes[mfc_id]
        addr = nodeinfo["address"]
        serial_num = nodeinfo.get("serial", "unknown")
        serial_key = normalize_serial(serial_num)

        if serial_key not in selected_gas_by_mfc:
            print(f"ERROR: No gas selected yet for MFC {mfc_id}; send GAS downlink first", flush=True)
            return False

        gas_code = selected_gas_by_mfc[serial_key]
        gas_name = GAS_NAME_BY_CODE.get(gas_code)
        if gas_name is None:
            print(f"ERROR: Unsupported gas code 0x{gas_code:02X} for MFC {mfc_id}", flush=True)
            return False
        
        loader = get_calibration_loader()
        print(f"Searching exact calibration for {serial_num} with {gas_name}")
        cal, calibration_found, resolved_gas = resolve_runtime_calibration(loader, serial_num, gas_code)
        if not calibration_found:
            print(
                f"WARNING: No calibration found for serial={serial_key}; using fallback slope=1.0",
                flush=True,
            )
        cal.cal_min = float(cal.cal_min)
        cal.cal_max = float(cal.cal_max)
        cal.slope = float(cal.slope)
        cal.offset = float(cal.offset)
        
        desired_flow = max(0.0, min(cal.cal_max, setpoint))
        
        register, raw_percent, applied_flow = flow_to_register(desired_flow, cal)
        debug_log(
            f"SETPOINT mfc={mfc_id} serial={serial_key} gas={gas_name} "
            f"in={setpoint:.3f} clipped={desired_flow:.3f} "
            f"slope={cal.slope:.6f} offset={cal.offset:.6f} raw_percent={raw_percent:.6f}"
        )
        if not (0 <= raw_percent <= 100):
            print(f"ERROR: Flow {desired_flow} exceeds device limits", flush=True)
            return False
        
        propar_value = register
        print(
            f"INFO: Quantized setpoint for MFC {mfc_id}: requested={desired_flow:.4f}, applied={applied_flow:.4f}, register={propar_value}",
            flush=True,
        )
        
        node_inst = get_instrument(addr)
        with serial_bus_lock(timeout=SERIAL_LOCK_TIMEOUT_SECONDS):
            wrote = node_inst.writeParameter(9, propar_value)
        
        if wrote:
            with serial_bus_lock(timeout=SERIAL_LOCK_TIMEOUT_SECONDS):
                rb = node_inst.readParameter(9)
            print(f"INFO: Set MFC {mfc_id} setpoint to {desired_flow:.2f} (readback={rb})", flush=True)
            return True
        else:
            print(f"ERROR: Failed to write setpoint to MFC {mfc_id}", flush=True)
            return False
    except Exception as e:
        print(f"ERROR: Socket handler failed: {e}", flush=True)
        return False


def handle_gas_command(mfc_id: int, gas_cmd: int) -> bool:
    try:
        if mfc_id is None or gas_cmd is None:
            print("ERROR: Missing gas command fields", flush=True)
            return False

        mfc_id = int(mfc_id)
        gas_code = int(gas_cmd) & 0xFF

        nodes = handle_setpoint_command.nodes
        if mfc_id < 0 or mfc_id >= len(nodes):
            print(f"ERROR: Invalid MFC ID {mfc_id} for gas command", flush=True)
            return False

        nodeinfo = nodes[mfc_id]
        serial_key = normalize_serial(nodeinfo.get("serial", "unknown"))

        selected_gas_by_mfc[serial_key] = gas_code
        gas_name = GAS_NAME_BY_CODE.get(gas_code, "UNKNOWN")
        print(f"INFO: Selected gas for MFC {mfc_id} ({serial_key}) set to 0x{gas_code:02X} ({gas_name})", flush=True)
        return True
    except Exception as e:
        print(f"ERROR: Gas command handler failed: {e}", flush=True)
        return False


def publish_status(ser, nodes, log_csv=False):
    timestamp = gps.get_timestamp()
    combined = {
        "timestamp": timestamp,
        "nodes": []
    }

    loader = get_calibration_loader()

    for idx, nodeinfo in enumerate(nodes):
        addr = nodeinfo.get("address")
        serial_num = nodeinfo.get("serial", "unknown")
        serial_key = normalize_serial(serial_num)
        node_cache_key = f"{addr}:{serial_key}"

        try:
            gas_code = selected_gas_by_mfc.get(serial_key)
            cal, calibration_found, resolved_gas = resolve_runtime_calibration(loader, serial_num, gas_code)
            if not calibration_found:
                print(
                    f"WARNING: No calibration found for serial={serial_key}; using fallback slope=1.0",
                    flush=True,
                )

            cal.device = cal.device
            cal.cal_min = float(cal.cal_min)
            cal.cal_max = float(cal.cal_max)
            cal.slope = float(cal.slope)
            cal.offset = float(cal.offset)

            device = cal.device
            if isinstance(device, tuple):
                device = device[0]
            
            raw = send_command(ser, read_status(addr))
            flow_raw = parse_raw_value(raw)
            flow = raw_to_calibrated_flow(flow_raw, cal)

            try:
                rsp = send_command(ser, read_setpoint(addr))
                setpoint_raw = parse_raw_value(rsp)
                setpoint = raw_to_calibrated_flow(setpoint_raw, cal)
            except Exception:
                setpoint_raw = None
                setpoint = None

            debug_log(
                f"STATUS mfc={idx} serial={serial_key} gas_code={gas_code} "
                f"gas={GAS_NAME_BY_CODE.get(gas_code, 'UNKNOWN')} "
                f"slope={cal.slope:.6f} offset={cal.offset:.6f} "
                f"cal_min={cal.cal_min:.6f} cal_max={cal.cal_max:.6f} "
                f"raw_status='{raw.decode(errors='ignore').strip()}' flow_raw={flow_raw} flow={flow:.6f} "
                f"raw_setpoint={setpoint_raw} setpoint={(f'{setpoint:.6f}' if setpoint is not None else 'None')}"
            )

            if setpoint is None:
                print(f"STATUS:{idx}:{flow:.4f}", flush=True)
            else:
                gas_code_out = selected_gas_by_mfc.get(serial_key, -1)
                print(f"STATUS:{device}:{idx}:{flow:.4f}:{setpoint:.4f}:{gas_code_out}", flush=True)

            # Keep logging resilient even before a gas has been selected.
            gas_name = GAS_NAME_BY_CODE.get(gas_code, "UNKNOWN")
            if not calibration_found:
                gas_name = "UNKNOWN"
            
            combined["nodes"].append({
                "id": device,
                "serial": serial_num,
                "address": addr,
                "gas": gas_name,
                "flow": round(flow, 4),
                "setpoint": (round(setpoint, 4) if setpoint is not None else None),
                "flow_raw": flow_raw,
                "setpoint_raw": (round(setpoint_raw, 4) if setpoint_raw is not None else None),
                "calibration_status": ("FOUND" if calibration_found else "NO_CAL_SLOPE_1"),
            })
            last_status_row_by_node[node_cache_key] = dict(combined["nodes"][-1])

        except Exception as e:
            print(f"ERROR:node{idx}:{e}", flush=True)
            fallback = last_status_row_by_node.get(node_cache_key)
            if fallback is None:
                fallback = {
                    "id": nodeinfo.get("device", idx),
                    "serial": serial_num,
                    "address": addr,
                    "gas": GAS_NAME_BY_CODE.get(selected_gas_by_mfc.get(serial_key), "UNKNOWN"),
                    "flow": None,
                    "setpoint": None,
                    "flow_raw": None,
                    "setpoint_raw": None,
                    "calibration_status": "NO_CAL_SLOPE_1",
                }
            combined["nodes"].append(dict(fallback))

    print("COMBINED:" + json.dumps(combined), flush=True)

    if log_csv:
        timestamp_utc, timestamp_local, gps_coords = resolve_csv_timestamps(timestamp)
        append_status_rows_to_csv(timestamp_utc, timestamp_local, combined["nodes"], gps_coords)

    return combined


def main():
    nodes = []

    # Avoid dual-writer logging. API server now owns CSV logging.
    if _other_process_has_cmd_fragment("api_server.py"):
        print(
            "INFO: api_server.py is running; refusing to start legacy mfc_status_publisher logger",
            flush=True,
        )
        return

    try:
        ser = get_serial()
    except Exception as e:
        print(f"FATAL: Could not open serial: {e}", flush=True)
        sys.exit(1)

    try:
        bus = get_bus()

        def discover_nodes():
            try:
                with serial_bus_lock(timeout=SERIAL_LOCK_TIMEOUT_DISCOVERY_SECONDS):
                    discovered = bus.master.get_nodes() or []
                return discovered
            except Exception as discovery_error:
                print(f"WARNING: Node discovery failed: {discovery_error}", flush=True)
                return []

        nodes = discover_nodes()
        if nodes:
            print(f"INFO: Found {len(nodes)} MFC nodes", flush=True)
        else:
            print("INFO: No MFC nodes detected yet; waiting for at least one node", flush=True)

        print(f"INFO: Logging CSV to {CSV_LOG_FILE}", flush=True)

        handle_setpoint_command.nodes = nodes
        previous_node_signature = tuple((n.get("address"), normalize_serial(str(n.get("serial", "")))) for n in nodes)
        
        def command_handler(action, mfc_id=None, setpoint=None, gas_cmd=None):
            if action == "setpoint":
                success = handle_setpoint_command(mfc_id, setpoint)
                if success:
                    publish_status(ser, nodes, log_csv=True)
                return success
            elif action == "gas":
                return handle_gas_command(mfc_id, gas_cmd)
            elif action == "refresh":
                publish_status(ser, nodes, log_csv=True)
                return True
            elif action == "status":
                combined = publish_status(ser, nodes, log_csv=True)
                return {
                    "success": True,
                    "message": "OK",
                    "status": combined,
                }
            return False
        
        # Start TCP socket server for control commands
        socket_server = SocketServer(command_handler)
        socket_server.start()

        import os
        zero_flag_file = "zeroed.flag"

        def zero_nodes_once(active_nodes):
            for idx, nodeinfo in enumerate(active_nodes):
                try:
                    addr = nodeinfo["address"]
                    serial_num = nodeinfo.get("serial", "unknown")
                    print(f"INFO: Zeroing setpoint for node {idx} ({serial_num}) at address {addr}", flush=True)
                    node_inst = get_instrument(addr)
                    with serial_bus_lock(timeout=SERIAL_LOCK_TIMEOUT_SECONDS):
                        wrote = node_inst.writeParameter(9, 0)
                    if wrote:
                        with serial_bus_lock(timeout=SERIAL_LOCK_TIMEOUT_SECONDS):
                            rb = node_inst.readParameter(9)
                        print(f"INFO: Zeroed node {idx}, readback={rb}", flush=True)
                    else:
                        print(f"WARNING: Failed to write zero to node {idx}", flush=True)
                except Exception as e:
                    print(f"WARNING: Zeroing failed for node {idx}: {e}", flush=True)

        zeroing_done = os.path.exists(zero_flag_file)
        if not zeroing_done:
            if nodes:
                zero_nodes_once(nodes)
                with open(zero_flag_file, "w") as f:
                    f.write("zeroed")
                zeroing_done = True
            else:
                print("INFO: Zeroing deferred until at least one node is detected", flush=True)
        else:
            print("INFO: Zeroing already done, skipping", flush=True)

        # Publish initial status and write first CSV snapshot if nodes exist.
        if nodes:
            publish_status(ser, nodes, log_csv=True)
        else:
            print("INFO: Skipping initial CSV write until node discovery succeeds", flush=True)

        # Poll socket commands, refresh nodes, and publish status every second.
        next_log_time = time.monotonic() + LOG_INTERVAL_SECONDS
        next_discovery_time = time.monotonic()
        empty_discovery_count = 0
        transient_empty_discovery_threshold = 30
        while True:
            socket_server.handle_one()
            now = time.monotonic()
            if now >= next_log_time:
                if now >= next_discovery_time:
                    discovered_nodes = discover_nodes()
                    if discovered_nodes:
                        empty_discovery_count = 0
                        node_signature = tuple(
                            (n.get("address"), normalize_serial(str(n.get("serial", "")))) for n in discovered_nodes
                        )
                        if node_signature != previous_node_signature:
                            print(f"INFO: Node inventory updated: {len(discovered_nodes)} connected", flush=True)
                            previous_node_signature = node_signature

                        nodes = discovered_nodes
                        handle_setpoint_command.nodes = nodes
                        next_discovery_time = now + NODE_DISCOVERY_INTERVAL_SECONDS
                    else:
                        if nodes:
                            empty_discovery_count += 1
                            if empty_discovery_count >= transient_empty_discovery_threshold:
                                nodes = []
                                handle_setpoint_command.nodes = nodes
                                previous_node_signature = tuple()
                                print("INFO: No MFC nodes connected", flush=True)
                        else:
                            empty_discovery_count = transient_empty_discovery_threshold
                        next_discovery_time = now + NODE_DISCOVERY_INTERVAL_WHEN_EMPTY_SECONDS

                if not zeroing_done and nodes:
                    zero_nodes_once(nodes)
                    with open(zero_flag_file, "w") as f:
                        f.write("zeroed")
                    zeroing_done = True

                if nodes:
                    publish_status(ser, nodes, log_csv=True)

                # Keep interval steady even if one loop is delayed.
                while next_log_time <= now:
                    next_log_time += LOG_INTERVAL_SECONDS
            time.sleep(SOCKET_POLL_SLEEP_SECONDS)
       
    except Exception as e:
        print('ERROR:', e)
    finally:
        
        print("Zeroing before exit")

        for idx, nodeinfo in enumerate(nodes):
            try:
                addr = nodeinfo["address"]
                node_inst = get_instrument(addr)
                with serial_bus_lock(timeout=SERIAL_LOCK_TIMEOUT_SECONDS):
                    node_inst.writeParameter(9, 0)
                print(f"Zeroed node {idx}")
            except Exception as e:
                print(f"FAILED to zero node {idx}: {e}")

        ser.close()
        print("Program closed safely")



if __name__ == '__main__':
    main()
