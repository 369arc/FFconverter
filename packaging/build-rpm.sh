#!/bin/sh
# Build a noarch RPM with vendored Python dependencies.
# Works on Fedora/RHEL and needs only rpmbuild + python3.

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VERSION=$(sed -n 's/^__version__ = "\([^"]*\)"/\1/p' "$ROOT/ffc.py" | head -n1)
OUTPUT_DIR=${OUTPUT_DIR:-"$ROOT/dist"}
TOP="$ROOT/build/rpmbuild"
SRC="$TOP/SOURCES/FFConverter-$VERSION"

[ -n "$VERSION" ] || { echo "cannot read version from ffc.py" >&2; exit 1; }
command -v rpmbuild >/dev/null 2>&1 || {
    echo "rpmbuild is required (install rpm-build)" >&2
    exit 1
}

rm -rf "$TOP"
mkdir -p "$SRC" "$OUTPUT_DIR"

cp "$ROOT/ffc.py" "$ROOT/run.sh" "$ROOT/LICENSE" "$ROOT/ffconverter.png" \
    "$ROOT/README.md" "$ROOT/THIRD_PARTY_NOTICES.md" "$SRC/"
cp -a "$ROOT/resources" "$SRC/"
mkdir -p "$SRC/usr/share/applications"
mkdir -p "$SRC/usr/share/icons/hicolor/256x256/apps"
cp "$ROOT/usr/share/applications/ffconverter.desktop" "$SRC/usr/share/applications/"
cp "$ROOT/usr/share/icons/hicolor/256x256/ffconverter.png" \
    "$SRC/usr/share/icons/hicolor/256x256/ffconverter.png"
cp "$ROOT/usr/share/icons/hicolor/256x256/ffconverter.png" \
    "$SRC/usr/share/icons/hicolor/256x256/apps/"
python3 "$ROOT/packaging/vendor.py" "$SRC/vendor" >/dev/null

tar -C "$TOP/SOURCES" -czf "$TOP/SOURCES/FFConverter-$VERSION.tar.gz" \
    "FFConverter-$VERSION"

SPEC="$ROOT/build/ffconverter.spec"
sed "s/^Version:.*/Version:        $VERSION/" \
    "$ROOT/packaging/ffconverter.spec" > "$SPEC"

rpmbuild -bb \
    --define "_topdir $TOP" \
    --define "_sourcedir $TOP/SOURCES" \
    --define "_rpmdir $TOP/RPMS" \
    --define "debug_package %{nil}" \
    "$SPEC" >/dev/null

RPM=$(find "$TOP/RPMS" -name '*.rpm' -type f | head -n1)
[ -n "$RPM" ] || { echo "rpmbuild produced no package" >&2; exit 1; }
cp "$RPM" "$OUTPUT_DIR/"
PACKAGE="$OUTPUT_DIR/$(basename "$RPM")"
(
    cd "$OUTPUT_DIR"
    sha256sum "$(basename "$PACKAGE")" > "$(basename "$PACKAGE").sha256"
)

echo "built $PACKAGE"
rpm -qip "$PACKAGE" | sed -n '1,16p'
