# Third-party notices

## FFmpeg

FFConverter calls FFmpeg to read and write media files. FFmpeg is a separate
project and is not part of FFConverter's source code:

- Project: https://ffmpeg.org/
- License overview: https://ffmpeg.org/legal.html

Release archives may include an FFmpeg binary. The license of that binary
depends on how it was configured. In particular, builds with `--enable-gpl`
(including most static “release” builds) are **GPL-2.0-or-later or
GPL-3.0-or-later**, not LGPL. The v1.0 README incorrectly described the
bundled FFmpeg as LGPL; that statement has been corrected here.

If you redistribute an archive with FFmpeg, keep the FFmpeg license text and
provide the corresponding source, as required by the GPL. FFConverter itself
is GPL-3.0-or-later, so combining it with a GPL FFmpeg build is compatible.

## Python packages

The `pip-wheels/` directory contains unmodified wheels from their upstream
projects:

| Package | License |
|---------|---------|
| CustomTkinter | MIT |
| darkdetect | BSD-3-Clause |
| packaging | Apache-2.0 / BSD-2-Clause |
| send2trash | BSD-3-Clause |
| tkinterdnd2 | MIT (TkDND is Tcl/Tk licensed) |

Their license files are included in the wheels (`*.dist-info/licenses/`).
