#!/usr/bin/env bash
# Steady - install desktop launcher
# Run from your steady directory: bash install/install-desktop.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
VENV_BIN="$PROJECT_DIR/.venv/bin/steady-tray"
ICONS_DIR="$HOME/.local/share/icons/hicolor/64x64/apps"
APPS_DIR="$HOME/.local/share/applications"

if [[ ! -f "$VENV_PYTHON" ]]; then
    echo "Error: virtualenv not found at $PROJECT_DIR/.venv"
    echo "Run: python -m venv .venv && source .venv/bin/activate && pip install -e '.[dev]'"
    exit 1
fi

# Ensure the editable install path is registered in the venv
PYTHON_VERSION=$("$VENV_PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "$PROJECT_DIR" > "$PROJECT_DIR/.venv/lib/python$PYTHON_VERSION/site-packages/steady-project.pth"

mkdir -p "$ICONS_DIR" "$APPS_DIR"

# Generate icon PNG using the installed Pillow + steady.tray.icon
ICON_PATH="$ICONS_DIR/steady.png"
PYTHONPATH="$PROJECT_DIR" "$VENV_PYTHON" -c "
from steady.tray.icon import make_icon
make_icon(True).save('$ICON_PATH')
"
echo "Icon saved to $ICON_PATH"

# Write .desktop file
DESKTOP_FILE="$APPS_DIR/steady.desktop"
cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Name=Steady
Comment=Tremor filter - stabilises mouse cursor
Exec=env PYSTRAY_BACKEND=appindicator PYTHONPATH=$PROJECT_DIR $VENV_BIN
Icon=$ICON_PATH
Type=Application
Terminal=false
Categories=Accessibility;Utility;
StartupNotify=false
EOF

chmod +x "$DESKTOP_FILE"
echo "App launcher installed: $DESKTOP_FILE"

# Copy to ~/Desktop if it exists
if [[ -d "$HOME/Desktop" ]]; then
    cp "$DESKTOP_FILE" "$HOME/Desktop/steady.desktop"
    chmod +x "$HOME/Desktop/steady.desktop"
    echo "Desktop shortcut created at ~/Desktop/steady.desktop"
fi

echo ""
echo "Done. Look for 'Steady' in your applications menu, or double-click the desktop icon."
