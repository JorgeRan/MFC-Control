import time
import sys
import json
from calibration_loader import CalibrationLoader
import gps
from shared_resources import get_serial, get_bus, get_instrument
from socket_commands import SocketServer

PORT = '/dev/ttyUSB0'
BAUD = 38400
TIMEOUT = 1

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
        print(addr)
        serial_num = nodeinfo.get("serial", "unknown")
        
        print(serial_num)

        if mfc_id not in selected_gas_by_mfc:
            print(f"ERROR: No gas selected yet for MFC {mfc_id}; send GAS downlink first", flush=True)
            return False

        gas_code = selected_gas_by_mfc[mfc_id]
        print(gas_code)
        gas_name = GAS_NAME_BY_CODE.get(gas_code)
        print(gas_name)
        if gas_name is None:
            print(f"ERROR: Unsupported gas code 0x{gas_code:02X} for MFC {mfc_id}", flush=True)
            return False
        
        loader = CalibrationLoader("/home/pi/Documents/Radiolib/examples/NonArduino/Raspberry_copy/mass-flow-controller/MFCCalibrations-ReadDirectlyByFlareCode.txt")
        cal, gas = loader.find_best_calibration(serial_num, gas_name)
        if cal is None:
            print(f"ERROR: No calibration found for MFC {mfc_id} serial={serial_num} gas={gas_name}", flush=True)
            return False
        cal.cal_min = float(cal.cal_min)
        cal.cal_max = float(cal.cal_max)
        cal.slope = float(cal.slope)
        cal.offset = float(cal.offset)
        
        desired_flow = max(cal.cal_min, min(cal.cal_max, setpoint))
        
        raw_percent = (desired_flow - cal.offset) / cal.slope
        if not (0 <= raw_percent <= 100):
            print(f"ERROR: Flow {desired_flow} exceeds device limits", flush=True)
            return False
        
        propar_value = int(raw_percent * 32000 / 100)
        
        node_inst = get_instrument(addr)
        wrote = node_inst.writeParameter(9, propar_value)
        
        if wrote:
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

        selected_gas_by_mfc[mfc_id] = gas_code
        gas_name = GAS_NAME_BY_CODE.get(gas_code, "UNKNOWN")
        print(f"INFO: Selected gas for MFC {mfc_id} set to 0x{gas_code:02X} ({gas_name})", flush=True)
        return True
    except Exception as e:
        print(f"ERROR: Gas command handler failed: {e}", flush=True)
        return False


def publish_status(ser, nodes):
    combined = {
        "timestamp": gps.get_timestamp(),
        "nodes": []
    }

    for idx, nodeinfo in enumerate(nodes[:2]):
        try:
            addr = nodeinfo["address"]
            serial_num = nodeinfo.get("serial", "unknown")

            loader = CalibrationLoader("/home/pi/Documents/Radiolib/examples/NonArduino/Raspberry_copy/mass-flow-controller/MFCCalibrations-ReadDirectlyByFlareCode.txt")
            cal = loader.get(serial=serial_num)
            cal.device = cal.device
            cal.cal_min = float(cal.cal_min)
            cal.cal_max = float(cal.cal_max)
            cal.slope = float(cal.slope)
            cal.offset = float(cal.offset)

            device = cal.device
            if isinstance(device, tuple):
                device = device[0]
            
            raw = send_command(ser, read_status(addr))
            flow = parse_flow(raw, cal.cal_max)

            try:
                rsp = send_command(ser, read_setpoint(addr))
                setpoint = parse_flow(rsp, cal.cal_max)
            except Exception:
                setpoint = None

            if setpoint is None:
                print(f"STATUS:{idx}:{flow:.2f}", flush=True)
            else:
                print(f"STATUS:{device}:{idx}:{flow:.2f}:{setpoint:.2f}", flush=True)

            combined["nodes"].append({
                "id": idx,
                "serial": serial_num,
                "address": addr,
                "flow": round(flow, 2),
                "setpoint": (round(setpoint, 2) if setpoint is not None else None)
            })

        except Exception as e:
            print(f"ERROR:node{idx}:{e}", flush=True)

    print("COMBINED:" + json.dumps(combined), flush=True)


def main():
    try:
        ser = get_serial()
    except Exception as e:
        print(f"FATAL: Could not open serial: {e}", flush=True)
        sys.exit(1)

    try:
        bus = get_bus()
        nodes = bus.master.get_nodes()
        if not nodes:
            print("FATAL: No nodes found", flush=True)
            try:
                ser.close()
            except Exception:
                pass
            sys.exit(1)

        print(f"INFO: Found {len(nodes)} MFC nodes", flush=True)

        # Store nodes reference for socket handler
        handle_setpoint_command.nodes = nodes
        
        def command_handler(action, mfc_id=None, setpoint=None, gas_cmd=None):
            if action == "setpoint":
                success = handle_setpoint_command(mfc_id, setpoint)
                if success:
                    publish_status(ser, nodes)
                return success
            elif action == "gas":
                return handle_gas_command(mfc_id, gas_cmd)
            elif action == "refresh":
                publish_status(ser, nodes)
                return True
            return False
        
        # Start TCP socket server for control commands
        socket_server = SocketServer(command_handler)
        socket_server.start()

        import os
        zero_flag_file = "zeroed.flag"
        if not os.path.exists(zero_flag_file):
            for idx, nodeinfo in enumerate(nodes[:2]):
                try:
                    addr = nodeinfo["address"]
                    serial_num = nodeinfo.get("serial", "unknown")
                    print(f"INFO: Zeroing setpoint for node {idx} ({serial_num}) at address {addr}", flush=True)
                    node_inst = get_instrument(addr)
                    wrote = node_inst.writeParameter(9, 0)
                    if wrote:
                        rb = node_inst.readParameter(9)
                        print(f"INFO: Zeroed node {idx}, readback={rb}", flush=True)
                    else:
                        print(f"WARNING: Failed to write zero to node {idx}", flush=True)
                    handle_setpoint_command.nodes = nodes
                    handle_setpoint_command.loader = CalibrationLoader('/home/pi/Documents/Radiolib/examples/NonArduino/Raspberry_copy/mass-flow-controller/MFCCalibrations-ReadDirectlyByFlareCode.txt')
                    print(f"WARNING: Zeroing failed for node {idx}: {e}", flush=True)
                except:
                    print("Error")
                
            with open(zero_flag_file, "w") as f:
                f.write("zeroed")
        else:
            print("INFO: Zeroing already done, skipping", flush=True)

        # Publish initial status
        publish_status(ser, nodes)

        # Now loop to handle socket commands
        while True:
            socket_server.handle_one()
       
    except Exception as e:
        print('ERROR:', e)
    finally:
        
        print("Zeroing before exit")

        for idx, nodeinfo in enumerate(nodes[:2]):
            try:
                addr = nodeinfo["address"]
                node_inst = get_instrument(addr)
                node_inst.writeParameter(9, 0)
                print(f"Zeroed node {idx}")
            except Exception as e:
                print(f"FAILED to zero node {idx}: {e}")

        ser.close()
        print("Program closed safely")



if __name__ == '__main__':
    main()
