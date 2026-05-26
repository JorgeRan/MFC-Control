import time
import serial
import pynmea2
from datetime import datetime, timezone


def get_locked_coordinates(timeout: float = 2.0):
    """Return (latitude, longitude) once a valid GPS lock is available.
    Returns None when no lock is found before timeout.
    """
    start = time.time()
    try:
        ser = serial.Serial('/dev/serial0', 9600, timeout=0.5)
    except Exception:
        return None

    try:
        while time.time() - start < timeout:
            try:
                line = ser.readline().decode('ascii', errors='replace').strip()
            except Exception:
                continue

            if not line:
                continue

            if line.startswith(('$GPRMC', '$GNRMC')):
                try:
                    msg = pynmea2.parse(line)
                    # RMC status 'A' means valid fix.
                    if getattr(msg, 'status', None) == 'A':
                        lat = getattr(msg, 'latitude', None)
                        lon = getattr(msg, 'longitude', None)
                        if lat is not None and lon is not None:
                            return float(lat), float(lon)
                except Exception:
                    continue
    finally:
        try:
            ser.close()
        except Exception:
            pass

    return None


def get_timestamp(timeout: float = 2.0) -> str:
    """Try to read an RMC sentence from GPS and return UTC timestamp in ISO format.
    Falls back to system UTC time if GPS isn't available or no valid sentence is received.
    """
    start = time.time()
    try:
        ser = serial.Serial('/dev/serial0', 9600, timeout=0.5)
    except Exception:
        print("No GPS signal")
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')

    try:
        while time.time() - start < timeout:
            try:
                line = ser.readline().decode('ascii', errors='replace').strip()
            except Exception:
                continue
            if not line:
                continue
            if line.startswith(('$GPRMC', '$GNRMC')):
                try:
                    msg = pynmea2.parse(line)
                    now = datetime.now(timezone.utc)
                    ts = datetime(now.year, now.month, now.day,
                                  msg.timestamp.hour, msg.timestamp.minute, msg.timestamp.second,
                                  tzinfo=timezone.utc)
                    return ts.replace(microsecond=0).isoformat().replace('+00:00', 'Z')
                except Exception:
                    continue
    finally:
        try:
            ser.close()
        except Exception:
            pass

    print("No GPS signal")
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')

if __name__ == '__main__':
    print(get_timestamp())
