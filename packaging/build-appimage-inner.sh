#!/bin/bash
# Runs inside the Ubuntu 22.04 container created by build-appimage.sh.
# Do not run this directly on the host unless it is an Ubuntu 22.04 system.

set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
export PIP_DISABLE_PIP_VERSION_CHECK=1
export PYTHONNOUSERSITE=1

ROOT=/src
OUT=/out
VERSION=$(sed -n 's/^__version__ = "\([^"]*\)"/\1/p' "$ROOT/ffc.py" | head -n1)
[ -n "$VERSION" ] || { echo "cannot read version from ffc.py" >&2; exit 1; }

apt-get update -qq
apt-get install -y -qq --no-install-recommends \
    python3 python3-venv python3-tk python3-pip python3-dev \
    ca-certificates curl file libfuse2 libxcursor1 xvfb binutils >/dev/null

python3 -m venv /tmp/venv
/tmp/venv/bin/pip install --no-index --find-links "$ROOT/pip-wheels" \
    customtkinter==5.2.2 darkdetect==0.8.0 packaging==26.2 \
    send2trash==2.1.0 tkinterdnd2==0.4.3 >/dev/null
# PyInstaller itself is a build tool, not a runtime dependency.
/tmp/venv/bin/pip install "pyinstaller==6.11.1" >/dev/null

rm -rf /tmp/pybuild /tmp/AppDir
mkdir -p /tmp/pybuild
cd /tmp/pybuild

/tmp/venv/bin/pyinstaller \
    --noconfirm --clean --onefile --name FFConverter \
    --add-data "$ROOT/resources:resources" \
    --add-data "$ROOT/ffconverter.png:." \
    --collect-all customtkinter \
    --collect-all tkinterdnd2 \
    "$ROOT/ffc.py"

# Smoke-test the frozen binary before packaging it.
./dist/FFConverter --version
xvfb-run -a timeout 6 ./dist/FFConverter --version

APPDIR=/tmp/AppDir
mkdir -p "$APPDIR/usr/bin" \
         "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/256x256/apps"

cp ./dist/FFConverter "$APPDIR/usr/bin/FFConverter"
chmod 755 "$APPDIR/usr/bin/FFConverter"
cp "$ROOT/ffconverter.png" "$APPDIR/ffconverter.png"
cp "$ROOT/usr/share/icons/hicolor/256x256/ffconverter.png" \
    "$APPDIR/usr/share/icons/hicolor/256x256/apps/ffconverter.png"

cat > "$APPDIR/ffconverter.desktop" <<'EOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=FFConverter
Comment=Simple Video, Audio, and Image Converter
GenericName=Media Converter
Exec=FFConverter %F
TryExec=FFConverter
Terminal=false
Categories=AudioVideo;AudioVideoEditing;
Keywords=convert;video;audio;image;ffmpeg;media;
MimeType=video/mp4;video/x-matroska;video/quicktime;video/x-msvideo;video/webm;video/mpeg;video/ogg;video/x-ms-wmv;video/mp2t;audio/mpeg;audio/mp4;audio/x-m4a;audio/flac;audio/x-wav;audio/ogg;audio/opus;image/jpeg;image/png;image/webp;image/gif;image/tiff;image/bmp;image/avif;
Icon=ffconverter
StartupNotify=true
StartupWMClass=FFConverter
EOF
cp "$APPDIR/ffconverter.desktop" "$APPDIR/usr/share/applications/ffconverter.desktop"

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE=$(dirname "$(readlink -f "$0")")
exec "$HERE/usr/bin/FFConverter" "$@"
EOF
chmod 755 "$APPDIR/AppRun"

curl -L --fail --retry 3 -o /tmp/appimagetool \
    https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
chmod 755 /tmp/appimagetool

ARCH=x86_64 /tmp/appimagetool --appimage-extract-and-run --no-appstream \
    "$APPDIR" "/out/FFConverter-${VERSION}-x86_64.AppImage"

cp ./dist/FFConverter "/out/FFConverter-${VERSION}-x86_64.bin"
chmod 755 "/out/FFConverter-${VERSION}-x86_64.bin"
(
    cd /out
    sha256sum "FFConverter-${VERSION}-x86_64.AppImage" \
        > "FFConverter-${VERSION}-x86_64.AppImage.sha256"
)

chmod 755 "/out/FFConverter-${VERSION}-x86_64.AppImage"
chmod 644 "/out/FFConverter-${VERSION}-x86_64.AppImage.sha256"
chmod 755 "/out/FFConverter-${VERSION}-x86_64.bin"
if [ -n "${HOST_UID:-}" ] && [ -n "${HOST_GID:-}" ]; then
    chown -R "$HOST_UID:$HOST_GID" /out
fi
echo "built FFConverter-${VERSION}-x86_64.AppImage"
