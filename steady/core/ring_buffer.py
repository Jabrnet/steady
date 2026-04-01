import threading
import time
from collections import deque

import numpy as np


class PositionBuffer:
    """
    Thread-safe ring buffer storing (timestamp, raw_x, raw_y, filt_x, filt_y).

    Write path (hook thread):  push() — O(1), brief lock.
    Read path (overlay/ML):    snapshot() / last_seconds() — returns numpy copy.
    """

    DTYPE = np.dtype([
        ('t',      np.float64),
        ('raw_x',  np.float32),
        ('raw_y',  np.float32),
        ('filt_x', np.float32),
        ('filt_y', np.float32),
    ])

    def __init__(self, capacity: int = 1800):
        self._buf = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def push(self, t: float, raw_x: float, raw_y: float,
             filt_x: float, filt_y: float) -> None:
        with self._lock:
            self._buf.append((t, raw_x, raw_y, filt_x, filt_y))

    def snapshot(self, max_samples: int = None) -> np.ndarray:
        """Return a structured numpy array copy of recent samples."""
        with self._lock:
            data = list(self._buf) if max_samples is None \
                   else list(self._buf)[-max_samples:]
        if not data:
            return np.array([], dtype=self.DTYPE)
        return np.array(data, dtype=self.DTYPE)

    def last_seconds(self, seconds: float) -> np.ndarray:
        """Return only samples within the last `seconds` window."""
        cutoff = time.monotonic() - seconds
        snap = self.snapshot()
        if snap.size == 0:
            return snap
        return snap[snap['t'] >= cutoff]
