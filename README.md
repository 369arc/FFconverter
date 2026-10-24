# FFConverter

A simple video, audio, and image converter for Linux, Windows, and macOS,
built with Python, Tk/CustomTkinter, and FFmpeg.

![FFConverter](screenshot-ui-dark_converted.png)
![FFConverter](screenshot-ui-light_converted.png)

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
| Platform | Linux (x86_64 / ARM64), Windows 10/11 (x64), macOS 11+ (Intel / Apple Silicon) |
| Python | Linux: 3.8 or newer; Windows/macOS builds bundle Python |
| Tk bindings | Linux: `python3-tk`, `python3-tkinter` or `tk`; Windows/macOS: bundled |
| FFmpeg | Linux: 5.0 or newer; Windows/macOS builds include FFmpeg/FFprobe |

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

### Windows 10/11 (64-bit)

FFmpeg is bundled, so no separate installation is required. Two variants are
available:

**Portable ZIP (recommended)** — fast startup, contains `FFConverter.exe`,
`ffmpeg.exe`, and `ffprobe.exe`:

```powershell
Invoke-WebRequest -Uri "https://github.com/369arc/FFconverter/releases/latest/download/FFConverter-1.1.0-windows-x86_64.zip" -OutFile "FFConverter.zip"
Expand-Archive -Path "FFConverter.zip" -DestinationPath "."
.\FFConverter\FFConverter.exe
```

**Single-file EXE** — one file, FFmpeg included, but startup is slower because
it is unpacked to a temporary directory on each run:

```powershell
Invoke-WebRequest -Uri "https://github.com/369arc/FFconverter/releases/latest/download/FFConverter-1.1.0-windows-x86_64.exe" -OutFile "FFConverter.exe"
.\FFConverter.exe
```

The Windows builds are **not code-signed**. If SmartScreen shows “Windows
protected your PC”, click **More info → Run anyway** after verifying the
SHA256 checksum. Do not disable Microsoft Defender or your antivirus. If a
scanner reports a false positive, open an issue instead of disabling
protection.

### macOS 11+ (Intel / Apple Silicon)

FFmpeg is bundled. Download the DMG for your architecture, open it, and drag
`FFConverter.app` to Applications:

- Apple Silicon: `FFConverter-1.1.0-macos-arm64.dmg`
- Intel: `FFConverter-1.1.0-macos-x86_64.dmg`

The macOS build is ad-hoc signed but **not notarized**. On first launch,
right-click / Control-click the app and choose **Open**, or use
**System Settings → Privacy & Security → Open Anyway** after verifying the
SHA256 checksum. Do not disable Gatekeeper globally.

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

The release includes a Flatpak bundle. It requires the
`org.freedesktop.Platform` 25.08 runtime from Flathub:

```bash
curl -LO https://github.com/369arc/FFconverter/releases/latest/download/FFConverter-1.1.0-x86_64.flatpak
flatpak install --user ./FFConverter-1.1.0-x86_64.flatpak
flatpak run com.ffconverter.FFConverter
```

To build it from source:

```bash
flatpak-builder --user --install --force-clean build-dir com.ffconverter.FFConverter.yml
flatpak run com.ffconverter.FFConverter
```

### AppImage

The AppImage is self-contained: it bundles Python, Tk and the Python GUI
dependencies. It uses the system FFmpeg for conversions and needs glibc 2.35+
(Ubuntu 22.04 or newer).

```bash
curl -LO https://github.com/369arc/FFconverter/releases/latest/download/FFConverter-1.1.0-x86_64.AppImage
chmod +x FFConverter-1.1.0-x86_64.AppImage
./FFConverter-1.1.0-x86_64.AppImage
```

If FUSE is unavailable, run it with
`./FFConverter-1.1.0-x86_64.AppImage --appimage-extract-and-run`.

## Build from source

```bash
git clone https://github.com/369arc/FFConverter.git
cd FFConverter
python3 -m unittest discover -s tests -v
./packaging/build-deb.sh       # dist/ffconverter_<version>_all.deb
./packaging/build-rpm.sh       # dist/FFConverter-<version>-1.noarch.rpm
./packaging/build-portable.sh  # dist/FFConverter-portable-x86_64.tar.xz
./packaging/build-appimage.sh  # dist/FFConverter-<version>-x86_64.AppImage
./packaging/build-flatpak.sh   # dist/FFConverter-<version>-x86_64.flatpak
```

Windows (from PowerShell):

```powershell
.\packaging\build-windows.ps1
# dist/FFConverter-<version>-windows-x86_64.zip
# dist/FFConverter-<version>-windows-x86_64.exe
```

macOS (Homebrew Python with Tk, FFmpeg and dylibbundler):

```bash
brew install python@3.12 python-tk@3.12 ffmpeg dylibbundler
PYTHON="$(brew --prefix python@3.12)/bin/python3.12" \
  ./packaging/build-macos.sh
# dist/FFConverter-<version>-macos-arm64.dmg (or x86_64)
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

### Windows SmartScreen or antivirus warning

The Windows builds are not code-signed. Verify the SHA256 from `SHA256SUMS`,
then use **More info → Run anyway** if you trust the download. Do not disable
Microsoft Defender or your antivirus. Report false positives via GitHub Issues
so they can be submitted to the scanner vendor.

### macOS: “developer cannot be verified”

This build is not notarized by Apple. Verify the DMG SHA256, then
right-click the app → **Open** → **Open**, or use
**System Settings → Privacy & Security → Open Anyway**. Do not disable
Gatekeeper globally.

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

Windows: delete the extracted `FFConverter` folder or the single `.exe` file.
macOS: move `FFConverter.app` from Applications to the Trash.
No registry entries, system files or launch agents are created.

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
