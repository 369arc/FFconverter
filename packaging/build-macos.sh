#!/bin/bash
# Build FFConverter for macOS as a .dmg.
#
# Produces dist/FFConverter-<version>-macos-<arch>.dmg
#
# Requirements (Homebrew):
#   brew install python@3.12 python-tk@3.12 ffmpeg dylibbundler
#
# Use PYTHON=/path/to/python3.12 if python3 is not the Homebrew Python.
# The app is ad-hoc signed, not notarized; see packaging/README-macos.txt.

set -euo pipefail

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
OUTPUT_DIR=${OUTPUT_DIR:-"$ROOT/dist"}
PYTHON=${PYTHON:-python3}
VERSION=$(sed -n 's/^__version__ = "\([^"]*\)"/\1/p' "$ROOT/ffc.py" | head -n1)

while [ $# -gt 0 ]; do
    case "$1" in
        --output) OUTPUT_DIR=$2; shift 2 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

[ -n "$VERSION" ] || { echo "cannot read version from ffc.py" >&2; exit 1; }
[ "$(uname -s)" = "Darwin" ] || {
    echo "build-macos.sh must run on macOS" >&2
    exit 1
}

ARCH=$(uname -m)
case "$ARCH" in
    arm64) ;;
    x86_64) ;;
    *) echo "unsupported architecture: $ARCH" >&2; exit 1 ;;
esac

for command in ffmpeg ffprobe dylibbundler hdiutil codesign; do
    command -v "$command" >/dev/null 2>&1 || {
        echo "missing command: $command" >&2
        echo "install with: brew install python@3.12 python-tk@3.12 ffmpeg dylibbundler" >&2
        exit 1
    }
done

if ! "$PYTHON" -c 'import tkinter' >/dev/null 2>&1; then
    echo "$PYTHON does not have tkinter. Install python-tk (Homebrew) and set PYTHON." >&2
    exit 1
fi

mkdir -p "$OUTPUT_DIR"
BUILD="$ROOT/build/macos"
rm -rf "$BUILD"
mkdir -p "$BUILD"

VENV="$BUILD/venv"
"$PYTHON" -m venv "$VENV"
PY="$VENV/bin/python"
"$PY" -m pip install --no-index --find-links "$ROOT/pip-wheels" \
    --disable-pip-version-check --no-compile \
    customtkinter==5.2.2 darkdetect==0.8.0 packaging==26.2 \
    send2trash==2.1.0 tkinterdnd2==0.4.3 >/dev/null
"$PY" -m pip install --disable-pip-version-check "pyinstaller==6.11.1" >/dev/null

DIST="$BUILD/dist"
WORK="$BUILD/work"
SPEC="$BUILD/spec"
mkdir -p "$DIST" "$WORK" "$SPEC"

echo "==> Building macOS .app"
"$PY" -m PyInstaller \
    --noconfirm --clean \
    --windowed \
    --name FFConverter \
    --osx-bundle-identifier com.ffconverter.FFConverter \
    --icon "$ROOT/resources/icon.icns" \
    --add-data "$ROOT/resources:resources" \
    --add-data "$ROOT/ffconverter.png:." \
    --collect-all customtkinter \
    --collect-all tkinterdnd2 \
    --distpath "$DIST" \
    --workpath "$WORK" \
    --specpath "$SPEC" \
    "$ROOT/ffc.py" >/dev/null

APP="$DIST/FFConverter.app"
[ -d "$APP" ] || { echo "PyInstaller did not create FFConverter.app" >&2; exit 1; }

FRAMEWORKS="$APP/Contents/Frameworks"
RESOURCES="$APP/Contents/Resources"
mkdir -p "$FRAMEWORKS" "$RESOURCES"

echo "==> Bundling FFmpeg and its dylibs"
cp "$(command -v ffmpeg)" "$FRAMEWORKS/ffmpeg"
cp "$(command -v ffprobe)" "$FRAMEWORKS/ffprobe"
chmod 755 "$FRAMEWORKS/ffmpeg" "$FRAMEWORKS/ffprobe"
# Homebrew binaries carry signatures that become invalid when dylib paths are
# rewritten; strip them before bundling and sign the whole app afterwards.
codesign --remove-signature "$FRAMEWORKS/ffmpeg" >/dev/null 2>&1 || true
codesign --remove-signature "$FRAMEWORKS/ffprobe" >/dev/null 2>&1 || true

dylibbundler -od -b \
    -x "$FRAMEWORKS/ffmpeg" \
    -x "$FRAMEWORKS/ffprobe" \
    -d "$FRAMEWORKS" \
    -p "@executable_path" >/dev/null

cp "$ROOT/LICENSE" "$RESOURCES/LICENSE"
cp "$ROOT/THIRD_PARTY_NOTICES.md" "$RESOURCES/THIRD_PARTY_NOTICES.md"
cp "$ROOT/packaging/README-macos.txt" "$RESOURCES/README-macos.txt"

FFMPEG_PREFIX=$(brew --prefix ffmpeg 2>/dev/null || true)
if [ -n "$FFMPEG_PREFIX" ]; then
    LICENSE_FILE=$(find "$FFMPEG_PREFIX" -maxdepth 4 -type f \
        \( -iname 'COPYING*' -o -iname 'LICENSE*' \) | head -n1)
    if [ -n "$LICENSE_FILE" ]; then
        cp "$LICENSE_FILE" "$RESOURCES/FFmpeg-LICENSE.txt"
    fi
fi
"$FRAMEWORKS/ffmpeg" -version > "$RESOURCES/FFMPEG-BUILD.txt"
{
    echo "Source: https://github.com/FFmpeg/FFmpeg"
    echo "Packaged by packaging/build-macos.sh from Homebrew ffmpeg."
} >> "$RESOURCES/FFMPEG-BUILD.txt"

echo "==> Signing (ad-hoc)"
codesign --force --deep --sign - "$APP"

echo "==> Smoke test"
"$APP/Contents/MacOS/FFConverter" --version
"$FRAMEWORKS/ffmpeg" -version >/dev/null

# The GUI smoke test needs a WindowServer session. Run it when available, but
# do not fail a build on headless CI.
if ! "$APP/Contents/MacOS/FFConverter" --smoke-test >/dev/null 2>&1; then
    echo "warning: GUI smoke test did not run in this session" >&2
fi

echo "==> Creating DMG"
DMG_STAGE="$BUILD/dmg"
mkdir -p "$DMG_STAGE"
cp -R "$APP" "$DMG_STAGE/"
ln -s /Applications "$DMG_STAGE/Applications"
cp "$ROOT/packaging/README-macos.txt" "$DMG_STAGE/README.txt"

DMG="$OUTPUT_DIR/FFConverter-$VERSION-macos-$ARCH.dmg"
rm -f "$DMG"
hdiutil create -volname "FFConverter" -srcfolder "$DMG_STAGE" \
    -ov -format UDZO "$DMG" >/dev/null
(
    cd "$OUTPUT_DIR"
    shasum -a 256 "$(basename "$DMG")" > "$(basename "$DMG").sha256"
)

echo "built $DMG"
ls -lh "$DMG"
