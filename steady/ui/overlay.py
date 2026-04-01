import logging
import os
import threading

import numpy as np

logger = logging.getLogger(__name__)

OVERLAY_W = 300
OVERLAY_H = 300
FPS = 30
TRAIL_SECONDS = 2.0
RAW_COLOR = (220, 60, 60)
FILT_COLOR = (60, 200, 80)
PANEL_COLOR = (10, 10, 10, 160)


class OverlayWindow:
    """
    Always-on-top, click-through floating window showing the last 2 seconds
    of raw (red) vs filtered (green) cursor trails.

    On X11: made always-on-top and click-through via python-xlib.
    On Wayland: window renders but cannot be made click-through; a warning
                is logged and the window is skipped entirely.

    Controlled by state.overlay_visible; creates/destroys the pygame window
    each time the toggle changes.
    """

    def __init__(self, state, position_buffer):
        self._state = state
        self._buf = position_buffer
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name='overlay', daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=3.0)

    # ------------------------------------------------------------------

    def _is_wayland(self) -> bool:
        return bool(os.environ.get('WAYLAND_DISPLAY'))

    def _run(self):
        if self._is_wayland():
            logger.info("Wayland session — overlay unavailable (no click-through support)")
            while not self._stop.is_set():
                self._state.overlay_changed.wait(timeout=1.0)
                self._state.overlay_changed.clear()
            return

        while not self._stop.is_set():
            if self._state.overlay_visible:
                self._run_pygame_loop()
            self._state.overlay_changed.wait(timeout=0.5)
            self._state.overlay_changed.clear()

    def _run_pygame_loop(self):
        try:
            import pygame
        except ImportError:
            logger.error("pygame not installed — overlay disabled")
            return

        os.environ.setdefault('SDL_VIDEO_WINDOW_POS', '20,50')
        pygame.init()
        screen = pygame.display.set_mode(
            (OVERLAY_W, OVERLAY_H),
            pygame.NOFRAME | pygame.SRCALPHA,
        )
        pygame.display.set_caption('Steady Overlay')
        self._setup_x11(pygame)

        clock = pygame.time.Clock()
        font = pygame.font.SysFont('monospace', 11)

        while not self._stop.is_set() and self._state.overlay_visible:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._state.overlay_visible = False

            snap = self._buf.last_seconds(TRAIL_SECONDS)
            self._draw(screen, snap, font, pygame)
            pygame.display.flip()
            clock.tick(FPS)

        pygame.quit()

    def _draw(self, screen, snap, font, pygame):
        screen.fill((0, 0, 0, 0))

        panel = pygame.Surface((OVERLAY_W, OVERLAY_H), pygame.SRCALPHA)
        panel.fill(PANEL_COLOR)
        screen.blit(panel, (0, 0))

        if snap.size < 2:
            lbl = font.render("Waiting for data...", True, (150, 150, 150))
            screen.blit(lbl, (10, 10))
            self._draw_legend(screen, font, pygame)
            return

        all_x = np.concatenate([snap['raw_x'], snap['filt_x']])
        all_y = np.concatenate([snap['raw_y'], snap['filt_y']])
        min_x, max_x = float(all_x.min()), float(all_x.max())
        min_y, max_y = float(all_y.min()), float(all_y.max())
        span_x = max(max_x - min_x, 1.0)
        span_y = max(max_y - min_y, 1.0)

        pad = 20
        scale = min((OVERLAY_W - 2 * pad) / span_x,
                    (OVERLAY_H - 2 * pad) / span_y)

        def to_screen(xs, ys):
            sx = (np.asarray(xs, dtype=np.float32) - min_x) * scale + pad
            sy = (np.asarray(ys, dtype=np.float32) - min_y) * scale + pad
            return list(zip(sx.astype(int).tolist(), sy.astype(int).tolist()))

        raw_pts = to_screen(snap['raw_x'], snap['raw_y'])
        filt_pts = to_screen(snap['filt_x'], snap['filt_y'])

        if len(raw_pts) >= 2:
            pygame.draw.lines(screen, RAW_COLOR, False, raw_pts, 2)
        if len(filt_pts) >= 2:
            pygame.draw.lines(screen, FILT_COLOR, False, filt_pts, 2)

        # Draw endpoints
        if raw_pts:
            pygame.draw.circle(screen, RAW_COLOR, raw_pts[-1], 3)
        if filt_pts:
            pygame.draw.circle(screen, FILT_COLOR, filt_pts[-1], 3)

        self._draw_legend(screen, font, pygame)

    def _draw_legend(self, screen, font, pygame):
        y = OVERLAY_H - 28
        pygame.draw.line(screen, RAW_COLOR, (8, y + 5), (24, y + 5), 2)
        lbl = font.render("raw", True, RAW_COLOR)
        screen.blit(lbl, (28, y))

        pygame.draw.line(screen, FILT_COLOR, (72, y + 5), (88, y + 5), 2)
        lbl2 = font.render("filtered", True, FILT_COLOR)
        screen.blit(lbl2, (92, y))

    def _setup_x11(self, pygame):
        """Make window always-on-top and click-through via python-xlib."""
        try:
            from Xlib import display as Xdisplay, X
            from Xlib.ext import shape

            wm_info = pygame.display.get_wm_info()
            xwin_id = wm_info.get('window')
            if not xwin_id:
                return

            xdisplay = Xdisplay.Display()
            xroot = xdisplay.screen().root
            xwin = xdisplay.create_resource_object('window', xwin_id)

            # Always-on-top
            _NET_WM_STATE = xdisplay.intern_atom('_NET_WM_STATE')
            _NET_WM_STATE_ABOVE = xdisplay.intern_atom('_NET_WM_STATE_ABOVE')
            from Xlib.protocol import event as Xevent
            xroot.send_event(
                Xevent.ClientMessage(
                    window=xwin,
                    client_type=_NET_WM_STATE,
                    data=(32, [1, _NET_WM_STATE_ABOVE, 0, 1, 0]),
                ),
                event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask,
            )

            # Click-through: empty input shape region
            if xdisplay.has_extension('SHAPE'):
                xwin.shape_select_input(0)
                # Combine with an empty set of rectangles for ShapeInput
                xwin.shape_combine_region(
                    xdisplay.create_resource_object('region', 0),
                    shape.ShapeInput, 0, 0,
                )
            xdisplay.sync()
            logger.debug("X11 overlay: always-on-top + click-through set")
        except Exception as exc:
            logger.debug("X11 overlay setup failed (non-fatal): %s", exc)
