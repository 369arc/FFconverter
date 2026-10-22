# FFConverter v1.0 audit

Date: 2026-10-22
Scope: repository `369arc/FFconverter`, release `v1.0` assets, current
`master`, installation paths, and the conversion pipeline.

## Summary

The application worked as a local Python script, but the published Linux
packages were not built from the repository and did not install a working
application on most distributions. The most common user-visible failures
(`ModuleNotFoundError: customtkinter`, “FFConverter: command not found”,
broken download links, ARM64 archive with no dependencies, non-working
cancel/progress, drag and drop selecting nothing) were reproducible and are
fixed in 1.1.0.

The audit also found legal/licensing metadata that contradicted the bundled
FFmpeg build, and repository bloat of roughly 160 MB in `.git`.

## Evidence

- Release asset `FFConverter_1.0-1_amd64.deb` control file:
  `Maintainer: <x@o>`, `Homepage: http://example.com/no-uri-given`,
  `License: unknown`, `Description: no description given`.
- That DEB contained packages under `/usr/lib/python3.14/site-packages/` and
  no `/usr/bin/FFConverter`. Ubuntu 24.04 ships Python 3.12, so the bundled
  modules were invisible to its Python.
- The RPM contained the same Python 3.14 tree, `Summary: no description
  given`, and no bundled FFmpeg.
- The AppImage decompressed to 2.6 MB, used the **system** Python and system
  `customtkinter`, and carried a dynamically linked Fedora FFmpeg.
- `FFConverter-portable-arm64.tar.xz` was 48 KB and contained no FFmpeg and no
  Python packages; the README told users to `cd FFConverter-portable-arm64`,
  but the archive has no top-level directory.
- All README/release download URLs referenced `github.com/963arc/...` instead
  of `369arc/...` (HTTP 404).

## Findings

Severity: **P0** blocks installation/conversion for most users, **P1** breaks
a major feature, **P2** quality/robustness, **P3** cosmetic/docs.

