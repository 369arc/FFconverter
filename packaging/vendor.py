#!/usr/bin/env python3
"""Extract the pure-Python runtime dependencies into a vendor directory.

The wheels are committed in pip-wheels/ so packaging never needs network
access and never runs pip as root.  Only arch-independent wheels are used;
Pillow/pystray (optional tray icon) are intentionally not required.
"""

import sys
import zipfile
from pathlib import Path

WHEELS = [
    "customtkinter-5.2.2-py3-none-any.whl",
    "darkdetect-0.8.0-py3-none-any.whl",
    "packaging-26.2-py3-none-any.whl",
    "send2trash-2.1.0-py3-none-any.whl",
    "tkinterdnd2-0.4.3-py3-none-any.whl",
]


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} DESTINATION", file=sys.stderr)
        return 2

    root = Path(__file__).resolve().parent.parent
    destination = Path(sys.argv[1]).resolve()
    destination.mkdir(parents=True, exist_ok=True)

    for name in WHEELS:
        wheel = root / "pip-wheels" / name
        if not wheel.is_file():
            print(f"missing wheel: {wheel}", file=sys.stderr)
            return 1
        with zipfile.ZipFile(wheel) as archive:
            archive.extractall(destination)

    print(f"vendored {len(WHEELS)} packages into {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
