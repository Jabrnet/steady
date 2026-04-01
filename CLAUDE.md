# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Set up (Arch Linux — venv required due to externally-managed Python)
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run all tests
pytest steady/tests

# Run a single test
pytest steady/tests/test_filter.py::TestTremorFilter::test_initial_profile_creation

# Run the app (Arch / AppIndicator tray)
PYSTRAY_BACKEND=appindicator steady-tray

# One-time permissions setup (required for /dev/uinput and /dev/input/ access)
sudo bash install/install-permissions.sh   # adds user to 'input' group, installs udev rules
sudo modprobe uinput                        # load kernel module immediately without reboot
```

## Architecture

Steady is a Linux mouse-tremor filter. It intercepts the physical mouse at the kernel input layer (`evdev` exclusive grab), applies filtering, and re-emits events via a `uinput` virtual mouse — so it works identically on X11 and Wayland without display-server-specific code.

### Threading model

| Thread | Owner | Role |
|--------|-------|------|
| Main | `pystray` | Runs the tray icon event loop (blocks) |
| `input-hook` | `InputHook` | Tight evdev read loop → filter → uinput write |
| `ml-adapter` | `MLAdapter` | FFT analysis every 5s, updates filter params |
| `atspi-poller` | `ATSPIPoller` | Polls AT-SPI every 200ms for clickable targets |
| `overlay` | `OverlayWindow` | pygame trail window at 30fps |
| `training-game` | spawned on demand | pygame calibration game |

### Shared state

`SteadyState` (`app.py`) is the single shared object passed to all components. It uses a `threading.Lock` for `enabled` and `profile_name`, plus `threading.Event`s (`changed`, `overlay_changed`) to signal threads without polling. `position_buffer` (`PositionBuffer`) is the ring buffer all threads read/write for cursor data.

### Data flow

```
Physical mouse (evdev grab)
  → abs_x/abs_y accumulator (hook thread)
  → TremorFilter.filter_position()          # exponential smoothing
  → apply_gravity()                          # AT-SPI pull toward UI elements
  → PositionBuffer.push()                   # (raw, filtered) for ML + overlay
  → uinput virtual mouse                    # what the OS sees
```

### Key design details

- **Filter algorithm**: exponential smoothing `x = (1-α)*x + α*raw` where α (`smoothing_factor`) is 0.10–0.60. Y-axis uses `α * 1.5`. ML adapter adjusts α based on FFT of the correction signal (`raw - filtered`).
- **Sub-pixel accumulation**: `frac_x/frac_y` in `hook.py` prevent cursor drift when float deltas are truncated to int for uinput.
- **Filter rebuild**: when `state.changed` fires (profile switch or enable toggle), the hook reconstructs `TremorFilter` but pre-seeds `x_state`/`y_state` with the current position to avoid cursor jumps.
- **Gravity formula**: quadratic falloff `pull = strength * (1 - dist/radius)²` applied to filtered position before uinput write. Requires `python-pyatspi` (Arch: `pacman -S python-pyatspi`); silently disabled if unavailable.
- **Overlay click-through**: `python-xlib` sets an empty `ShapeInput` region on X11. On Wayland the overlay thread exits immediately with a log warning.
- **`EV_SYN` must not be in `UINPUT_CAPABILITIES`** — the kernel rejects it with `EINVAL`.

### Profile system

`TremorFilter.PREDEFINED_PROFILES` defines three static profiles. `TremorProfile` stores `params` (mutable dict including `smoothing_factor`), and `learning_history` (list of param snapshots written by `update_params()`). Custom profiles persist to `~/.steady/profiles/<name>.json`.
