#!/bin/sh
# Build a Debian/Ubuntu package without debhelper or network access.
# The Python runtime dependencies are vendored, so installation never runs pip
# and works with the distribution's own Python version.

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VERSION=$(sed -n 's/^__version__ = "\([^"]*\)"/\1/p' "$ROOT/ffc.py" | head -n1)
OUTPUT_DIR=${OUTPUT_DIR:-"$ROOT/dist"}
STAGE="$ROOT/build/deb/ffconverter_${VERSION}_all"

[ -n "$VERSION" ] || { echo "cannot read version from ffc.py" >&2; exit 1; }
command -v dpkg-deb >/dev/null 2>&1 || {
    echo "dpkg-deb is required (install dpkg-dev)" >&2
    exit 1
}

rm -rf "$ROOT/build/deb"
mkdir -p "$STAGE/DEBIAN" "$OUTPUT_DIR"

install -D -m 755 "$ROOT/ffc.py" "$STAGE/usr/share/ffconverter/ffc.py"
install -D -m 755 "$ROOT/run.sh" "$STAGE/usr/share/ffconverter/run.sh"
install -D -m 644 "$ROOT/LICENSE" "$STAGE/usr/share/doc/ffconverter/copyright"
install -D -m 644 "$ROOT/THIRD_PARTY_NOTICES.md" \
    "$STAGE/usr/share/doc/ffconverter/THIRD_PARTY_NOTICES.md"
install -D -m 644 "$ROOT/ffconverter.png" "$STAGE/usr/share/ffconverter/ffconverter.png"
cp -a "$ROOT/resources" "$STAGE/usr/share/ffconverter/"
python3 "$ROOT/packaging/vendor.py" "$STAGE/usr/share/ffconverter/vendor" >/dev/null

install -D -m 644 "$ROOT/usr/share/applications/ffconverter.desktop" \
    "$STAGE/usr/share/applications/ffconverter.desktop"
install -D -m 644 "$ROOT/usr/share/icons/hicolor/256x256/ffconverter.png" \
    "$STAGE/usr/share/icons/hicolor/256x256/apps/ffconverter.png"

mkdir -p "$STAGE/usr/bin"
cat > "$STAGE/usr/bin/FFConverter" <<'EOF'
#!/bin/sh
exec /usr/share/ffconverter/run.sh "$@"
EOF
chmod 755 "$STAGE/usr/bin/FFConverter"
ln -s FFConverter "$STAGE/usr/bin/ffconverter"

cat > "$STAGE/DEBIAN/control" <<EOF
Package: ffconverter
Version: ${VERSION}-1
Section: video
Priority: optional
Architecture: all
Maintainer: 369ARC <email@369arc.com>
Homepage: https://github.com/369arc/FFconverter
Installed-Size: $(du -sk "$STAGE" | cut -f1)
Depends: python3 (>= 3.8), python3-tk, libxcursor1
Recommends: ffmpeg, xdg-utils
Description: simple video, audio, and image converter
 FFConverter is a graphical frontend for FFmpeg that converts video,
 audio, and image files between common formats.
 .
 The Python GUI dependencies are bundled in the package, so no pip
 installation or network access is required. FFmpeg is recommended
 for actual conversions.
EOF

# dpkg expects relative paths without the leading "./".
(
    cd "$STAGE"
    find . -type f ! -path './DEBIAN/*' -printf '%P\0' \
        | sort -z \
        | xargs -0 md5sum > DEBIAN/md5sums
)

PACKAGE="$OUTPUT_DIR/ffconverter_${VERSION}_all.deb"
dpkg-deb --build --root-owner-group "$STAGE" "$PACKAGE" >/dev/null
(
    cd "$OUTPUT_DIR"
    sha256sum "$(basename "$PACKAGE")" > "$(basename "$PACKAGE").sha256"
)

echo "built $PACKAGE"
dpkg-deb -I "$PACKAGE" | sed -n '1,20p'
