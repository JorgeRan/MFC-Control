import csv
from dataclasses import dataclass
from typing import Dict, Tuple, Optional


@dataclass
class Calibration:
    device: str
    gas: str
    slope: float
    offset: float
    cal_min: float
    cal_max: float
    max_flow: Optional[float]


class CalibrationLoader:
    """
    Production-safe calibration loader.

    Guarantees:
    - No silent gas overwrite
    - Fast lookup
    - Numeric normalization
    - Backwards compatible with get(serial)
    """

    def __init__(self, filepath: str):
        self.filepath = filepath

        # Primary map: (serial, gas) -> Calibration
        self._cal_by_pair: Dict[Tuple[str, str], Calibration] = {}

        # Secondary map: serial -> default Calibration (first seen)
        self._default_by_serial: Dict[str, Calibration] = {}

        self._load_calibrations()

    # --------------------------------------------------
    # PUBLIC API — BACKWARD COMPATIBLE
    # --------------------------------------------------

    def get(self, serial: str) -> Calibration:
        """
        Backwards-compatible lookup.
        Returns default calibration for serial.
        """
        serial_key = self._clean_serial(serial)

        if serial_key not in self._default_by_serial:
            raise KeyError(f"No calibration found for {serial_key}")

        return self._default_by_serial[serial_key]

    def get_for_gas(self, serial: str, gas: str) -> Calibration:
        """
        Preferred production lookup.
        Exact serial + gas match required.
        """
        serial_key = self._clean_serial(serial)
        gas_key = gas.strip().upper()

        key = (serial_key, gas_key)

        if key not in self._cal_by_pair:
            available = self.available_gases(serial_key)
            raise KeyError(
                f"No calibration for serial={serial_key}, gas={gas_key}. "
                f"Available gases: {available}"
            )

        return self._cal_by_pair[key]

    def find_best_calibration(self, serial: str, gas: str):
        """
        Safe fallback lookup.
        Returns (calibration, used_gas)
        """
        serial_key = self._clean_serial(serial)
        gas_key = gas.strip().upper()

        key = (serial_key, gas_key)

        if key in self._cal_by_pair:
            return self._cal_by_pair[key], gas_key

        available = self.available_gases(serial_key)

        if available:
            chosen = available[0]
            print(
                f"[CalibrationLoader] Gas '{gas_key}' not found for serial "
                f"'{serial_key}'. Using '{chosen}' instead.",
                flush=True,
            )
            return self._cal_by_pair[(serial_key, chosen)], chosen

        print(
            f"[CalibrationLoader] No calibrations found for serial "
            f"'{serial_key}'.",
            flush=True,
        )
        return None, None

    def available_gases(self, serial: str):
        serial_key = self._clean_serial(serial)
        return sorted(
            gas for (s, gas) in self._cal_by_pair.keys() if s == serial_key
        )

    # --------------------------------------------------
    # INTERNALS
    # --------------------------------------------------

    def _clean_serial(self, serial: str) -> str:
        return serial.split("\x00")[0].strip()

    def _safe_float(self, value: str) -> Optional[float]:
        if value is None:
            return None
        value = value.strip()
        if value == "":
            return None
        return float(value)

    def _load_calibrations(self):
        loaded = 0

        with open(self.filepath, newline="") as f:
            reader = csv.DictReader(f, delimiter="\t")

            for row in reader:
                try:
                    device = row["MFC"].split("-")[0]
                    serial = self._clean_serial(row["MFC"].split("-")[2])
                    gas = row["Cal Species"].strip().upper()

                    cal = Calibration(
                        device=device,
                        gas=gas,
                        slope=float(row["Slope"]),
                        offset=float(row["Offset"]),
                        cal_min=float(row["Cal Min [SLPM]"]),
                        cal_max=float(row["Cal Max [SLPM]"]),
                        max_flow=self._safe_float(row["Max Flow [SLPM]"]),
                    )

                    # Primary mapping
                    self._cal_by_pair[(serial, gas)] = cal

                    # Default mapping (first one wins — deterministic)
                    if serial not in self._default_by_serial:
                        self._default_by_serial[serial] = cal

                    loaded += 1

                except Exception as e:
                    print(f"Skipping bad calibration row: {e}", flush=True)

        print(
            f"[CalibrationLoader] Loaded {loaded} calibrations "
            f"({len(self._default_by_serial)} devices)",
            flush=True,
        )


# --------------------------------------------------
# OPTIONAL UTILITY (unchanged behavior)
# --------------------------------------------------

def apply_calibration(raw_flow: float, cal: Calibration) -> float:
    corrected = float(cal.slope) * float(raw_flow) + float(cal.offset)

    if corrected < cal.cal_min:
        corrected = cal.cal_min
    if corrected > cal.cal_max:
        corrected = cal.cal_max

    return corrected
