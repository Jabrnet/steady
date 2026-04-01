import logging
import threading

import numpy as np

logger = logging.getLogger(__name__)

ANALYSIS_INTERVAL = 5.0   # seconds between FFT cycles
WINDOW_SECONDS = 4.0      # seconds of buffer history to analyze
MIN_SAMPLES = 128         # skip analysis if fewer samples available
ADAPT_RATE = 0.15         # fraction of gap to close each cycle
ALPHA_MIN = 0.10
ALPHA_MAX = 0.60
FREQ_BAND = (1.0, 20.0)   # Hz: physiological tremor range


class MLAdapter:
    """
    Background daemon thread: every ANALYSIS_INTERVAL seconds, runs FFT on the
    correction signal (raw - filtered) from the PositionBuffer and nudges the
    live TremorFilter's smoothing_factor toward the optimal value.

    Parameter changes are deliberately gradual (ADAPT_RATE=0.15) so the user
    never feels a sudden jump in cursor behaviour.
    """

    def __init__(self, state, position_buffer):
        self._state = state
        self._buf = position_buffer
        self._stop = threading.Event()
        self._filter_ref = None
        self._filter_lock = threading.Lock()
        self._thread = threading.Thread(
            target=self._run, name='ml-adapter', daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=5.0)

    def set_filter(self, tremor_filter):
        """Called by InputHook whenever it creates/rebuilds the TremorFilter."""
        with self._filter_lock:
            self._filter_ref = tremor_filter

    def apply_training_result(self, result: dict):
        """Apply FFT results from the training game — larger step, still smooth."""
        alpha = result.get('recommended_alpha')
        if alpha is None:
            return
        with self._filter_lock:
            filt = self._filter_ref
        if filt is None:
            return
        current = filt.current_profile.params.get('smoothing_factor', 0.3)
        blended = current + 0.5 * (alpha - current)
        blended = float(np.clip(blended, ALPHA_MIN, ALPHA_MAX))
        filt.update_params({'smoothing_factor': blended})
        logger.info("Training result applied: alpha %.3f → %.3f (freq=%.1fHz)",
                    current, blended, result.get('freq_hz', 0))

    # ------------------------------------------------------------------

    def _run(self):
        while not self._stop.is_set():
            self._stop.wait(ANALYSIS_INTERVAL)
            if self._stop.is_set():
                break
            try:
                self._analyze_and_adapt()
            except Exception as exc:
                logger.debug("ML adapter cycle error: %s", exc)

    def _analyze_and_adapt(self):
        snap = self._buf.last_seconds(WINDOW_SECONDS)
        if snap.size < MIN_SAMPLES:
            return

        with self._filter_lock:
            filt = self._filter_ref
        if filt is None:
            return

        # Tremor signal = what the filter removed (raw - filtered)
        corr_x = (snap['raw_x'] - snap['filt_x']).astype(np.float64)
        corr_y = (snap['raw_y'] - snap['filt_y']).astype(np.float64)

        freq_x, amp_x, alpha_x = self._fft_suggest(corr_x, snap)
        freq_y, amp_y, alpha_y = self._fft_suggest(corr_y, snap)

        if amp_x >= amp_y:
            dominant_freq, recommended_alpha = freq_x, alpha_x
            dominant_amp = amp_x
        else:
            dominant_freq, recommended_alpha = freq_y, alpha_y
            dominant_amp = amp_y

        if recommended_alpha is None:
            return

        current = filt.current_profile.params.get('smoothing_factor', 0.3)
        new_alpha = current + ADAPT_RATE * (recommended_alpha - current)
        new_alpha = float(np.clip(new_alpha, ALPHA_MIN, ALPHA_MAX))

        if abs(new_alpha - current) > 0.001:
            filt.update_params({'smoothing_factor': new_alpha})
            logger.debug("ML adapt: %.1fHz amp=%.1fpx alpha %.3f→%.3f",
                         dominant_freq, dominant_amp, current, new_alpha)

    def _fft_suggest(self, signal: np.ndarray, snap) -> tuple:
        """Return (dominant_freq_hz, amplitude, recommended_alpha) or (0, 0, None)."""
        N = len(signal)
        if N < 32:
            return 0.0, 0.0, None

        dt_total = float(snap['t'][-1] - snap['t'][0])
        if dt_total <= 0:
            return 0.0, 0.0, None
        sample_rate = (N - 1) / dt_total

        sig = signal - signal.mean()
        window = np.hanning(N)
        spectrum = np.fft.rfft(sig * window)
        magnitudes = np.abs(spectrum) * 2.0 / N
        freqs = np.fft.rfftfreq(N, d=1.0 / sample_rate)

        band_mask = (freqs >= FREQ_BAND[0]) & (freqs <= FREQ_BAND[1])
        if not band_mask.any():
            return 0.0, 0.0, None

        band_mags = magnitudes[band_mask]
        band_freqs = freqs[band_mask]
        peak_idx = int(np.argmax(band_mags))
        freq = float(band_freqs[peak_idx])
        amp = float(band_mags[peak_idx])
        alpha = float(np.clip(0.6 - freq * 0.03, ALPHA_MIN, ALPHA_MAX))
        return freq, amp, alpha
