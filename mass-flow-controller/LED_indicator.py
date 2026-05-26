import threading
import os
import traceback
from time import sleep

try:
    from gpiozero import LED as _LED
    _GPIO_OK = True
    _GPIO_IMPORT_ERROR = None
except Exception:
    _GPIO_OK = False
    _GPIO_IMPORT_ERROR = traceback.format_exc()


class _FakeLED:
    """No-op stand-in for environments without GPIO."""
    def on(self): pass
    def off(self): pass


class LEDController:
    STATE_OK            = "ok"
    STATE_UPDATING      = "updating"
    STATE_GPS_SEARCHING = "gps_searching"
    STATE_ERROR         = "error"

    _instance = None
    _instance_lock = threading.Lock()

    _BLINK_ON  = 0.35   
    _BLINK_OFF = 0.35   

    def __new__(cls, *args, **kwargs):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self._green = _FakeLED()
        self._yellow = _FakeLED()
        self._red = _FakeLED()
        self._using_fake_leds = True

        if _GPIO_OK:
            green_pin = int(os.getenv("LED_PIN_GREEN", "27"))
            yellow_pin = int(os.getenv("LED_PIN_YELLOW", "22"))
            red_pin = int(os.getenv("LED_PIN_RED", "23"))
            active_high = True
            try:
                self._green = _LED(green_pin, active_high=active_high)
                self._yellow = _LED(yellow_pin, active_high=active_high)
                self._red = _LED(red_pin, active_high=active_high)
                self._using_fake_leds = False
                print(
                    f"[LED] Pins configured G={green_pin} Y={yellow_pin} R={red_pin} active_high={active_high}",
                    flush=True,
                )
            except Exception as e:
                print(f"[LED] GPIO init failed, LEDs disabled: {e}", flush=True)
        else:
            print("[LED] gpiozero import failed, LEDs disabled", flush=True)
            if _GPIO_IMPORT_ERROR:
                print(f"[LED] gpiozero import error detail:\n{_GPIO_IMPORT_ERROR}", flush=True)

        self._state        = self.STATE_OK
        self._lock         = threading.Lock()
        self._change_event = threading.Event()
        self._stop_event   = threading.Event()

        self._thread = threading.Thread(
            target=self._run, daemon=True, name="led-controller"
        )
        self._thread.start()

        if self._using_fake_leds:
            print("[LED] Running in no-op LED mode", flush=True)
        else:
            print("[LED] Hardware LED mode enabled", flush=True)

        self._initialized = True

 

    def set_state(self, state: str) -> None:
        with self._lock:
            self._state = state
        self._change_event.set()

    def stop(self) -> None:
        self._stop_event.set()
        self._change_event.set()
        self._thread.join(timeout=3.0)
        self._all_off()


    def _all_off(self):
        self._green.off()
        self._yellow.off()
        self._red.off()

    def _get_state(self) -> str:
        with self._lock:
            return self._state

    def _wait(self, seconds: float) -> bool:
        """"""
        triggered = self._change_event.wait(timeout=seconds)
        if triggered:
            self._change_event.clear()
        return triggered


    def _startup_sequence(self):
        for _ in range(3):
            for led in (self._red, self._yellow, self._green):
                if self._stop_event.is_set():
                    return
                self._all_off()
                led.on()
                sleep(0.3)
                led.off()
                sleep(0.1)
        self._all_off()



    def _run(self):
        self._startup_sequence()

        while not self._stop_event.is_set():
            state = self._get_state()

            if state == self.STATE_OK:
                self._all_off()
                self._green.on()
                self._wait(60.0)  
            elif state == self.STATE_UPDATING:
                self._all_off()
                self._green.on()
                if self._wait(self._BLINK_ON):
                    continue       
                self._green.off()
                self._wait(self._BLINK_OFF)

            elif state == self.STATE_GPS_SEARCHING:
                self._all_off()
                self._yellow.on()
                if self._wait(self._BLINK_ON):
                    continue
                self._yellow.off()
                self._wait(self._BLINK_OFF)

            elif state == self.STATE_ERROR:
                self._all_off()
                self._red.on()
                self._wait(60.0)

            else:
                self._wait(1.0)

        self._all_off()

