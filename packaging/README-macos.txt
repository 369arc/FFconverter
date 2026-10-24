FFConverter for macOS
=====================

A simple video, audio, and image converter for macOS 11 or newer (Apple
Silicon and Intel). FFmpeg is included in the application bundle.

Install
-------
1. Open the .dmg file.
2. Drag FFConverter.app into the Applications folder.
3. Launch it from Applications.

This build is not notarized by Apple. On first launch macOS may show
"FFConverter cannot be opened because the developer cannot be verified".

If you trust the download and its SHA256 checksum, do one of the following:

- Right-click / Control-click FFConverter.app, choose "Open", then "Open"
  again; or
- Open System Settings -> Privacy & Security and click "Open Anyway"; or
- Remove the quarantine flag:

    xattr -dr com.apple.quarantine /Applications/FFConverter.app

Do not disable Gatekeeper globally.

Files and output
----------------
Converted files are written to ~/Converted by default. You can choose another
output folder in the application.

Verify the download
-------------------
SHA256 checksums are published in SHA256SUMS on the release page:

    shasum -a 256 FFConverter-<version>-macos-<arch>.dmg

The value must match the corresponding line in SHA256SUMS.

Uninstall
---------
Quit FFConverter and move FFConverter.app from Applications to the Trash.
No system files or launch agents are installed.

License
-------
FFConverter is GPL-3.0-or-later. FFmpeg is a separate project; see
THIRD_PARTY_NOTICES.md and the FFmpeg license files in the application bundle.
