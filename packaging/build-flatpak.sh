#!/bin/sh
# Build the Flatpak bundle from com.ffconverter.FFConverter.yml.
#
# Requires flatpak-builder, plus the org.freedesktop.Sdk 25.08 runtime:
#   flatpak install --user flathub org.freedesktop.Sdk/x86_64/25.08
#
# Usage:
#   packaging/build-flatpak.sh [--output DIR]

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
OUTPUT_DIR=${OUTPUT_DIR:-"$ROOT/dist"}
VERSION=$(sed -n 's/^__version__ = "\([^"]*\)"/\1/p' "$ROOT/ffc.py" | head -n1)
ARCH=$(uname -m)
case "$ARCH" in
    x86_64|amd64) ARCH=x86_64 ;;
    aarch64|arm64) ARCH=aarch64 ;;
    *) echo "unsupported architecture: $ARCH" >&2; exit 1 ;;
esac

while [ $# -gt 0 ]; do
    case "$1" in
        --output) OUTPUT_DIR=$2; shift 2 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

[ -n "$VERSION" ] || { echo "cannot read version from ffc.py" >&2; exit 1; }
command -v flatpak-builder >/dev/null 2>&1 || {
    echo "flatpak-builder is required (install flatpak-builder)" >&2
    exit 1
}
if ! flatpak list --runtime --columns=ref 2>/dev/null | grep -q "org.freedesktop.Sdk/${ARCH}/25.08"; then
    echo "Install the SDK first: flatpak install --user flathub org.freedesktop.Sdk/${ARCH}/25.08" >&2
    exit 1
fi

mkdir -p "$OUTPUT_DIR"
REPO="$ROOT/build/flatpak-repo"
BUILD="$ROOT/build/flatpak-build"
rm -rf "$BUILD" "$REPO"

flatpak-builder --user --disable-rofiles-fuse --force-clean \
    --repo="$REPO" "$BUILD" "$ROOT/com.ffconverter.FFConverter.yml"

BUNDLE="$OUTPUT_DIR/FFConverter-${VERSION}-${ARCH}.flatpak"
flatpak build-bundle \
    --runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo \
    "$REPO" "$BUNDLE" com.ffconverter.FFConverter

(
    cd "$OUTPUT_DIR"
    sha256sum "$(basename "$BUNDLE")" > "$(basename "$BUNDLE").sha256"
)

echo "built $BUNDLE"
ls -lh "$BUNDLE"