| ID | Sev | Finding | Status |
|----|-----|---------|--------|
| P0-1 | P0 | Download links and release notes point to the wrong GitHub account (`963arc`). | Fixed |
| P0-2 | P0 | Published DEB/RPM/AppImage/ARM artifacts do not match the repo and bundle Python 3.14 packages only; they fail on Python 3.8–3.13. | Fixed (new build scripts) |
| P0-3 | P0 | DEB/RPM install no `FFConverter` command; desktop entry uses a PATH-dependent `run.sh`. | Fixed |
| P0-4 | P0 | `run.sh` does not install/check `customtkinter`; portable build fails with `ModuleNotFoundError`. | Fixed (vendored deps + offline fallback) |
| P0-5 | P0 | ARM64 archive has no dependencies/FFmpeg and the README extraction path is wrong. | Fixed |
| P0-6 | P0 | AppImage is not self-contained (system Python, dynamic FFmpeg, 3.14-only packages). | Fixed (PyInstaller AppImage, Ubuntu 22.04 build) |
| P0-7 | P0 | Duplicate `_on_closing` calls non-existent `_cleanup_and_exit`; close button raises and app cannot quit cleanly. | Fixed |
| P0-8 | P0 | Batch conversion submits all files to a 2-worker pool with a single global FFmpeg process; cancel kills one process and leaves others running; output names collide and overwrite. | Fixed (sequential worker, unique names) |
| P0-9 | P0 | Drag and drop updates only the label, not `selected_*_files`, so Convert says “select a file”. | Fixed |
| P1-1 | P1 | Progress never updates: no `-progress`, and FFmpeg writes stats with `\r` to stderr; `readline()` misses them. | Fixed |
| P1-2 | P1 | Progress monitor runs on the same 2-worker executor as the conversions, causing a potential deadlock/queued monitor. | Fixed |
| P1-3 | P1 | Tk widgets and `after()` are called from worker threads (not thread-safe); tab switches send progress to the wrong tab. | Fixed (UI queue, per-mode updates) |
| P1-4 | P1 | CRF/`-preset medium` is passed to codecs that do not support it (MPEG-1/2, WMV, Theora...), so many conversions fail. | Fixed |
| P1-5 | P1 | Bitrate regex `(\d+M)` misses `1.5M` (480P preset). | Fixed |
| P1-6 | P1 | Video “Keep aspect ratio” is a no-op; presets labelled 1080P/4K/8K never resize. | Fixed |
| P1-7 | P1 | Uppercase format names vs lowercase comparisons: image compress does nothing; WAV/FLAC with limiter/dither falls through to AAC in a WAV file. | Fixed |
| P1-8 | P1 | ALAC writes `.alac` (no such muxer); AMR ignores 8 kHz mono; OGG offers 320K/256K, which libvorbis rejects. | Fixed |
| P1-9 | P1 | `scale=W:-1` can produce odd heights, which JPEG/4:2:0 rejects. | Fixed (`-2`) |
| P1-10 | P1 | Image tab offers PDF/PSD/AI/EPS/HEIC as outputs although FFmpeg cannot encode them; ICO fails above 256×256. | Fixed |
| P1-11 | P1 | Missing `libXcursor` makes `tkinterdnd2` raise during root-window construction, killing the whole app instead of disabling DnD. | Fixed |
| P1-12 | P1 | `ffprobe` path is derived with `FFMPEG_PATH.replace("ffmpeg","ffprobe")`, which fails for wrappers/snap paths. | Fixed |
| P1-13 | P1 | Silent overwrite of existing outputs (`-y`, fixed `_converted` name). | Fixed (unique names, no overwrite) |
| P1-14 | P1 | Cancel leaves partial output files. | Fixed |
| P1-15 | P1 | `-vf`/`-r` are silently ignored in copy mode (the old `cmd[-1] != "copy"` check is unreliable). | Fixed (explicit error) |
| P1-16 | P1 | `debian/postinst` runs `pip3 install --break-system-packages` as root; failures are hidden by `|| true`; `prerm` only removes one launcher. | Removed (new packaging) |
| P1-17 | P1 | Flatpak manifest says runtime 23.08 while the published bundle uses 25.08; `--share=network` is unnecessary; ffmpeg extension is not auto-downloaded; runtime Python lacks tkinter. | Fixed (Tcl/Tk modules, 25.08, rebuilt) |
| P1-18 | P1 | Bundled FFmpeg is described as LGPL, but the v1.0 static/AppImage builds enable GPL. | Fixed in notices |
| P1-19 | P1 | No checksums, signatures, or CI for DEB/RPM/portable/AppImage/Flatpak; only an ARM workflow using the deprecated `upload-release-asset@v1`. | Fixed (scripts + CI) |
| P2-1 | P2 | No CLI file arguments, so desktop `%F`/“Open with” did nothing. | Fixed |
| P2-2 | P2 | Output extensions were uppercase (`clip.MP4`), surprising on Linux. | Fixed |
| P2-3 | P2 | Tray script in predictable `/tmp/ffconverter_tray.py`, shared sentinel files, never cleaned; tray process not stopped on exit. | Fixed (private temp dir, cleanup) |
| P2-4 | P2 | `_get_file_duration` runs synchronously in the UI thread per file. | Fixed (worker thread) |
| P2-5 | P2 | Empty/unsupported output dirs and read-only destinations produce tracebacks or unclear FFmpeg errors. | Improved (explicit errors) |
| P2-6 | P2 | Missing `resources/images/folder_icon.png` referenced by the Browse button. | Fixed (fallback) |
| P2-7 | P2 | `CustomSizeDialog` silently closes on invalid input. | Fixed |
| P2-8 | P2 | `MimeType=video/*;audio/*;image/*` is invalid in desktop files; category hint duplicated entries. | Fixed |
| P2-9 | P2 | README tells Arch users `sudo cp -r usr /` and later `rm -rf /opt/FFConverter`, which do not match. | Fixed |
| P2-10 | P2 | README claims “Python 3.8+”, “FFmpeg optional/bundled” for DEB/RPM, and “~388 MB” inconsistently. | Fixed |
| P2-11 | P2 | No tests at all. | Fixed (22 unit tests) |
| P2-12 | P2 | Bare `except:` clauses and dead custom-dialog code. | Partially fixed |
| P3-1 | P3 | Repository contains a 96 MB Flatpak and 68 MB of Pillow wheels/tarball; `.git` is 162 MB. | Working tree cleaned; history remains |
| P3-2 | P3 | Root spec had `Source0: /home/x/rpmbuild/...` and URL `963arc`. | Removed/replaced |
| P3-3 | P3 | DEB metadata had placeholder maintainer/homepage and no description. | Fixed |
| P3-4 | P3 | `APP_CONFIG`/help text contains stale hints and “pip install” advice. | Partially fixed |

