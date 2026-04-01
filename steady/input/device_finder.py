import logging
import evdev

logger = logging.getLogger(__name__)


def find_mouse_devices() -> list:
    """
    Return all /dev/input/eventN devices that look like a physical mouse.

    Criteria (all must pass):
      - Has EV_REL with REL_X and REL_Y
      - Has EV_KEY with BTN_LEFT
      - Not a touchpad (has EV_ABS but no REL_WHEEL)
      - Not our own virtual device (name contains 'steady')

    Sorted so devices with 'mouse' in name come first.
    """
    candidates = []
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
        except (PermissionError, OSError):
            continue

        # Skip our own virtual output device
        if 'steady' in dev.name.lower():
            dev.close()
            continue

        caps = dev.capabilities()
        rel_events = caps.get(evdev.ecodes.EV_REL, [])
        key_events = caps.get(evdev.ecodes.EV_KEY, [])
        abs_events = caps.get(evdev.ecodes.EV_ABS, [])

        if evdev.ecodes.REL_X not in rel_events:
            dev.close()
            continue
        if evdev.ecodes.REL_Y not in rel_events:
            dev.close()
            continue
        if evdev.ecodes.BTN_LEFT not in key_events:
            dev.close()
            continue

        # Reject touchpads: have ABS axes but no scroll wheel
        has_abs = len(abs_events) > 0
        has_wheel = evdev.ecodes.REL_WHEEL in rel_events
        if has_abs and not has_wheel:
            dev.close()
            continue

        candidates.append(dev)

    candidates.sort(key=lambda d: 0 if 'mouse' in d.name.lower() else 1)
    return candidates


def find_primary_mouse():
    """Return the best mouse candidate, or None if none found."""
    devices = find_mouse_devices()
    # Close extras we won't use
    for dev in devices[1:]:
        dev.close()
    return devices[0] if devices else None
