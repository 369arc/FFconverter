#!/bin/sh
# FFConverter launcher.
#
# Works both from a git checkout and from a portable tarball:
#   * a bundled ./vendor directory is used when present;
#   * otherwise the system Python packages are used;
#   * if neither is available, an offline virtualenv is built from ./wheels
#     or ./pip-wheels (the wheels are shipped with source/portable builds).

set -eu

APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

show_error() {
    message=$1
    printf 'FFConverter: %s\n' "$message" >&2
    if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
        if command -v zenity >/dev/null 2>&1; then
            zenity --error --title="FFConverter" --text="$message" >/dev/null 2>&1 || true
        elif command -v kdialog >/dev/null 2>&1; then
            kdialog --title "FFConverter" --error "$message" >/dev/null 2>&1 || true
        elif command -v xmessage >/dev/null 2>&1; then
            xmessage -center "$message" >/dev/null 2>&1 || true
        fi
    fi
}

if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
else
    show_error "Python 3 was not found. Install python3 and python3-tk (Debian/Ubuntu), python3-tkinter (Fedora) or tk (Arch), then run this script again."
    exit 1
fi

if ! "$PYTHON" -c 'import tkinter' >/dev/null 2>&1; then
    show_error "Python Tk support is missing. Debian/Ubuntu: sudo apt install python3-tk. Fedora: sudo dnf install python3-tkinter. Arch: sudo pacman -S tk."
    exit 1
fi

# A portable build ships its dependencies in ./vendor.
if [ -d "$APP_DIR/vendor" ]; then
    PYTHONPATH="$APP_DIR/vendor${PYTHONPATH:+:$PYTHONPATH}"
    export PYTHONPATH
fi

# Source checkouts can still fall back to the bundled wheels. This is
# deliberately offline (--no-index): installation must not need network access.
if ! "$PYTHON" -c 'import customtkinter' >/dev/null 2>&1; then
    WHEELS_DIR=
    if [ -d "$APP_DIR/wheels" ]; then
        WHEELS_DIR="$APP_DIR/wheels"
    elif [ -d "$APP_DIR/pip-wheels" ]; then
        WHEELS_DIR="$APP_DIR/pip-wheels"
    fi

    if [ -n "$WHEELS_DIR" ]; then
        CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/ffconverter"
        VENV_DIR="$CACHE_DIR/venv-$(printf '%s' "$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')")"
        if [ ! -x "$VENV_DIR/bin/python" ]; then
            if ! "$PYTHON" -m venv "$VENV_DIR" >/dev/null 2>&1; then
                show_error "The Python venv module is missing. Install python3-venv (Debian/Ubuntu) or use the packaged FFConverter build."
                exit 1
            fi
        fi
        if ! "$VENV_DIR/bin/python" -c 'import customtkinter' >/dev/null 2>&1; then
            if ! "$VENV_DIR/bin/python" -m pip install --no-index --find-links "$WHEELS_DIR" \
                --disable-pip-version-check --no-compile \
                customtkinter==5.2.2 darkdetect==0.8.0 packaging==26.2 \
                send2trash==2.1.0 tkinterdnd2==0.4.3 >/dev/null 2>&1; then
                show_error "The bundled Python wheels could not be installed. Reinstall FFConverter or install python3-pip and python3-venv."
                exit 1
            fi
        fi
        PYTHON="$VENV_DIR/bin/python"
    else
        show_error "The Python package 'customtkinter' is missing. Use the packaged build, or run: $PYTHON -m pip install --user customtkinter send2trash tkinterdnd2"
        exit 1
    fi
fi

# Prefer the bundled FFmpeg only when the system has none.
if [ -x "$APP_DIR/usr/bin/ffmpeg" ]; then
    if ! command -v ffmpeg >/dev/null 2>&1; then
        PATH="$APP_DIR/usr/bin:$PATH"
        export PATH
        [ -n "${FFCONVERTER_DEBUG:-}" ] && echo "Using bundled FFmpeg"
    fi
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
    # Do not abort here: the GUI can still browse files and shows a clear
    # in-app warning. This also keeps --version/--help working.
    if [ -n "${FFCONVERTER_DEBUG:-}" ]; then
        echo "FFmpeg not found; conversion will be disabled." >&2
    fi
fi

exec "$PYTHON" "$APP_DIR/ffc.py" "$@"
