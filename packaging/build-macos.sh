#!/bin/bash
# Build FFConverter for macOS as a .dmg.
#
# Produces dist/FFConverter-<version>-macos-<arch>.dmg
#
# Requirements:
#   - macOS with python3.12 including tkinter (python.org build or Homebrew
#     python@3.12 + python-tk@3.12)
#   - curl and unzip
#
# FFmpeg/FFprobe are static macOS builds from ffmpeg.martin-riedl.de (pinned
# below, with SHA256). The app is ad-hoc signed, not notarized; see
# packaging/README-macos.txt.

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

for command in curl unzip hdiutil codesign; do
    command -v "$command" >/dev/null 2>&1 || {
        echo "missing command: $command" >&2
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

echo "==> Downloading static FFmpeg/FFprobe (9.0.2)"
if [ "$ARCH" = "arm64" ]; then
    FFMPEG_BASE="https://ffmpeg.martin-riedl.de/download/macos/arm64/1789931890_9.0.2"
    FFMPEG_SHA="c8ed4c4e6978a03c485edbfe4e0a5dc2380f8a30bba5150531b31b094492d924"
    FFPROBE_SHA="fcbe839537485eaee7a7a8bc5cbc0f90d53617e80943e8a5b2e31cb851197ea6"
else
    FFMPEG_BASE="https://ffmpeg.martin-riedl.de/download/macos/amd64/1789931006_9.0.2"
    FFMPEG_SHA="7c6b4125b191cbf773832dc51f424cf2b6bb7da43007d1e066f95909e47cacd4"
    FFPROBE_SHA="2322438ed2f6319a691291b247d09c69dcaa3a982460d1f269a7e1af335cfdfd"
fi
FFMPEG_CACHE="$BUILD/ffmpeg-download"
mkdir -p "$FFMPEG_CACHE"
curl -fL --retry 3 -o "$FFMPEG_CACHE/ffmpeg.zip" "$FFMPEG_BASE/ffmpeg.zip"
curl -fL --retry 3 -o "$FFMPEG_CACHE/ffprobe.zip" "$FFMPEG_BASE/ffprobe.zip"
echo "$FFMPEG_SHA  $FFMPEG_CACHE/ffmpeg.zip" | shasum -a 256 -c -
echo "$FFPROBE_SHA  $FFMPEG_CACHE/ffprobe.zip" | shasum -a 256 -c -
unzip -o "$FFMPEG_CACHE/ffmpeg.zip" -d "$FFMPEG_CACHE/ffmpeg" >/dev/null
unzip -o "$FFMPEG_CACHE/ffprobe.zip" -d "$FFMPEG_CACHE/ffprobe" >/dev/null
cp "$FFMPEG_CACHE/ffmpeg/ffmpeg" "$FRAMEWORKS/ffmpeg"
cp "$FFMPEG_CACHE/ffprobe/ffprobe" "$FRAMEWORKS/ffprobe"
chmod 755 "$FRAMEWORKS/ffmpeg" "$FRAMEWORKS/ffprobe"

cp "$ROOT/LICENSE" "$RESOURCES/LICENSE"
cp "$ROOT/LICENSE" "$RESOURCES/FFmpeg-LICENSE.txt"
cp "$ROOT/THIRD_PARTY_NOTICES.md" "$RESOURCES/THIRD_PARTY_NOTICES.md"
cp "$ROOT/packaging/README-macos.txt" "$RESOURCES/README-macos.txt"

"$FRAMEWORKS/ffmpeg" -version > "$RESOURCES/FFMPEG-BUILD.txt"
{
    echo "Source: $FFMPEG_BASE"
    echo "Builds: https://ffmpeg.martin-riedl.de/"
    echo "FFmpeg source: https://github.com/FFmpeg/FFmpeg"
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
