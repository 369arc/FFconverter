FFConverter for macOS
=====================

A simple video, audio, and image converter for macOS 11 or newer (Apple
Silicon and Intel). FFmpeg is included in the application bundle.

Install
-------
1. Open the .dmg file.
2. Drag FFConverter.app into the Applications folder.
3. Launch it from Applications.

This build is not notarized by Apple. On first launch macOS may show:

  "Apple could not verify 'FFConverter' is free of malware that may harm
   your Mac or compromise your privacy."

This is Gatekeeper's standard warning for an app that is not notarized; it is
not a virus report. If you trust the download and its SHA256 checksum, do one
of the following:

- Open System Settings -> Privacy & Security, find the FFConverter message
  and click "Open Anyway", then confirm; or
- Right-click / Control-click FFConverter.app, choose "Open", then "Open"
  again (this may not be available on newer macOS versions); or
- Remove the quarantine flag:

    xattr -dr com.apple.quarantine /Applications/FFConverter.app

If macOS says the app is "damaged", run:

    xattr -cr /Applications/FFConverter.app

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
