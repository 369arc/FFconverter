#!/bin/sh
# Build a self-contained x86_64 AppImage in an Ubuntu 22.04 container.
#
# The container is used deliberately: PyInstaller embeds the glibc/Python/Tk
# it is built against, and building on a new distribution would produce an
# AppImage that only works on equally new systems.
#
# Usage:
#   packaging/build-appimage.sh [--output DIR]
#
# Requires podman or docker. The AppImage bundles Python, Tk and the Python
# GUI dependencies; it still uses the system FFmpeg for conversions.

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
OUTPUT_DIR=${OUTPUT_DIR:-"$ROOT/dist"}
ENGINE=${CONTAINER_ENGINE:-}

while [ $# -gt 0 ]; do
    case "$1" in
        --output) OUTPUT_DIR=$2; shift 2 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

if [ -z "$ENGINE" ]; then
    if command -v podman >/dev/null 2>&1; then
        ENGINE=podman
    elif command -v docker >/dev/null 2>&1; then
        ENGINE=docker
    else
        echo "podman or docker is required to build the AppImage" >&2
        exit 1
    fi
fi

mkdir -p "$OUTPUT_DIR"

if [ "$ENGINE" = "podman" ]; then
    "$ENGINE" run --rm \
        -v "$ROOT:/src:ro,Z" \
        -v "$OUTPUT_DIR:/out:Z" \
        ubuntu:22.04 \
        bash /src/packaging/build-appimage-inner.sh
else
    "$ENGINE" run --rm \
        -v "$ROOT:/src:ro" \
        -v "$OUTPUT_DIR:/out" \
        -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
        ubuntu:22.04 \
        bash /src/packaging/build-appimage-inner.sh
fi

# The container runs as root; make the artifacts writable by the caller.
if [ "$(id -u)" -ne 0 ]; then
    find "$OUTPUT_DIR" -maxdepth 1 -user 0 \( -name '*.AppImage' -o -name '*.bin' -o -name '*.sha256' \) \
        -exec chown "$(id -u):$(id -g)" {} + 2>/dev/null || true
fi

echo "AppImage artifacts written to $OUTPUT_DIR"
ls -lh "$OUTPUT_DIR"/FFConverter-*-x86_64.AppImage "$OUTPUT_DIR"/FFConverter-*-x86_64.AppImage.sha256
