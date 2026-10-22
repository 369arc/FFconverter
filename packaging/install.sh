#!/bin/sh
# Install FFConverter for the current user (default: ~/.local) or a custom
# prefix. No root, no pip, no network access.
#
#   ./packaging/install.sh
#   ./packaging/install.sh --prefix /usr/local
#   ./packaging/install.sh --uninstall [--prefix ...]

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PREFIX=${PREFIX:-"$HOME/.local"}
UNINSTALL=0

while [ $# -gt 0 ]; do
    case "$1" in
        --prefix) PREFIX=$2; shift 2 ;;
        --uninstall) UNINSTALL=1; shift ;;
        --help|-h)
            sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

APP_DIR="$PREFIX/share/ffconverter"
BIN_DIR="$PREFIX/bin"
DESKTOP_DIR="$PREFIX/share/applications"
ICON_DIR="$PREFIX/share/icons/hicolor/256x256/apps"

if [ "$UNINSTALL" -eq 1 ]; then
    rm -f "$BIN_DIR/FFConverter" "$BIN_DIR/ffconverter"
    rm -f "$DESKTOP_DIR/ffconverter.desktop"
    rm -f "$ICON_DIR/ffconverter.png"
    rm -rf "$APP_DIR"
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
    fi
    echo "FFConverter removed from $PREFIX"
    exit 0
fi

command -v python3 >/dev/null 2>&1 || {
    echo "python3 is required" >&2
    exit 1
}

if ! python3 -c 'import tkinter' >/dev/null 2>&1; then
    cat >&2 <<'EOF'
Python Tk support is missing.
  Debian/Ubuntu: sudo apt install python3-tk
  Fedora:        sudo dnf install python3-tkinter
  Arch:          sudo pacman -S tk
EOF
    exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "Warning: FFmpeg is not installed; conversion will not work until it is." >&2
    echo "  Debian/Ubuntu: sudo apt install ffmpeg" >&2
    echo "  Fedora:        sudo dnf install ffmpeg" >&2
    echo "  Arch:          sudo pacman -S ffmpeg" >&2
fi

mkdir -p "$APP_DIR" "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR"

install -m 755 "$ROOT/ffc.py" "$APP_DIR/ffc.py"
install -m 755 "$ROOT/run.sh" "$APP_DIR/run.sh"
install -m 644 "$ROOT/LICENSE" "$APP_DIR/LICENSE"
install -m 644 "$ROOT/THIRD_PARTY_NOTICES.md" "$APP_DIR/THIRD_PARTY_NOTICES.md"
install -m 644 "$ROOT/ffconverter.png" "$APP_DIR/ffconverter.png"
cp -a "$ROOT/resources" "$APP_DIR/"
python3 "$ROOT/packaging/vendor.py" "$APP_DIR/vendor" >/dev/null

install -m 644 "$ROOT/usr/share/icons/hicolor/256x256/ffconverter.png" \
    "$ICON_DIR/ffconverter.png"

# Use absolute paths so the entry also works when ~/.local/bin is not on the
# graphical session's PATH.
sed -e "s|^Exec=.*|Exec=$BIN_DIR/FFConverter %F|" \
    -e "s|^TryExec=.*|TryExec=$BIN_DIR/FFConverter|" \
    -e "s|^Icon=.*|Icon=$ICON_DIR/ffconverter.png|" \
    "$ROOT/usr/share/applications/ffconverter.desktop" \
    > "$DESKTOP_DIR/ffconverter.desktop"

cat > "$BIN_DIR/FFConverter" <<EOF
#!/bin/sh
exec "$APP_DIR/run.sh" "\$@"
EOF
chmod 755 "$BIN_DIR/FFConverter"
ln -sf FFConverter "$BIN_DIR/ffconverter"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi

echo "FFConverter installed in $PREFIX"
echo "  launcher: $BIN_DIR/FFConverter"
echo "  menu entry: $DESKTOP_DIR/ffconverter.desktop"
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo "  note: add $BIN_DIR to PATH to run 'FFConverter' from a terminal" ;;
esac
