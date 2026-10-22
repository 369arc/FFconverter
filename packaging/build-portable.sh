#!/bin/sh
# Build a portable FFConverter tarball with vendored Python dependencies.
#
# Usage:
#   packaging/build-portable.sh [--arch x86_64|arm64] [--with-ffmpeg DIR]
#                               [--output DIR]
#
# If --with-ffmpeg is given, DIR must contain statically linked (or otherwise
# self-contained) ffmpeg and ffprobe binaries. Without it the tarball uses the
# system FFmpeg, which is the only portable choice on most distributions.

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ARCH=x86_64
FFMPEG_DIR=
OUTPUT_DIR="$ROOT/dist"
VERSION=$(sed -n 's/^__version__ = "\([^"]*\)"/\1/p' "$ROOT/ffc.py" | head -n1)

while [ $# -gt 0 ]; do
    case "$1" in
        --arch) ARCH=$2; shift 2 ;;
        --with-ffmpeg) FFMPEG_DIR=$2; shift 2 ;;
        --output) OUTPUT_DIR=$2; shift 2 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

case "$ARCH" in
    x86_64|amd64) ARCH=x86_64 ;;
    arm64|aarch64) ARCH=arm64 ;;
    *) echo "unsupported arch: $ARCH" >&2; exit 2 ;;
esac

[ -n "$VERSION" ] || { echo "cannot read version from ffc.py" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "python3 is required" >&2; exit 1; }

STAGE="$ROOT/build/portable-$ARCH/FFConverter"
rm -rf "$ROOT/build/portable-$ARCH"
mkdir -p "$STAGE" "$OUTPUT_DIR"

cp "$ROOT/ffc.py" "$ROOT/run.sh" "$ROOT/LICENSE" "$ROOT/ffconverter.png" \
   "$ROOT/THIRD_PARTY_NOTICES.md" "$STAGE/"
cp "$ROOT/packaging/install-desktop.sh" "$STAGE/"
chmod 755 "$STAGE/install-desktop.sh"
mkdir -p "$STAGE/resources"
cp -a "$ROOT/resources/." "$STAGE/resources/"

mkdir -p "$STAGE/usr/share/applications"
mkdir -p "$STAGE/usr/share/icons/hicolor/256x256/apps"
cp "$ROOT/usr/share/applications/ffconverter.desktop" "$STAGE/usr/share/applications/"
cp "$ROOT/usr/share/icons/hicolor/256x256/ffconverter.png" \
   "$STAGE/usr/share/icons/hicolor/256x256/apps/"

python3 "$ROOT/packaging/vendor.py" "$STAGE/vendor" >/dev/null

if [ -n "$FFMPEG_DIR" ]; then
    mkdir -p "$STAGE/usr/bin"
    for binary in ffmpeg ffprobe; do
        [ -x "$FFMPEG_DIR/$binary" ] || {
            echo "missing executable: $FFMPEG_DIR/$binary" >&2
            exit 1
        }
        cp "$FFMPEG_DIR/$binary" "$STAGE/usr/bin/$binary"
        chmod 755 "$STAGE/usr/bin/$binary"
    done
fi

chmod 755 "$STAGE/run.sh"

ARCHIVE="$OUTPUT_DIR/FFConverter-portable-$ARCH.tar.xz"
tar -C "$ROOT/build/portable-$ARCH" -cJf "$ARCHIVE" FFConverter

(
    cd "$OUTPUT_DIR"
    sha256sum "$(basename "$ARCHIVE")" > "$(basename "$ARCHIVE").sha256"
)

echo "built $ARCHIVE"
du -h "$ARCHIVE"
