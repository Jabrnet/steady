import logging
import signal
import sys
import threading

from steady.input.hook import InputHook
from steady.tray.menu import build_tray

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)s %(levelname)s %(message)s',
)

logger = logging.getLogger(__name__)


class SteadyState:
    """
    Thread-safe shared state between the input hook, tray UI, overlay, and ML adapter.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._enabled = True
        self._profile_name = 'Essential Tremor'
        self.changed = threading.Event()

        # Shared position buffer — set by main() before any thread starts
        self.position_buffer = None

        # Overlay visibility toggle
        self._overlay_visible = False
        self.overlay_changed = threading.Event()

        # Training result callback — set by main()
        self.on_training_complete = None

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        with self._lock:
            self._enabled = value
        self.changed.set()

    @property
    def profile_name(self) -> str:
        with self._lock:
            return self._profile_name

    @profile_name.setter
    def profile_name(self, value: str):
        with self._lock:
            self._profile_name = value
        self.changed.set()

    @property
    def overlay_visible(self) -> bool:
        with self._lock:
            return self._overlay_visible

    @overlay_visible.setter
    def overlay_visible(self, value: bool):
        with self._lock:
            self._overlay_visible = value
        self.overlay_changed.set()


def main():
    from steady.core.ring_buffer import PositionBuffer
    from steady.core.ml_adapter import MLAdapter
    from steady.ui.overlay import OverlayWindow

    state = SteadyState()

    buf = PositionBuffer(capacity=1800)
    state.position_buffer = buf

    hook = InputHook(state)
    adapter = MLAdapter(state, buf)

    hook.start()
    adapter.start()
    logger.info("Steady input hook and ML adapter started")

    overlay = OverlayWindow(state, buf)
    overlay.start()

    def on_training_complete(result: dict):
        adapter.apply_training_result(result)

    state.on_training_complete = on_training_complete

    def on_quit():
        logger.info("Shutting down")
        overlay.stop()
        adapter.stop()
        hook.stop()

    def _signal_handler(sig, frame):
        on_quit()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    tray = build_tray(state, on_quit)
    logger.info("Starting system tray icon")
    tray.run()


if __name__ == '__main__':
    main()
