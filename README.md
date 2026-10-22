# FFConverter

A simple, portable video, audio, and image converter for Linux, built with
Python, Tk/CustomTkinter, and FFmpeg.

![FFConverter](screenshot-ui-dark_converted.png)

## Features

- Video, audio, and image tabs with format-specific options
- Batch conversion with per-file progress and working cancellation
- Drag and drop, native file dialogs, and “Open with” support
- Optional system tray icon
- No Python packages are installed with `pip` and no network access is
  required at install time

## Requirements

| Component | Version / package |
|-----------|-------------------|
| Python | 3.8 or newer |
| Tk bindings | `python3-tk` (Debian/Ubuntu), `python3-tkinter` (Fedora), `tk` (Arch) |
| FFmpeg | 5.0 or newer (recommended) |

FFConverter checks for FFmpeg at startup. Without it the GUI still opens, but
conversion is disabled and a clear warning is shown.

## Install

### Portable archive (recommended)

The portable archive contains the Python GUI dependencies in `vendor/`, so it
works on any distribution with Python 3 + Tk:

```bash
curl -LO https://github.com/369arc/FFconverter/releases/latest/download/FFConverter-portable-x86_64.tar.xz
tar -xf FFConverter-portable-x86_64.tar.xz
cd FFConverter
./run.sh
```

For ARM64 (Raspberry Pi 4/5, ARM servers) use
`FFConverter-portable-arm64.tar.xz`.

To add a menu entry, run `./install-desktop.sh` from the extracted directory.
The portable `run.sh` uses the bundled FFmpeg when the archive contains
`usr/bin/ffmpeg`; otherwise it requires a system FFmpeg.

### Debian / Ubuntu

```bash
sudo apt install ffmpeg
curl -LO https://github.com/369arc/FFconverter/releases/latest/download/ffconverter_1.1.0_all.deb
sudo apt install ./ffconverter_1.1.0_all.deb
FFConverter
```

`apt install ./file.deb` resolves `python3-tk` and `libxcursor1`
automatically. The package is architecture-independent; the Python
dependencies are bundled inside it.

### Fedora / RHEL

```bash
sudo dnf install ffmpeg          # from RPM Fusion if it is not in your repos
curl -LO https://github.com/369arc/FFconverter/releases/latest/download/FFConverter-1.1.0-1.noarch.rpm
sudo dnf install ./FFConverter-1.1.0-1.noarch.rpm
FFConverter
```

Do **not** use `rpm -ivh --nodeps`: it hides missing Tk/X11 libraries instead
of installing them.

### Arch Linux

Use the portable archive, or install from a checkout into `~/.local`:

```bash
sudo pacman -S python tk ffmpeg
git clone https://github.com/369arc/FFConverter.git
cd FFConverter
./packaging/install.sh
~/.local/bin/FFConverter
```

The installer writes to `~/.local` by default. It does not run `sudo`, `pip`,
or any network request.

### Flatpak

A Flatpak bundle can be built from the included manifest:

```bash
flatpak-builder --user --install --force-clean build-dir com.ffconverter.FFConverter.yml
flatpak run com.ffconverter.FFConverter
```

If you already have a `FFConverter.flatpak` bundle:

```bash
flatpak install --user ./FFConverter.flatpak
flatpak run com.ffconverter.FFConverter
```

### AppImage

The AppImage published with v1.0 was built against a single Python version and
did not actually bundle Python; it is deprecated. Use the portable archive
until a reproducible AppImage build is published.

## Build from source

```bash
git clone https://github.com/369arc/FFConverter.git
cd FFConverter
python3 -m unittest discover -s tests -v
./packaging/build-deb.sh       # dist/ffconverter_<version>_all.deb
./packaging/build-rpm.sh       # dist/FFConverter-<version>-1.noarch.rpm
./packaging/build-portable.sh  # dist/FFConverter-portable-x86_64.tar.xz
```

To include FFmpeg in a portable archive, pass a directory containing
self-contained `ffmpeg` and `ffprobe` binaries:

```bash
./packaging/build-portable.sh --with-ffmpeg /path/to/static/ffmpeg
```

`packaging/build-portable.sh --arch arm64` builds the ARM64 archive. The
build scripts never install anything with `pip`; `packaging/vendor.py`
unpacks the committed pure-Python wheels into `vendor/`.

## Troubleshooting

### `ModuleNotFoundError: No module named 'customtkinter'`

Use a package/portable build from Releases. Do not run
`pip install --break-system-packages` as root: it can break the distribution's
Python and was the cause of most v1.0 installation failures.

### `No module named 'tkinter'`

```bash
# Debian/Ubuntu
sudo apt install python3-tk
# Fedora
sudo dnf install python3-tkinter
# Arch
sudo pacman -S tk
```

### “FFmpeg was not found”

```bash
# Debian/Ubuntu
sudo apt install ffmpeg
# Fedora (RPM Fusion)
sudo dnf install ffmpeg
# Arch
sudo pacman -S ffmpeg
```

### Drag and drop does not work on a minimal system

The bundled `tkinterdnd2` needs `libXcursor`. Debian/Ubuntu:
`sudo apt install libxcursor1`; Fedora: `sudo dnf install libXcursor`. If the
library is unavailable, FFConverter now starts normally and simply disables
drag and drop.

### Permission denied

```bash
chmod +x run.sh
```

## Uninstall

```bash
# DEB
sudo apt remove ffconverter
# RPM
sudo dnf remove FFConverter
# User-local install
./packaging/install.sh --uninstall
# Portable
rm -rf FFConverter
```

## Project layout

| Path | Purpose |
|------|---------|
| `ffc.py` | Application (GUI + conversion pipeline) |
| `run.sh` | Launcher with dependency/FFmpeg checks |
| `packaging/` | Reproducible DEB/RPM/portable/user-local installers |
| `pip-wheels/` | Pure-Python wheels used offline by the build scripts |
| `tests/` | Unit tests for argument building and helpers |
| `com.ffconverter.FFConverter.yml` | Flatpak manifest |

## License

FFConverter is free software under the GNU GPL v3 or later. See `LICENSE`.

Bundled FFmpeg builds are distributed under their own license, which may be
GPL-3.0-or-later depending on the build. See `THIRD_PARTY_NOTICES.md`. FFmpeg
is a separate project: <https://ffmpeg.org/>.
