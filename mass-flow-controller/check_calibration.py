#!/usr/bin/env python3
import sys

def check_calibration_file(calib_file, serial, gas):
    found = False
    with open(calib_file, 'r') as f:
        for line in f:
            if line.strip() == '' or line.startswith('MFC'):
                continue
            parts = line.split('\t')
            if len(parts) < 2:
                continue
            device = parts[0].strip()
            cal_gas = parts[1].strip().upper()
            if serial in device and cal_gas == gas.upper():
                print(f"Found calibration: {line.strip()}")
                found = True
    if not found:
        print(f"No calibration found for device '{serial}' and gas '{gas}'")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} <calibration_file> <device_serial> <gas>")
        sys.exit(1)
    calib_file = sys.argv[1]
    serial = sys.argv[2]
    gas = sys.argv[3]
    check_calibration_file(calib_file, serial, gas)
