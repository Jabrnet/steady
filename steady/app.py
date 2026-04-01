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
    Thread-safe shared state between the input hook and the tray UI.

    The 'changed' event is set whenever enabled or profile_name changes.
    The hook thread checks this event and rebuilds its filter accordingly.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._enabled = True
        self._profile_name = 'Essential Tremor'
        self.changed = threading.Event()

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


def main():
    state = SteadyState()
    hook = InputHook(state)
    hook.start()
    logger.info("Steady input hook started")

    def on_quit():
        logger.info("Shutting down")
        hook.stop()

    def _signal_handler(sig, frame):
        on_quit()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    # build_tray returns a pystray Icon; .run() blocks the main thread
    tray = build_tray(state, on_quit)
    logger.info("Starting system tray icon")
    tray.run()


if __name__ == '__main__':
    main()
