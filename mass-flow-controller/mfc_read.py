import time
import serial
import threading
import sys
from calibration_loader import CalibrationLoader
from shared_resources import get_bus

PORT = '/dev/ttyUSB0'
BAUD = 38400
TIMEOUT = 1

ser = None
CAL_FILE = '/home/pi/Documents/Radiolib/examples/NonArduino/Raspberry_copy/mass-flow-controller/MFCCalibrations-ReadDirectlyByFlareCode.txt'

# ------------------ Protocol helpers ------------------

def node_to_protocol(node_dec):
    if not (0 <= node_dec <= 255):
        raise ValueError("Node must be 0-255")
    return format(node_dec, "02X")
    
def control_read(address) -> bytes:
    node = node_to_protocol(address)
    return f':06{node}0401040104\r\n'.encode()
    
def control_write(address) -> bytes:
    node = node_to_protocol(address)
    return f':05{node}01010400\r\n'.encode()

def read_status(address) -> bytes:
    node = node_to_protocol(address)
    return f':06{node}0401210120\r\n'.encode()
    


def read_setpoint(address: int) -> bytes:
    node = node_to_protocol(address)
    return f':06{node}0401210121\r\n'.encode()

def write_setpoint(raw_percent: float, address: int) -> bytes:
    node = node_to_protocol(address)

    raw_percent = max(0.0, min(100.0, raw_percent))

    value = int(raw_percent * 32000 / 100)
    hexval = format(value, "04X")

    return f':06{node}010121{hexval}\r\n'.encode()

def valid_reply(reply: bytes):
    return reply.startswith(b':') and reply.endswith(b'\r\n')

# ------------------ Parsing ------------------

def parse_flow(reply: bytes, max_flow: float) -> float:
    body = reply.decode(errors="ignore").strip()

    if len(body) < 15:
        raise ValueError("Short frame")

    value_hex = body[11:]
    if not value_hex:
        raise ValueError("Empty data")

    value_int = int(value_hex, 16)
    return value_int * max_flow / 32000


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
    return float(cal.slope) * raw_percent + float(cal.offset)


def flow_to_register(desired_flow: float, cal) -> tuple[int, float, float]:
    raw_percent = (desired_flow - float(cal.offset)) / float(cal.slope)
    register = int(raw_percent * 32000 / 100)
    applied_raw_percent = float(register) * 100.0 / 32000.0
    applied_flow = float(cal.slope) * applied_raw_percent + float(cal.offset)
    return register, raw_percent, applied_flow

# ------------------ Serial IO ------------------

def send_command(cmd: bytes) -> bytes:
    ser.reset_input_buffer()
    ser.write(cmd)
    reply = ser.read(100)
    if not reply:
        raise RuntimeError("No response")
    return reply

# ------------------ Control loop ------------------

def control_loop(cal, address):

    print("\n--- CONTROL READY ---")
    print(f"Calibration: slope={cal.slope}, offset={cal.offset}")
    print(f"Range: {cal.cal_min} → {cal.cal_max} LN/min\n")

    def status_thread():
        while True:
            try:
                raw = send_command(read_status(address))
                flow_raw = parse_raw_value(raw)
                flow = raw_to_calibrated_flow(flow_raw, cal)
                print(f"[STATUS] Flow: {flow:.4f} LN/min (raw={flow_raw})")
            except Exception as e:
                print("[STATUS ERROR]", e)

            time.sleep(5)

    time.sleep(1)
    threading.Thread(target=status_thread, daemon=True).start()

    while True:
        try:
            user = input("Set flow LN/min (or q): ").strip()
            if user.lower() == 'q':
                break

            desired_flow = float(user)
            
            if desired_flow < cal.cal_min:
                desired_flow = cal.cal_min
            if desired_flow > cal.cal_max:
                desired_flow = cal.cal_max
   
            # if not (cal.cal_min <= desired_flow <= cal.cal_max):
            #     print("Outside calibration range")
            #     continue

            raw_percent = (desired_flow - cal.offset) / cal.slope

            if not (0 <= raw_percent <= 100):
                print("Command exceeds device limits")
                continue

            register, raw_percent_quantized, applied_flow = flow_to_register(desired_flow, cal)
            if not (0 <= register <= 32000):
                print("Quantized register exceeds device limits")
                continue

            print(
                f"Quantized setpoint: requested={desired_flow:.4f}, applied={applied_flow:.4f}, "
                f"raw_percent={raw_percent_quantized:.6f}, register={register}"
            )
            print(f"Sending {raw_percent_quantized:.2f}% to MFC")
            ack = send_command(write_setpoint(raw_percent_quantized, address))
            print("ACK:", ack)
            
            time.sleep(1)
            
            r_setpoint = send_command(read_setpoint(address=address))
            setpoint_raw = parse_raw_value(r_setpoint)
            setpoint_calibrated = raw_to_calibrated_flow(setpoint_raw, cal)
            print(f"Current Setpoint: {setpoint_calibrated:.4f} LN/min (raw={setpoint_raw})")
            
            

        except Exception as e:
            print("Error:", e)

# ------------------ Main ------------------

def _main_block():
    global ser
    
    try:
        ser = serial.Serial(PORT, BAUD, timeout=TIMEOUT)
        print("Serial port opened")
    except Exception as e:
        print(f"Fatal error opening serial port: {e}")
        return

    try:
        bus = get_bus()
        nodes = bus.master.get_nodes()
        if not nodes:
            print("Fatal error: No MFC nodes found")
            return
        print(f"{nodes}")
        for node in nodes:
            address = node["address"]
            serial_num = node["serial"]
            serial_key = serial_num.split("\x00")[0]
        
            print(f"connected to {serial_num} with address {address}")

        # loader = CalibrationLoader(CAL_FILE)

        # gas_name = None
        # if len(sys.argv) > 1:
        #     gas_name = sys.argv[1].strip().upper()

        # if gas_name:
        #     cal = loader.get_for_gas(serial_key, gas_name)
        #     print(f"Using calibration gas: {gas_name}")
        # else:
        #     cal = loader.get(serial=serial_key)
        #     print(f"Using default calibration gas: {cal.gas}")

        # cal.cal_min = float(cal.cal_min)
        # cal.cal_max = float(cal.cal_max)
        # cal.slope = float(cal.slope)
        # cal.offset = float(cal.offset)

        # print(f"Connected to {serial_num} with node address {address}")

        # control_loop(cal=cal, address=address)
        
        print(send_command(write_setpoint(0, address=address)))

    except Exception as e:
        print("Fatal error:", e)

    finally:
        try:
            if ser:
                ser.close()
        except Exception:
            pass


if __name__ == '__main__':
    _main_block()
