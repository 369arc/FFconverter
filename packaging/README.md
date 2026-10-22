# Packaging

The old `debian/` and `FFConverter.spec` files in the repository root were not
the ones used to produce the v1.0 release artifacts. They could not be built
from a clean checkout (the spec had an absolute `/home/x/...` `Source0`, the
Debian package had no `changelog`, and the binary packages did not match the
release). They have been replaced by reproducible scripts:

| Script | Output |
|--------|--------|
| `vendor.py` | Extracts pure-Python dependencies into `vendor/` (offline) |
| `install.sh` | User-local install into `~/.local` (or `--prefix`) |
| `install-desktop.sh` | Adds a menu entry for a portable directory |
| `build-deb.sh` | `dist/ffconverter_<version>_all.deb` |
| `build-rpm.sh` | `dist/FFConverter-<version>-1.noarch.rpm` |
| `build-portable.sh` | `dist/FFConverter-portable-<arch>.tar.xz` |

All scripts use the wheels in `../pip-wheels/`, never run `pip` as root, and
never need network access. `build-portable.sh --with-ffmpeg DIR` can embed
self-contained `ffmpeg`/`ffprobe` binaries.

Flatpak builds use the manifest in the repository root:

```bash
flatpak-builder --user --install --force-clean build-dir \
  com.ffconverter.FFConverter.yml
```

## Verification

```bash
python3 -m unittest discover -s tests -v
./packaging/build-deb.sh
dpkg-deb -c dist/ffconverter_1.1.0_all.deb
./packaging/build-rpm.sh
rpm -qlp dist/FFConverter-1.1.0-1.noarch.rpm
```

The release workflow in `.github/workflows/ci.yml` builds the packages on
Ubuntu and runs the unit tests. The ARM64 workflow builds the portable archive
on `ubuntu-24.04-arm`.
