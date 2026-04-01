import logging
import math
import threading
from typing import List, Tuple

logger = logging.getLogger(__name__)

GRAVITY_RADIUS = 40       # px: cursor must be within this radius for any pull
GRAVITY_STRENGTH = 0.35   # max pull fraction (at center of target)

# AT-SPI roles considered clickable targets
_CLICKABLE_ROLES = frozenset([
    'PUSH_BUTTON', 'RADIO_BUTTON', 'CHECK_BOX', 'TOGGLE_BUTTON',
    'MENU_ITEM', 'CHECK_MENU_ITEM', 'RADIO_MENU_ITEM',
    'LINK', 'LIST_ITEM', 'TABLE_CELL', 'COMBO_BOX',
    'SPIN_BUTTON', 'SLIDER', 'TEXT',
])


class GravityTarget:
    __slots__ = ('cx', 'cy')

    def __init__(self, cx: float, cy: float):
        self.cx = cx
        self.cy = cy


class ATSPIPoller(threading.Thread):
    """
    Daemon thread that polls AT-SPI every 200ms and maintains a fresh list
    of on-screen clickable targets for the hook thread to read.

    Degrades gracefully: if pyatspi is not installed or raises (e.g. on
    Wayland without accessibility support), available=False and the thread
    never starts, so apply_gravity is never called.
    """

    POLL_INTERVAL = 0.2

    def __init__(self):
        super().__init__(name='atspi-poller', daemon=True)
        self._stop = threading.Event()
        self._targets: List[GravityTarget] = []
        self._lock = threading.Lock()
        self._available = False
        self._pyatspi = None

    def start_polling(self):
        self._try_import()
        if self._available:
            self.start()

    def _try_import(self):
        try:
            import pyatspi
            self._pyatspi = pyatspi
            self._available = True
            logger.info("AT-SPI available — cursor gravity enabled")
        except (ImportError, Exception):
            logger.info("pyatspi not available — gravity disabled")
            self._available = False

    def run(self):
        pyatspi = self._pyatspi
        while not self._stop.is_set():
            try:
                targets = self._collect_targets(pyatspi)
                with self._lock:
                    self._targets = targets
            except Exception as exc:
                logger.debug("AT-SPI poll error: %s", exc)
                with self._lock:
                    self._targets = []
            self._stop.wait(self.POLL_INTERVAL)

    def _collect_targets(self, pyatspi) -> List[GravityTarget]:
        targets = []
        try:
            desktop = pyatspi.Registry.getDesktop(0)
        except Exception:
            return targets

        for app in desktop:
            if app is None:
                continue
            self._walk(app, targets, depth=0, max_depth=6, pyatspi=pyatspi)
            if len(targets) > 200:
                break
        return targets

    def _walk(self, node, targets: list, depth: int, max_depth: int, pyatspi):
        if node is None or depth > max_depth:
            return
        try:
            role_name = node.getRoleName().replace(' ', '_').upper()
            if role_name in _CLICKABLE_ROLES:
                try:
                    ext = node.queryComponent().getExtents(pyatspi.XY_SCREEN)
                    if ext.width > 0 and ext.height > 0:
                        targets.append(GravityTarget(
                            cx=ext.x + ext.width / 2,
                            cy=ext.y + ext.height / 2,
                        ))
                except Exception:
                    pass
            for i in range(node.childCount):
                self._walk(node.getChildAtIndex(i), targets,
                           depth + 1, max_depth, pyatspi)
        except Exception:
            pass

    def get_targets(self) -> List[GravityTarget]:
        with self._lock:
            return self._targets

    def stop(self):
        self._stop.set()

    @property
    def available(self) -> bool:
        return self._available


def apply_gravity(
    fx: float, fy: float,
    targets: List[GravityTarget],
    radius: float = GRAVITY_RADIUS,
    strength: float = GRAVITY_STRENGTH,
) -> Tuple[float, float]:
    """
    Return a gravity-adjusted cursor position pulled toward the nearest
    clickable target within `radius` pixels.

    Uses quadratic falloff to avoid singularities and ensure smooth
    entry/exit at the boundary:
        pull = strength * (1 - dist/radius)²
        new_pos = pos + (target_center - pos) * pull

    At dist=0: pull=strength (full attraction)
    At dist=radius: pull=0 (boundary, no effect)
    """
    if not targets:
        return fx, fy

    best_dist = float('inf')
    best_target = None
    for t in targets:
        dx = t.cx - fx
        dy = t.cy - fy
        d = math.sqrt(dx * dx + dy * dy)
        if d < best_dist:
            best_dist = d
            best_target = t

    if best_dist >= radius or best_target is None:
        return fx, fy

    pull = strength * (1.0 - best_dist / radius) ** 2
    gx = fx + (best_target.cx - fx) * pull
    gy = fy + (best_target.cy - fy) * pull
    return gx, gy
