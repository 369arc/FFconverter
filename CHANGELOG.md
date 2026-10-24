# Changelog

## 1.1.0 — 2026-10-22

### Installation and packaging

- Fixed all download links that pointed at the non-existent `963arc`
  account; the repository is `369arc/FFconverter`.
- Replaced the unreproducible v1.0 Debian/RPM/AppImage/ARM build outputs with
  reproducible scripts in `packaging/`.
- Bundled the pure-Python GUI dependencies and removed install-time
  `pip install --break-system-packages` / root pip usage.
- Added a user-local installer (`packaging/install.sh`) that needs no root,
  pip, or network.
- Fixed the DEB/RPM launchers (`FFConverter` command), desktop entries, icons,
  package names, descriptions, dependencies, and licenses.
- Added missing `libXcursor` dependency and graceful fallback when the
  drag-and-drop Tk extension cannot load.
- Updated the Flatpak manifest to runtime 25.08, bundled Tcl/Tk for tkinter,
  and removed unnecessary network access.
- Added a self-contained AppImage (PyInstaller, Python/Tk bundled), a Flatpak
  bundle, Windows portable ZIP / single-file EXE builds, and macOS arm64/
  Intel DMGs with bundled FFmpeg.
- Removed committed build artifacts and unused Pillow wheels from the working
  tree (history still contains them; see `AUDIT.md`).

### Conversion fixes

- Rewrote batch conversion to run sequentially on one worker; cancel now stops
  the active FFmpeg process and does not leave queued jobs running.
- Fixed output collisions (`clip.mp4` + `clip.mkv` no longer overwrite
  `clip_converted.mp4`) and removed truncated files after failures.
- Replaced stderr scraping with `-progress pipe:1`, so the progress bar
  actually updates.
- Made UI updates thread-safe through a Tk queue.
- Fixed drag and drop storing the dropped files (it previously updated only
  the label, then reported “select a file”).
- Fixed uppercase/lowercase format bugs affecting image compression, WAV/FLAC
  filters, ALAC output, and several audio codecs.
- CRF/preset are now applied only to encoders that support them; copy mode
  rejects filters/frame-rate instead of silently ignoring them.
- Fixed the bitrate parser for presets such as `480P (1.5M)`, added actual
  resolution scaling, and made “Keep aspect ratio” work.
- Fixed image resizing (`-2` instead of `-1`), ICO size limits, animated input
  handling, and unsupported output formats.
- Added `--version`, `--help`, and desktop “Open with” file arguments.
- Fixed application close (a duplicate `_on_closing` called a non-existent
  method) and tray-process cleanup.

### Tests

- Added 22 unit tests for argument building, format validation, output naming,
  and progress parsing.
- Verified the built DEB on Ubuntu 24.04 (Python 3.12), the RPM on Fedora 44
  (Python 3.14), the portable archive on Fedora 44, the AppImage on Ubuntu
  22.04/Fedora 44, the Flatpak with a real conversion, and the Windows
  EXE/ZIP with a frozen-GUI smoke test on windows-latest, and the macOS DMGs
  on macos-15 / macos-15-intel.

## 1.0 — 2026-05-03

Initial release. See `AUDIT.md` for the issues found in its artifacts.
