import logging
import math
import random
import threading
import time

import numpy as np

logger = logging.getLogger(__name__)

TARGET_COUNT = 12
TARGET_RADIUS = 25
WINDOW_W, WINDOW_H = 900, 600
BG_COLOR = (20, 20, 30)
TARGET_COLOR = (80, 200, 120)
TARGET_HIT_COLOR = (60, 100, 60)
TARGET_ACTIVE_COLOR = (255, 255, 255)
TRAIL_COLOR = (180, 80, 80)
TEXT_COLOR = (200, 200, 200)
RESULT_COLOR = (100, 220, 150)


class TrainingGame:
    """
    Pygame window showing circular targets for the user to click.
    Records raw cursor positions from the PositionBuffer (not pygame's mouse,
    which is already filtered) for honest tremor measurement.
    After all targets are clicked, runs FFT analysis and shows results.
    """

    def __init__(self, position_buffer, result_callback):
        self._buf = position_buffer
        self._callback = result_callback

    def run(self):
        try:
            import pygame
        except ImportError:
            logger.error("pygame not installed — training game unavailable")
            return

        pygame.init()
        screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        pygame.display.set_caption("Steady — Tremor Calibration")
        clock = pygame.time.Clock()
        font = pygame.font.SysFont('sans', 22)
        font_small = pygame.font.SysFont('sans', 16)

        targets = self._generate_targets()
        current = 0
        session_start = time.monotonic()
        trail_points = []
        running = True

        while running and current < len(targets):
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    break
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False
                    break
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = event.pos
                    tx, ty = targets[current]
                    if math.hypot(mx - tx, my - ty) <= TARGET_RADIUS * 2:
                        current += 1

            mx, my = pygame.mouse.get_pos()
            trail_points.append((mx, my))
            if len(trail_points) > 150:
                trail_points.pop(0)

            screen.fill(BG_COLOR)

            # Draw completed targets (dim)
            for i in range(current):
                tx, ty = targets[i]
                pygame.draw.circle(screen, TARGET_HIT_COLOR, (tx, ty), TARGET_RADIUS)

            # Draw remaining targets (faint)
            for i in range(current + 1, len(targets)):
                tx, ty = targets[i]
                pygame.draw.circle(screen, TARGET_COLOR, (tx, ty),
                                   TARGET_RADIUS, 1)

            # Draw current target (bright, pulsing ring)
            if current < len(targets):
                tx, ty = targets[current]
                pygame.draw.circle(screen, TARGET_COLOR, (tx, ty), TARGET_RADIUS, 2)
                t_pulse = int(abs(math.sin(time.monotonic() * 4)) * 6)
                pygame.draw.circle(screen, TARGET_ACTIVE_COLOR, (tx, ty),
                                   TARGET_RADIUS + 6 + t_pulse, 1)

            # Draw cursor trail
            if len(trail_points) > 1:
                pygame.draw.lines(screen, TRAIL_COLOR, False, trail_points, 1)

            label = font.render(
                f"Target {current + 1} of {len(targets)}  —  click the circle",
                True, TEXT_COLOR)
            screen.blit(label, (20, 16))

            hint = font_small.render("ESC to cancel", True, (100, 100, 100))
            screen.blit(hint, (WINDOW_W - hint.get_width() - 16, 16))

            pygame.display.flip()
            clock.tick(60)

        if running and current == len(targets):
            self._analyze_and_report(pygame, session_start)

        pygame.quit()

    def _generate_targets(self):
        margin = 70
        targets = []
        attempts = 0
        while len(targets) < TARGET_COUNT and attempts < 1000:
            attempts += 1
            x = random.randint(margin, WINDOW_W - margin)
            y = random.randint(margin + 50, WINDOW_H - margin)
            if all(math.hypot(x - tx, y - ty) > 120 for tx, ty in targets):
                targets.append((x, y))
        return targets

    def _analyze_and_report(self, pygame, session_start: float):
        session_end = time.monotonic()
        duration = session_end - session_start

        snap = self._buf.snapshot() if self._buf is not None else None
        freq, amplitude, recommended_alpha = 8.0, 0.0, 0.3

        if snap is not None and snap.size >= 64:
            mask = (snap['t'] >= session_start) & (snap['t'] <= session_end)
            segment = snap[mask]
            if segment.size >= 64:
                signal = segment['raw_x'].astype(np.float64)
                times = segment['t']
                sample_rate = (len(times) - 1) / (times[-1] - times[0]) \
                              if len(times) >= 2 else 60.0
                freq, amplitude, recommended_alpha = \
                    self._fft_analysis(signal, sample_rate)

        self._show_results(pygame, freq, amplitude, recommended_alpha, duration)

        if self._callback:
            self._callback({
                'freq_hz': freq,
                'amplitude': amplitude,
                'recommended_alpha': recommended_alpha,
            })

    def _fft_analysis(self, signal: np.ndarray,
                      sample_rate: float) -> tuple:
        N = len(signal)
        sig = signal - signal.mean()
        window = np.hanning(N)
        spectrum = np.fft.rfft(sig * window)
        magnitudes = np.abs(spectrum) * 2.0 / N
        freqs = np.fft.rfftfreq(N, d=1.0 / sample_rate)

        band_mask = (freqs >= 1.0) & (freqs <= 20.0)
        if not band_mask.any():
            return 8.0, 0.0, 0.3

        band_mags = magnitudes[band_mask]
        band_freqs = freqs[band_mask]
        peak_idx = int(np.argmax(band_mags))
        dominant_freq = float(band_freqs[peak_idx])
        amplitude = float(band_mags[peak_idx])
        recommended_alpha = float(np.clip(0.6 - dominant_freq * 0.03, 0.15, 0.55))
        return dominant_freq, amplitude, recommended_alpha

    def _show_results(self, pygame, freq: float, amplitude: float,
                      alpha: float, duration: float):
        screen = pygame.display.get_surface()
        font_large = pygame.font.SysFont('sans', 36)
        font_med = pygame.font.SysFont('sans', 24)
        font_small = pygame.font.SysFont('sans', 18)

        lines = [
            ("Tremor Analysis Complete", font_large, RESULT_COLOR),
            ("", font_med, TEXT_COLOR),
            (f"Dominant tremor frequency:  {freq:.1f} Hz", font_med, TEXT_COLOR),
            (f"Tremor amplitude:           {amplitude:.1f} px", font_med, TEXT_COLOR),
            (f"Recommended smoothing:      α = {alpha:.2f}", font_med, TEXT_COLOR),
            ("", font_med, TEXT_COLOR),
            ("Filter updated automatically.", font_small, RESULT_COLOR),
            ("Press any key or wait 6 seconds to close.", font_small, (130, 130, 130)),
        ]

        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline:
            for event in pygame.event.get():
                if event.type in (pygame.QUIT, pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                    return
            screen.fill(BG_COLOR)
            y = 80
            for text, font, color in lines:
                if text:
                    surf = font.render(text, True, color)
                    screen.blit(surf, (WINDOW_W // 2 - surf.get_width() // 2, y))
                y += font.size("A")[1] + 8
            pygame.display.flip()


def launch_training_game(position_buffer, result_callback):
    """Spawn the training game in its own daemon thread (safe from tray callbacks)."""
    def _run():
        game = TrainingGame(position_buffer, result_callback)
        game.run()

    t = threading.Thread(target=_run, name='training-game', daemon=True)
    t.start()
