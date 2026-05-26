import sys
from calibration_loader import CalibrationLoader
from shared_resources import get_bus
from socket_commands import send_setpoint_command

CAL_FILE = '/home/pi/Documents/Radiolib/examples/NonArduino/Raspberry_copy/mass-flow-controller/MFCCalibrations-ReadDirectlyByFlareCode.txt'

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


def normalize_serial(serial: str) -> str:
    return serial.split("\x00")[0]


def flow_to_register(desired_flow: float, cal) -> tuple[int, float, float, float]:
    if desired_flow <= 0:
        return 0, 0.0, 0.0, 0.0

    raw_percent = (desired_flow - float(cal.offset)) / float(cal.slope)
    register = int(raw_percent * 32000 / 100)
    applied_raw_percent = float(register) * 100.0 / 32000.0
    applied_flow = float(cal.slope) * applied_raw_percent + float(cal.offset)
    return register, raw_percent, applied_raw_percent, applied_flow


def preview_quantized_setpoint(mfc_index: int, desired_flow: float, gas_code: int):
    try:
        bus = get_bus()
        nodes = bus.master.get_nodes()
        if mfc_index < 0 or mfc_index >= len(nodes):
            return

        serial_num = nodes[mfc_index].get("serial", "")
        serial_key = normalize_serial(serial_num)

        gas_name = GAS_NAME_BY_CODE.get(gas_code)
        if gas_name is None:
            print(f"INFO: No calibration preview (unsupported gas code 0x{gas_code:02X})")
            return

        loader = CalibrationLoader(CAL_FILE)
        cal = loader.get_for_gas(serial_key, gas_name)

        desired_flow = max(0.0, min(float(cal.cal_max), desired_flow))
        register, raw_percent, applied_raw_percent, applied_flow = flow_to_register(desired_flow, cal)

        print(
            "Quantized preview: "
            f"serial={serial_key}, gas={gas_name}, requested={desired_flow:.4f}, "
            f"raw_percent={raw_percent:.6f}, register={register}, "
            f"applied_percent={applied_raw_percent:.6f}, applied={applied_flow:.4f}"
        )
    except Exception as e:
        print(f"INFO: Calibration preview unavailable: {e}")

def main():
    if len(sys.argv) < 3:
        sys.exit(1)
    try:
        print(sys.argv)
        desired_flow = float(sys.argv[1])
        mfc_index = int(sys.argv[2])
        gas = int(sys.argv[3])
    except (ValueError, IndexError) as e:
        print(f"Error: Invalid arguments. {e}")
        print("Usage: mfc_setpoint_controller.py <desired_flow_LN_min> <mfc_index>")
        sys.exit(1)
    
    print(f'Desired flow: {desired_flow}')
    print(f'MFC index: {mfc_index}')
    print(f'Selected Gas: {gas}')
    preview_quantized_setpoint(mfc_index, desired_flow, gas)
    
    print(f"Sending setpoint command: mfc_index={mfc_index}, desired_flow={desired_flow}")
    response = send_setpoint_command(mfc_index, desired_flow, timeout=5.0)
    
    if response["success"]:
        print(f"Success! {response['message']}")
    else:
        print(f"Error: {response['message']}")
        sys.exit(1)

if __name__ == "__main__":
    main()
