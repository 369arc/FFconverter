FFConverter for Windows
=======================

A simple video, audio, and image converter for Windows 10/11 (64-bit).
FFmpeg is included in this package; no separate installation is required.

Contents
--------
- FFConverter.exe  - the application
- ffmpeg.exe       - bundled FFmpeg
- ffprobe.exe      - bundled FFprobe
- LICENSE, THIRD_PARTY_NOTICES.md, FFmpeg-LICENSE.txt

How to run
----------
Portable ZIP:
  1. Extract the whole archive to a folder.
  2. Run FFConverter.exe.

Single-file EXE:
  1. Run FFConverter-<version>-windows-x86_64.exe.
  2. Startup is slower because the executable is unpacked to a temporary
     folder on each run.

Converted files are written to C:\Users\<your-name>\Converted by default. You
can choose another output folder in the application.

Windows SmartScreen
-------------------
This build is not code-signed, so Windows may show "Windows protected your PC".
Click "More info" -> "Run anyway" if you trust the download and its SHA256
checksum. Do not disable Microsoft Defender or your antivirus.

If an antivirus product reports a false positive, please open an issue with the
report instead of disabling protection:
https://github.com/369arc/FFconverter/issues

Verify the download
-------------------
SHA256 checksums are published in SHA256SUMS on the release page. On Windows:

  certutil -hashfile FFConverter-<version>-windows-x86_64.zip SHA256

The reported value must match the corresponding line in SHA256SUMS.

Uninstall
---------
The portable builds do not install anything. Delete the extracted folder or
the single .exe file.

License
-------
FFConverter is GPL-3.0-or-later. FFmpeg is a separate project; see
THIRD_PARTY_NOTICES.md and FFmpeg-LICENSE.txt.
