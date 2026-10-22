#!/bin/sh
# Add a menu entry for a portable FFConverter directory.
set -eu

APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ ! -f "$APP_DIR/usr/share/applications/ffconverter.desktop" ] \
   && [ -f "$APP_DIR/../usr/share/applications/ffconverter.desktop" ]; then
    APP_DIR=$(CDPATH= cd -- "$APP_DIR/.." && pwd)
fi
DATA_HOME=${XDG_DATA_HOME:-"$HOME/.local/share"}
DESKTOP_DIR="$DATA_HOME/applications"
TEMPLATE="$APP_DIR/usr/share/applications/ffconverter.desktop"

[ -f "$TEMPLATE" ] || {
    echo "missing desktop template: $TEMPLATE" >&2
    exit 1
}

mkdir -p "$DESKTOP_DIR"
sed -e "s|^Exec=.*|Exec=$APP_DIR/run.sh %F|" \
    -e "s|^TryExec=.*|TryExec=$APP_DIR/run.sh|" \
    -e "s|^Icon=.*|Icon=$APP_DIR/ffconverter.png|" \
    "$TEMPLATE" > "$DESKTOP_DIR/ffconverter.desktop"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi

echo "Menu entry installed: $DESKTOP_DIR/ffconverter.desktop"
