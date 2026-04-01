#!/usr/bin/env bash
# Steady tremor filter - one-time permissions setup
# Run as root: sudo bash install-permissions.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RULES_SRC="$SCRIPT_DIR/99-steady.rules"
RULES_DEST="/etc/udev/rules.d/99-steady.rules"

if [[ $EUID -ne 0 ]]; then
    echo "Error: this script must be run as root."
    echo "Usage: sudo bash $0"
    exit 1
fi

# Determine the real user (not root) who ran sudo
TARGET_USER="${SUDO_USER:-$USER}"

echo "Installing udev rules..."
cp "$RULES_SRC" "$RULES_DEST"
chmod 644 "$RULES_DEST"

echo "Ensuring uinput kernel module loads at boot..."
echo "uinput" > /etc/modules-load.d/uinput.conf
modprobe uinput 2>/dev/null || true

echo "Adding $TARGET_USER to the 'input' group..."
usermod -aG input "$TARGET_USER"

echo "Reloading udev rules..."
udevadm control --reload-rules
udevadm trigger --subsystem-match=input

echo ""
echo "Done. IMPORTANT: you must log out and log back in for the group"
echo "membership to take effect, then run:  steady-tray"
