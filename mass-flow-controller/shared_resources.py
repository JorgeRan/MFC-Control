import serial
import propar
import time
import fcntl
from contextlib import contextmanager

if not hasattr(propar, "instrument"):
    raise ImportError(
        "Loaded the wrong 'propar' package. Install the Bronkhorst library with:\n"
        "  pip uninstall -y propar\n"
        "  pip install bronkhorst-propar"
    )

# Shared configuration
PORT = '/dev/ttyUSB0'
BAUD = 38400
TIMEOUT = 1

# Internal singletons
_serial = None
_bus = None
_instruments = {}
_lock_file_handle = None
LOCK_FILE = '/tmp/mfc_serial_bus.lock'
DEFAULT_SERIAL_LOCK_TIMEOUT = 8.0


def get_serial():
    """Return a single shared `serial.Serial` instance (opens once)."""
    global _serial
    if _serial is None:
        _serial = serial.Serial(port=PORT, baudrate=BAUD, timeout=TIMEOUT)
    return _serial


def _get_lock_file_handle():
    global _lock_file_handle
    if _lock_file_handle is None or _lock_file_handle.closed:
        _lock_file_handle = open(LOCK_FILE, 'a+')
    return _lock_file_handle


@contextmanager
def serial_bus_lock(timeout: float = DEFAULT_SERIAL_LOCK_TIMEOUT, poll_interval: float = 0.02):
    """Cross-process lock for /dev/ttyUSB0 access.

    Both backend and logger run in separate processes; this lock prevents them
    from interleaving serial/propar reads and writes on the same bus.
    """
    fh = _get_lock_file_handle()
    deadline = time.monotonic() + max(0.0, timeout)

    while True:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() >= deadline:
                raise TimeoutError('Timed out waiting for serial bus lock')
            time.sleep(poll_interval)

    try:
        yield
    finally:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def get_bus():
    """Return a single shared propar bus (calls propar.instrument once)."""
    global _bus
    if _bus is None:
        _bus = propar.instrument(PORT)
    return _bus


def get_instrument(address):
    """Return a cached per-address instrument created via propar.instrument.

    Instruments are cached so repeated calls don't re-open the port
    or re-create the same object multiple times.
    """
    global _instruments
    if address in _instruments:
        return _instruments[address]
    inst = propar.instrument(PORT, address=address)
    _instruments[address] = inst
    return inst


def close_all():
    """Close any opened resources. Safe to call on shutdown."""
    global _serial, _bus, _instruments, _lock_file_handle
    try:
        if _serial is not None:
            try:
                _serial.close()
            except Exception:
                pass
    finally:
        _serial = None

    _instruments = {}
    _bus = None
    if _lock_file_handle is not None:
        try:
            _lock_file_handle.close()
        except Exception:
            pass
        _lock_file_handle = None
