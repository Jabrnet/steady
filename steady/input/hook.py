import logging
import threading
import time

import evdev

from steady.core.filter import TremorFilter
from steady.input.device_finder import find_primary_mouse
from steady.input.gravity import ATSPIPoller, apply_gravity

logger = logging.getLogger(__name__)

UINPUT_CAPABILITIES = {
    evdev.ecodes.EV_REL: [
        evdev.ecodes.REL_X,
        evdev.ecodes.REL_Y,
        evdev.ecodes.REL_WHEEL,
        evdev.ecodes.REL_HWHEEL,
    ],
    evdev.ecodes.EV_KEY: [
        evdev.ecodes.BTN_LEFT,
        evdev.ecodes.BTN_RIGHT,
        evdev.ecodes.BTN_MIDDLE,
        evdev.ecodes.BTN_SIDE,
        evdev.ecodes.BTN_EXTRA,
    ],
}

RETRY_DELAY = 2.0


class InputHook:
    """
    Background thread that:
      1. Grabs the physical mouse exclusively via evdev
      2. Applies TremorFilter to accumulated absolute position
      3. Applies AT-SPI gravity pull toward nearby UI elements
      4. Writes filtered+gravity-adjusted events to a uinput virtual mouse
      5. Pushes (raw, filtered) positions to the shared PositionBuffer
    """

    def __init__(self, state, ml_adapter=None):
        self._state = state
        self._ml_adapter = ml_adapter
        self._stop = threading.Event()
        self._poller = ATSPIPoller()
        self._thread = threading.Thread(
            target=self._run,
            name='input-hook',
            daemon=True,
        )

    def start(self):
        self._poller.start_polling()
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._poller.stop()
        self._thread.join(timeout=3.0)

    def set_ml_adapter(self, adapter):
        self._ml_adapter = adapter

    # ------------------------------------------------------------------

    def _run(self):
        while not self._stop.is_set():
            device = find_primary_mouse()
            if device is None:
                logger.warning("No mouse found, retrying in %.0fs", RETRY_DELAY)
                self._stop.wait(RETRY_DELAY)
                continue

            ui = None
            try:
                ui = evdev.UInput(UINPUT_CAPABILITIES, name='steady-filtered-mouse')
            except (OSError, PermissionError) as exc:
                logger.error("Cannot open /dev/uinput: %s", exc)
                device.close()
                self._stop.wait(RETRY_DELAY)
                continue

            try:
                device.grab()
            except OSError as exc:
                logger.error("Cannot grab %s: %s", device.path, exc)
                ui.close()
                device.close()
                self._stop.wait(RETRY_DELAY)
                continue

            logger.info("Grabbed %s at %s", device.name, device.path)
            try:
                self._event_loop(device, ui)
            except OSError as exc:
                logger.warning("Device lost (%s), will retry", exc)
            finally:
                try:
                    device.ungrab()
                except OSError:
                    pass
                device.close()
                ui.close()

    def _event_loop(self, device, ui):
        state = self._state

        tremor_filter = TremorFilter(state.profile_name)
        if self._ml_adapter is not None:
            self._ml_adapter.set_filter(tremor_filter)

        abs_x = 0.0
        abs_y = 0.0
        last_out_x = 0.0
        last_out_y = 0.0
        frac_x = 0.0
        frac_y = 0.0

        for event in device.read_loop():
            if self._stop.is_set():
                break

            if state.changed.is_set():
                state.changed.clear()
                tremor_filter = TremorFilter(state.profile_name)
                tremor_filter.x_state = abs_x
                tremor_filter.y_state = abs_y
                last_out_x = abs_x
                last_out_y = abs_y
                frac_x = 0.0
                frac_y = 0.0
                if self._ml_adapter is not None:
                    self._ml_adapter.set_filter(tremor_filter)

            if event.type == evdev.ecodes.EV_SYN:
                ui.write(evdev.ecodes.EV_SYN, evdev.ecodes.SYN_REPORT, 0)
                continue

            if event.type != evdev.ecodes.EV_REL:
                ui.write(event.type, event.code, event.value)
                continue

            if event.code not in (evdev.ecodes.REL_X, evdev.ecodes.REL_Y):
                ui.write(event.type, event.code, event.value)
                continue

            if event.code == evdev.ecodes.REL_X:
                abs_x += event.value
            else:
                abs_y += event.value

            if not state.enabled:
                ui.write(evdev.ecodes.EV_REL, event.code, event.value)
                last_out_x = abs_x
                last_out_y = abs_y
                frac_x = 0.0
                frac_y = 0.0
                continue

            # Apply tremor filter
            fx, fy = tremor_filter.filter_position((abs_x, abs_y))

            # Apply AT-SPI gravity (after filter, before output)
            if self._poller.available:
                targets = self._poller.get_targets()
                fx, fy = apply_gravity(fx, fy, targets)

            # Push to shared ring buffer for overlay and ML
            buf = state.position_buffer
            if buf is not None:
                buf.push(time.monotonic(), abs_x, abs_y, fx, fy)

            # Convert filtered absolute position back to relative integers
            # with sub-pixel accumulation to prevent drift
            frac_x += fx - last_out_x
            int_dx = int(frac_x)
            frac_x -= int_dx
            last_out_x = fx

            frac_y += fy - last_out_y
            int_dy = int(frac_y)
            frac_y -= int_dy
            last_out_y = fy

            if int_dx != 0:
                ui.write(evdev.ecodes.EV_REL, evdev.ecodes.REL_X, int_dx)
            if int_dy != 0:
                ui.write(evdev.ecodes.EV_REL, evdev.ecodes.REL_Y, int_dy)