## Fixes in 1.1.0

### Packaging

- `packaging/vendor.py` unpacks the committed pure-Python wheels into
  `vendor/` without pip/network.
- `packaging/build-deb.sh` builds a valid `Architecture: all` DEB with
  `/usr/bin/FFConverter`, correct dependencies, desktop entry, icon, and
  bundled Python modules.
- `packaging/build-rpm.sh` builds a valid `noarch` RPM with the same layout
  and `AutoReqProv: no` (the vendored multi-arch TkDND libraries otherwise
  generate bogus aarch64 dependencies).
- `packaging/build-portable.sh` builds x86_64/ARM64 archives with `vendor/`.
- `packaging/install.sh` installs into `~/.local` or a custom prefix without
  root, pip, or network.
- `packaging/build-appimage.sh` builds a PyInstaller AppImage on Ubuntu 22.04,
  bundling Python/Tk and using the system FFmpeg.
- `packaging/build-flatpak.sh` builds a Flatpak bundle with Tcl/Tk modules; the
  manifest uses runtime 25.08 and only X11 (Tk has no native Wayland backend).
- `run.sh` checks Python/Tk, uses `vendor/`, offers an offline wheel-based
  venv fallback, and no longer aborts before `--version` when FFmpeg is
  missing.
- CI workflows build/test DEB, RPM, portable, and AppImage artifacts.

### Application

- Sequential batch worker; thread-safe UI queue; real `-progress pipe:1`
  parsing; working cancel and partial-file cleanup.
- Unique output names; no silent overwrite.
- Format/argument correctness fixes listed above.
- `--version`, `--help`, and desktop file arguments.
- Clean shutdown and tray cleanup.

## Verification performed

- `python3 -m unittest discover -s tests -v` — 22 tests pass.
- Built `ffconverter_1.1.0_all.deb`; installed and launched it inside
  `ubuntu:24.04` (Python 3.12) with `xvfb-run`; `FFConverter --version` and
  GUI startup verified.
- Built `FFConverter-1.1.0-1.noarch.rpm`; installed and launched it inside
  `fedora:44` (Python 3.14) with `xvfb-run`; verified.
- Built the portable archive and ran it with `PYTHONNOUSERSITE=1`; bundled
  imports and GUI startup verified.
- Integration tests: 2-file batch with colliding stems produced
  `a_converted.mp4` and `a_converted_1.mp4`; MP3/JPG conversions; cancel
  during an 8K conversion stopped FFmpeg and removed the partial file.
- AppImage (Ubuntu 22.04/Fedora 44) and Flatpak (runtime 25.08) launched; the
  Flatpak performed a real MP4 → MKV conversion.
- Format matrix against Fedora FFmpeg 8: all video outputs except the
  deliberately removed DV/GXF now succeed; all audio outputs succeed; all
  image outputs succeed (ICO now scales to 256).

## Open items / recommendations

1. **Old v1.0 assets.** The v1.0 release is now marked deprecated, but its
   broken assets are still downloadable. Delete them if repository owners do
   not want to keep them for history.
2. **Repository history.** Deleting the 96 MB Flatpak and 68 MB of wheels from
   the working tree does not shrink existing clones. If repository size
   matters, rewrite history with `git filter-repo` and force-push — a
   destructive operation that needs owner approval.
3. **Old `debian/` and root spec.** Removed because they were not the files
   used for the release and could not build from a clean checkout. Standard
   `dpkg-buildpackage` packaging can be added later on top of
   `packaging/build-deb.sh`.
4. **UI testing.** The fixes were verified with Tk/Xvfb; test on GNOME
   Wayland, KDE, and a HiDPI display before release.
5. **Translations/settings persistence** are not part of this audit.

## Notes on the audit environment

- Host: Fedora 44, Python 3.14.8, FFmpeg 8.0.1, no passwordless sudo.
- DEB/RPM installs were performed in rootless Podman containers.
- The Flatpak was rebuilt from the updated manifest (runtime 25.08, Tcl/Tk
  modules), installed, and verified with Python imports and a real MP4 → MKV
  conversion. The AppImage was built on Ubuntu 22.04 and launched there and on
  Fedora 44.
