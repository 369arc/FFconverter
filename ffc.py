# FFConverter - A simple, portable video, audio, and image converter for Linux.
# Copyright (C) 2026 369ARC
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# Note: Bundled FFmpeg builds are licensed separately; most static builds are
# GPL, not LGPL. See THIRD_PARTY_NOTICES.md for details.

# Modules
import argparse
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from pathlib import Path
from typing import List, Optional, Tuple

# PyInstaller's --windowed mode sets stdout/stderr to None on Windows/macOS.
# argparse and a few diagnostics write to them, so provide a safe sink.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

__version__ = "1.1.0"

# A desktop application must fail with a readable message, not a bare traceback,
# when its GUI dependencies are missing.
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    import customtkinter as ctk
except ImportError as exc:  # pragma: no cover - depends on the host system
    sys.stderr.write(
        "FFConverter cannot start because a Python GUI dependency is missing:\n"
        f"  {exc}\n\n"
        "Install Tk support for Python and the application dependencies:\n"
        "  Debian/Ubuntu: sudo apt install python3-tk\n"
        "  Fedora:        sudo dnf install python3-tkinter\n"
        "  Arch:          sudo pacman -S tk\n"
        "  Then run:      ./run.sh\n"
    )
    raise SystemExit(1) from exc

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# Check for tkinterdnd2 availability for drag-and-drop support
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    TKINTERDND_AVAILABLE = True
except ImportError:
    TKINTERDND_AVAILABLE = False

try:
    from send2trash import send2trash

    SEND2TRASH_AVAILABLE = True
except ImportError:
    SEND2TRASH_AVAILABLE = False

# Check for pystray availability for system tray support
try:
    import pystray
    from PIL import Image

    PYSTRAY_AVAILABLE = True
except ImportError:
    PYSTRAY_AVAILABLE = False
# CTkDnD
if TKINTERDND_AVAILABLE:

    class CTkDnD(ctk.CTk, TkinterDnD.DnDWrapper):
        """
        Custom class inheriting from CustomTkinter and TkinterDnD.
        This provides a CustomTkinter-compatible root window with drag-and-drop support.
        """

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # Drag and drop is optional. A missing X11 helper library (for
            # example libXcursor on a minimal container) used to abort the
            # whole application here; fall back to a normal Tk window instead.
            self.dnd_ready = False
            try:
                self.TkdndVersion = TkinterDnD._require(self)
                self.dnd_ready = True
            except Exception as exc:
                if os.environ.get("FFCONVERTER_DEBUG"):
                    print(f"Warning: drag-and-drop disabled: {exc}")
else:
    # Fallback to standard CTk if tkinterdnd2 is not installed
    CTkDnD = ctk.CTk

# Config

# Paths
CURRENT_DIR = Path(__file__).parent.absolute()

def _get_ffmpeg_path():
    """Return the FFmpeg executable to use, preferring a bundled build."""
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    bundled = [
        CURRENT_DIR / "usr" / "bin" / exe,
        CURRENT_DIR / "resources" / "ffmpeg" / exe,
        CURRENT_DIR / exe,
    ]

    # AppImage layout: $APPDIR/usr/bin/ffmpeg
    if os.environ.get("APPDIR"):
        bundled.insert(0, Path(os.environ["APPDIR"]) / "usr" / "bin" / exe)

    for path in bundled:
        if path.is_file():
            return str(path)

    return shutil.which(exe) or exe


def _get_ffprobe_path(ffmpeg_path: str) -> str:
    """Find ffprobe next to ffmpeg, falling back to PATH."""
    ffmpeg = Path(ffmpeg_path)
    if ffmpeg.name in ("ffmpeg", "ffmpeg.exe"):
        candidate = ffmpeg.with_name("ffprobe" + (".exe" if os.name == "nt" else ""))
        if candidate.is_file():
            return str(candidate)

    return shutil.which("ffprobe") or "ffprobe"


FFMPEG_PATH = _get_ffmpeg_path()
FFPROBE_PATH = _get_ffprobe_path(FFMPEG_PATH)

# Print the actual executable only in debug mode; desktop launchers have no
# visible terminal and the old unconditional print looked like an error.
if os.environ.get("FFCONVERTER_DEBUG"):
    print(f"FFmpeg: {FFMPEG_PATH}")
    print(f"FFprobe: {FFPROBE_PATH}")


def ffmpeg_available() -> bool:
    """Return True when the selected FFmpeg executable can actually be run."""
    try:
        result = subprocess.run(
            [FFMPEG_PATH, "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


FOLDER_ICON_PATH = CURRENT_DIR / "resources" / "images" / "folder_icon.png"
LOGO_PATH = CURRENT_DIR / "resources" / "images" / "LOGO_256.png"

# Formats
VIDEO_FORMATS = [
    "MP4",
    "MKV",
    "MOV",
    "AVI",
    "WEBM",
    "TS",
    "M2TS",
    "FLV",
    "SWF",
    "WMV",
    "MPG",
    "MPEG",
    "MXF",
    "VOB",
    "3GP",
    "3G2",
    "OGG",
    "OGV",
    "M4V",
    "NUT",
    "APNG",
    "ASF",
    "WTV",
    "IVF",
    "H264",
    "H265",
    "HEVC",
]
AUDIO_FORMATS = [
    "MP3",
    "AAC",
    "FLAC",
    "WAV",
    "OGG",
    "OPUS",
    "M4A",
    "WMA",
    "AIFF",
    "AC3",
    "DTS",
    "EAC3",
    "ALAC",
    "AMR",
    "MP2",
    "WV",
    "AU",
    "TTA",
]
# Output formats shown in the Image tab. Input-only formats (RAW camera
# files, PDF, PSD, SVG, HEIC, ...) are deliberately not offered as outputs:
# FFmpeg can read many of them but cannot encode them on a normal distribution.
IMAGE_FORMATS = [
    "JPG",
    "JPEG",
    "PNG",
    "WEBP",
    "GIF",
    "TIFF",
    "TIF",
    "AVIF",
    "BMP",
    "ICO",
    "TGA",
    "DPX",
    "PPM",
    "PBM",
    "PGM",
    "PAM",
    "PFM",
    "PCX",
    "SGI",
    "XWD",
    "SUN",
    "QOI",
]

IMAGE_INPUT_FORMATS = IMAGE_FORMATS + [
    "PSD",
    "SVG",
]

VIDEO_INPUT_FORMATS = VIDEO_FORMATS + [
    "MTS",
    "M2T",
    "F4V",
    "RM",
    "RMVB",
    "DIVX",
    "OGM",
    "DVR-MS",
    "DV",
    "GXF",
]

AUDIO_INPUT_FORMATS = AUDIO_FORMATS + [
    "M4B",
    "OGA",
    "SPX",
    "CAF",
    "APE",
    "MPC",
    "RA",
    "AIF",
    "AIFC",
]

# Audio codec that is safe in each video container. "copy" keeps the source
# stream (only used in ORIGINAL/COPY mode).
VIDEO_AUDIO_CODEC = {
    "mp4": "aac",
    "m4v": "aac",
    "mov": "aac",
    "mkv": "aac",
    "webm": "libopus",
    "avi": "libmp3lame",
    "ts": "aac",
    "m2ts": "aac",
    "flv": "aac",
    "swf": "libmp3lame",
    "wmv": "wmav2",
    "asf": "wmav2",
    "wtv": "wmav2",
    "mpg": "mp2",
    "mpeg": "mp2",
    "vob": "mp2",
    "mxf": "pcm_s16le",
    "gxf": "pcm_s16le",
    "dv": "pcm_s16le",
    "ogg": "libvorbis",
    "ogv": "libvorbis",
    "3gp": "aac",
    "3g2": "aac",
    "nut": "aac",
}

# Containers that cannot carry audio at all.
VIDEO_NO_AUDIO = {"h264", "h265", "hevc", "apng", "ivf"}

VIDEO_CODEC_MAP = {
    "WEBM": "libvpx-vp9",
    "WMV": "wmv2",
    "ASF": "wmv2",
    "WTV": "wmv2",
    "FLV": "flv",
    "SWF": "flv",
    "MPG": "mpeg1video",
    "MPEG": "mpeg1video",
    "VOB": "mpeg2video",
    "MXF": "mpeg2video",
    "GXF": "mpeg2video",
    "DV": "dvvideo",
    "APNG": "apng",
    "OGG": "libtheora",
    "OGV": "libtheora",
    "IVF": "libvpx",
    "H264": "libx264",
    "H265": "libx265",
    "HEVC": "libx265",
}

# Encoders that understand -crf/-preset. Others get a generic quality flag.
CRF_ENCODERS = {
    "libx264",
    "libx265",
    "libvpx",
    "libvpx-vp9",
    "libaom-av1",
    "libsvtav1",
}
PRESET_ENCODERS = {"libx264", "libx265"}

# Human-readable target resolution for the bitrate presets. The label in the
# UI promises a resolution, so actually scale to it instead of only setting a
# bitrate (the old behaviour made "KEEP ASPECT RATIO" a no-op).
VIDEO_RESOLUTIONS = {
    "8K (50M)": (7680, 4320),
    "4K (20M)": (3840, 2160),
    "1440P (10M)": (2560, 1440),
    "1080P (5M)": (1920, 1080),
    "720P (2M)": (1280, 720),
    "480P (1.5M)": (854, 480),
    "360P (1M)": (640, 360),
}


# Presets
AUDIO_SETTINGS = {
    "AAC": {
        "type": "bitrate",
        "options": ["320K", "256K", "192K", "128K", "96K", "64K"],
    },
    "OGG": {
        "type": "bitrate",
        # libvorbis rejects 256K/320K at common sample rates ("could not open
        # encoder"); 224K is the practical maximum and 192K is a safe default.
        "options": ["192K", "128K", "96K", "64K", "48K"],
    },
    "M4A": {
        "type": "bitrate",
        "options": ["320K", "256K", "192K", "128K", "96K", "64K"],
    },
    "WMA": {
        "type": "bitrate",
        "options": ["320K", "256K", "192K", "128K", "96K", "64K"],
    },
    "OPUS": {
        "type": "bitrate",
        "options": ["256K", "192K", "128K", "96K", "64K", "48K"],
    },
    "AC3": {
        "type": "bitrate",
        "options": ["640K", "448K", "384K", "256K", "192K", "128K"],
    },
    "DTS": {"type": "bitrate", "options": ["1536K", "768K", "512K"]},
    "EAC3": {"type": "bitrate", "options": ["768K", "640K", "448K", "384K", "256K"]},
    "AMR": {
        "type": "bitrate",
        "options": [
            "12.2K",
            "10.2K",
            "7.95K",
            "7.40K",
            "6.70K",
            "5.90K",
            "5.15K",
            "4.75K",
        ],
    },
    "MP2": {"type": "bitrate", "options": ["384K", "256K", "192K", "128K", "96K"]},
    "WAV": {
        "type": "samplerate",
        "options": [
            "192000 HZ",
            "96000 HZ",
            "48000 HZ",
            "44100 HZ",
            "32000 HZ",
            "22050 HZ",
            "16000 HZ",
        ],
    },
    "FLAC": {
        "type": "samplerate",
        "options": [
            "192000 HZ",
            "96000 HZ",
            "48000 HZ",
            "44100 HZ",
            "32000 HZ",
            "22050 HZ",
        ],
    },
    "AIFF": {
        "type": "samplerate",
        "options": [
            "192000 HZ",
            "96000 HZ",
            "48000 HZ",
            "44100 HZ",
            "32000 HZ",
            "22050 HZ",
        ],
    },
    "ALAC": {
        "type": "samplerate",
        "options": ["192000 HZ", "96000 HZ", "48000 HZ", "44100 HZ", "32000 HZ"],
    },
    "WV": {
        "type": "bitrate",
        "options": ["768K", "512K", "384K", "256K"],
    },
    "AU": {
        "type": "samplerate",
        "options": [
            "192000 HZ",
            "96000 HZ",
            "48000 HZ",
            "44100 HZ",
            "32000 HZ",
            "22050 HZ",
            "16000 HZ",
        ],
    },
    "TTA": {
        "type": "compression",
        "options": ["0 (FASTEST)", "1", "2", "3", "4 (BEST)"],
    },
}
MP3_CBR_OPTIONS = ["320K", "256K", "192K", "128K", "96K", "64K"]
MP3_VBR_OPTIONS = [
    "V0 (HIGHEST QUALITY)",
    "V1",
    "V2 (HIGH QUALITY)",
    "V3",
    "V4",
    "V5 (GOOD QUALITY)",
    "V6",
    "V7",
    "V8",
    "V9 (SMALLEST FILE)",
]

VIDEO_QUALITY_MODES = [
    "ORIGINAL (COPY)",
    "BITRATE (CBR/VBR AVG)",
    "CRF (CONSTANT QUALITY)",
]
CRF_OPTIONS = [
    "18 (HIGHEST QUALITY)",
    "20 (HIGH QUALITY)",
    "23 (GOOD - DEFAULT)",
    "25 (MEDIUM QUALITY)",
    "28 (LOW QUALITY)",
    "30 (LOWEST QUALITY)",
]

VIDEO_QUALITY_PRESETS = [
    "8K (50M)",
    "4K (20M)",
    "1440P (10M)",
    "1080P (5M)",
    "720P (2M)",
    "480P (1.5M)",
    "360P (1M)",
]

VIDEO_FRAME_RATE_PRESETS = [
    "ORIGINAL (COPY)",
    "60",
    "59.94",
    "50",
    "30",
    "29.97",
    "25",
    "24",
    "23.976",
    "15",
]

IMAGE_SIZE_PRESETS = [
    "ORIGINAL (COPY)",
    "7680X4320 (8K)",
    "2560X1440 (2K)",
    "1920X1080 (FULL HD)",
    "1280X720 (HD)",
    "854X480 (480P)",
    "640X360 (360P)",
    "CUSTOM (WXH)",
]

IMAGE_FILTERS = [
    "ORIGINAL (NO FILTER)",
    "GRAYSCALE (BLACK & WHITE)",
    "SHARPEN (BASIC)",
    "INVERT COLORS",
]

# Help
HELP_MESSAGES = {
    # Common - General
    "default": "Hover over any option to see what it does.",
    "browse_files": "Click Browse to select your input files.",
    "output_folder": "This folder will store your converted files.",
    "change_folder": "Click to choose a different output folder.",
    "open_folder": "Click to open the output folder.",
    "convert_btn": "Click to start converting your files to the selected format.",
    
    # Video Settings
    "video_format": "Choose the output video type (mp4, mkv, avi, etc).",
    "video_quality_mode": "Select quality mode: Original (fastest), Bitrate (fixed size), or CRF (fixed quality).",
    "video_quality_value": "Set target bitrate (like 5M) or CRF quality level (18=best, 23=default).",
    "video_framerate": "Set video speed (frames per second). Keep Original for fastest conversion.",
    "video_bitrate": "Target video quality using bitrate. Higher = better quality, bigger file.",
    "video_crf_value": "CRF sets quality. Lower number = better quality. Recommended: 18-23.",
    
    # Video Toggles
    "keep_aspect_ratio": "Keep original width-to-height proportions when resizing.",
    "apply_deinterlace": "Fix old video that looks wavy, blurry, or has lines.",
    "strip_metadata": "Remove hidden info like creation date, author, software name.",
    "remove_audio": "Remove sound track from video. Creates silent video.",
    "remove_video": "Keep only audio track. Creates audio-only WAV file.",
    
    # Audio Settings
    "audio_format": "Choose output audio type (mp3, wav, flac, aac, etc).",
    "mp3_mode": "CBR = same quality always. VBR = smaller file when audio is quiet.",
    "audio_quality": "Higher number = better quality, bigger file. Lower = smaller file.",
    "mp3_mode_cbr": "Constant Bitrate: Same quality throughout the file.",
    "mp3_mode_vbr": "Variable Bitrate: Quality adjusts to save space.",
    
    # Audio Toggles
    "apply_dithering": "Apply dither to reduce quantization noise in quiet sounds.",
    "apply_limiter": "Prevent audio from being too loud. Stops digital clipping.",
    
    # Image Settings
    "image_format": "Choose output image type (jpg, png, webp, etc).",
    "image_size": "Resize image. Choose preset or enter custom width x height.",
    "image_size_custom": "Enter your own width and height in pixels.",
    "visual_filter": "Apply visual effect: Original (none), Grayscale, Sharpen, or Invert Colors.",
    
    # Image Toggles
    "image_keep_aspect_ratio": "Keep original width-to-height proportions when resizing.",
    "image_compress": "Apply maximum compression to reduce file size.",
    "image_strip_metadata": "Remove hidden info like camera model, date taken.",
    
    # Theme
    "light_theme": "Switch interface to light colors (bright background).",
    "dark_theme": "Switch interface to dark colors (dark background).",
    "btn_light": "Click to switch to light mode.",
    "btn_dark": "Click to switch to dark mode.",
    "btn_audio": "Click to switch to Audio tab for audio conversion.",
    "btn_video": "Click to switch to Video tab for video conversion.",
    "btn_image": "Click to switch to Image tab for image conversion.",
}

# App
APP_CONFIG = {
    "WINDOW_SIZE": "1187x860",
    "FILE_DIALOG_SIZE": "850x638",
    "SIZE_DIALOG_SIZE": "400x300",
    "DEFAULT_OUTPUT_DIR": str(Path.home() / "Converted"),
    "THEME_COLORS": {
        "card_bg": ("#DBDBDB", "#2B2D30"),
        "text_primary": ("#666666", "#E0E0E0"),
        "text_secondary": ("#707070", "#A0A0A0"),
        "btn_inactive": ("#9E9E9E", "#3B4049"),
        "btn_hover": ("#666666", "#4F545C"),
        "btn_active_blue": ("#3B8ED0", "#1F6AA5"),
        "btn_hover_blue": ("#36719E", "#144870"),
        "btn_green": ("#2CC985", "#00A651"),
        "btn_green_hover": ("#25A86E", "#00803E"),
        "btn_cancel": ("#E05252", "#B33A3A"),
        "btn_cancel_hover": ("#C04040", "#8C2B2B"),
        "btn_open": ("#FF4D94", "#FF9500"),  # Light: Pink | Dark: Orange
        "btn_open_hover": ("#E63980", "#E68600"),  # Deeper shades for hover
        "input_bg": ("#F0F0F0", "#343638"),
        "transparent": "transparent",
        "white": "white",
        "green": "green",
    },
}


# Pure helpers (kept outside the GUI class so they can be unit-tested without
# a display).
def unique_output_path(
    directory: Path,
    stem: str,
    extension: str,
    reserved: Optional[set] = None,
) -> Path:
    """Return a non-existing output path, never silently overwriting a file.

    Two inputs such as ``clip.mp4`` and ``clip.mkv`` used to produce the same
    ``clip_converted.mp4`` and the second conversion overwrote the first one.
    ``reserved`` lets the caller reserve names before the files exist.
    """
    ext = extension.lower().lstrip(".")
    reserved = reserved if reserved is not None else set()

    candidate = directory / f"{stem}_converted.{ext}"
    counter = 1
    while candidate.exists() or candidate in reserved:
        candidate = directory / f"{stem}_converted_{counter}.{ext}"
        counter += 1

    reserved.add(candidate)
    return candidate


def parse_ffmpeg_progress(line: str) -> dict:
    """Parse one ``-progress pipe:1`` key/value line."""
    line = line.strip()
    if "=" not in line:
        return {}
    key, value = line.split("=", 1)
    if key in ("out_time_us", "out_time_ms"):
        try:
            return {"seconds": int(value) / 1_000_000}
        except ValueError:
            return {}
    if key == "out_time":
        match = re.fullmatch(r"(\d+):(\d+):(\d+(?:\.\d+)?)", value)
        if match:
            hours, minutes, seconds = match.groups()
            return {
                "seconds": int(hours) * 3600
                + int(minutes) * 60
                + float(seconds)
            }
    if key == "speed":
        return {"speed": value}
    if key == "progress":
        return {"progress": value}
    return {}


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


def tab_for_path(path: str) -> Optional[str]:
    """Guess which tab a file belongs to from its extension."""
    suffix = Path(path).suffix.lower().lstrip(".")
    checks = (
        ("Video", {ext.lower() for ext in VIDEO_INPUT_FORMATS}),
        ("Audio", {ext.lower() for ext in AUDIO_INPUT_FORMATS}),
        ("Image", {ext.lower() for ext in IMAGE_INPUT_FORMATS}),
    )
    for tab, extensions in checks:
        if suffix in extensions:
            return tab
    return None



# FileDialog
class CustomFileDialog(ctk.CTkToplevel):
    def __init__(
        self, parent, title: str = "Select Files", filetypes=None, initialdir=None
    ):
        super().__init__(parent)
        self.title(title)
        self.geometry(APP_CONFIG["FILE_DIALOG_SIZE"])
        self.transient(parent)

        self.result: Optional[List[str]] = None
        self.filetypes = filetypes or [("All Files", "*.*")]

        # FIX: Ensure initial directory is valid, otherwise fallback to Home
        init_path = Path(initialdir) if initialdir else Path.home()
        self.current_dir = init_path if init_path.exists() else Path.home()

        self.selected_files: List[str] = []
        self.clipboard_files: List[str] = []

        self._create_widgets()
        self._populate_tree()
        self._populate_file_list()
        self._bind_events()

    def _create_widgets(self):
        # Main frame
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Top frame for path and buttons
        top_frame = ctk.CTkFrame(main_frame)
        top_frame.pack(fill="x", padx=5, pady=5)

        self.path_entry = ctk.CTkEntry(top_frame, placeholder_text="Current directory")
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))

        # FIX: Bind Enter key to handle manual path typing
        self.path_entry.bind("<Return>", self._on_manual_path_entry)

        refresh_btn = ctk.CTkButton(
            top_frame,
            text="Refresh",
            command=self._refresh_all,
            width=80,
            text_color="white",
        )
        refresh_btn.pack(side="right", padx=(5, 0))

        # Content frame with tree and file list
        content_frame = ctk.CTkFrame(main_frame)
        content_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Tree view for folder navigation
        tree_frame = ctk.CTkFrame(content_frame, width=250)
        tree_frame.pack(side="left", fill="y", padx=(0, 5), pady=0)
        tree_frame.pack_propagate(False)

        tree_label = ctk.CTkLabel(
            tree_frame, text="Folders", font=ctk.CTkFont(weight="bold")
        )
        tree_label.pack(pady=(5, 0))

        # Create treeview using tkinter's Treeview
        from tkinter import ttk

        self.tree = ttk.Treeview(tree_frame, height=20, show="tree")
        self.tree.pack(fill="both", expand=True, padx=5, pady=5)

        # Configure tree colors to match application theme
        self._configure_tree_colors()

        # File list
        self.file_listbox = ctk.CTkScrollableFrame(content_frame)
        self.file_listbox.pack(
            side="right", fill="both", expand=True, padx=(5, 0), pady=0
        )

        # Status bar
        self.status_label = ctk.CTkLabel(
            main_frame, text="Ready to select files", anchor="w"
        )
        self.status_label.pack(fill="x", padx=5, pady=(0, 5))

        # Bottom buttons
        bottom_frame = ctk.CTkFrame(
            main_frame, fg_color=APP_CONFIG["THEME_COLORS"]["transparent"]
        )
        bottom_frame.pack(fill="x", padx=5, pady=5)

        cancel_btn = ctk.CTkButton(
            bottom_frame,
            text="Cancel",
            command=self._cancel,
            fg_color=APP_CONFIG["THEME_COLORS"]["btn_cancel"],
            hover_color=APP_CONFIG["THEME_COLORS"]["btn_cancel_hover"],
        )
        cancel_btn.pack(side="right", padx=(5, 0))

        ok_btn = ctk.CTkButton(
            bottom_frame, text="OK", command=self._ok, text_color="white"
        )
        ok_btn.pack(side="right")

    def _configure_tree_colors(self):
        # Configure the treeview colors to match the application theme
        style = ttk.Style()

        # Get current theme colors
        bg_color = (
            APP_CONFIG["THEME_COLORS"]["card_bg"][1]
            if ctk.get_appearance_mode() == "Dark"
            else APP_CONFIG["THEME_COLORS"]["card_bg"][0]
        )
        fg_color = (
            APP_CONFIG["THEME_COLORS"]["text_primary"][1]
            if ctk.get_appearance_mode() == "Dark"
            else APP_CONFIG["THEME_COLORS"]["text_primary"][0]
        )
        select_bg = (
            APP_CONFIG["THEME_COLORS"]["btn_active_blue"][1]
            if ctk.get_appearance_mode() == "Dark"
            else APP_CONFIG["THEME_COLORS"]["btn_active_blue"][0]
        )

        # Configure treeview style
        style.configure(
            "Treeview",
            background=bg_color,
            foreground=fg_color,
            fieldbackground=bg_color,
            borderwidth=0,
            font=("TkDefaultFont", 10),
        )

        style.configure(
            "Treeview.Heading", background=bg_color, foreground=fg_color, borderwidth=0
        )

        style.map(
            "Treeview",
            background=[("selected", select_bg)],
            foreground=[("selected", "white")],
        )

        # Remove borders and change selection colors
        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

    def _populate_file_list(self):
        # Clear existing widgets
        for widget in self.file_listbox.winfo_children():
            widget.destroy()

        try:
            # FIX: Only update the entry to reflect the current dir. DO NOT read from it here.
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, str(self.current_dir))

            # Add parent directory if not root
            if self.current_dir.parent != self.current_dir:
                parent_btn = ctk.CTkButton(
                    self.file_listbox,
                    text="..",
                    command=lambda: self._change_dir(self.current_dir.parent),
                    anchor="w",
                )
                parent_btn.pack(fill="x", padx=2, pady=1)

            # List directories first
            for item in sorted(self.current_dir.iterdir()):
                if item.is_dir():
                    btn = ctk.CTkButton(
                        self.file_listbox,
                        text=f"[DIR] {item.name}",
                        command=lambda p=item: self._change_dir(p),
                        anchor="w",
                        fg_color=APP_CONFIG["THEME_COLORS"]["transparent"],
                        hover_color=APP_CONFIG["THEME_COLORS"]["btn_inactive"],
                        text_color=APP_CONFIG["THEME_COLORS"]["text_primary"][1]
                        if ctk.get_appearance_mode() == "Dark"
                        else APP_CONFIG["THEME_COLORS"]["text_primary"][0],
                    )
                    btn.pack(fill="x", padx=2, pady=1)

            # Then files
            for item in sorted(self.current_dir.iterdir()):
                if item.is_file():
                    # Check if file matches any of the filetypes
                    if self._matches_filetype(item):
                        btn = ctk.CTkButton(
                            self.file_listbox,
                            text=item.name,
                            command=None,
                            anchor="w",
                            fg_color=APP_CONFIG["THEME_COLORS"]["transparent"],
                            text_color=APP_CONFIG["THEME_COLORS"]["text_primary"][1]
                            if ctk.get_appearance_mode() == "Dark"
                            else APP_CONFIG["THEME_COLORS"]["text_primary"][0],
                        )
                        btn.pack(fill="x", padx=2, pady=1)
                        # Store reference for selection highlighting
                        btn.file_path = item
                        # Bind single click to select single
                        btn.bind(
                            "<Button-1>", lambda e, p=item: self._select_file_single(p)
                        )
                        # Bind Ctrl+click to toggle multi-select
                        btn.bind(
                            "<Control-Button-1>", lambda e, p=item: self._toggle_file(p)
                        )

                        # FIX: Add double-click binding to select and close on a file
                        def on_file_double_click(event, path):
                            # Check if the file is currently selected (single-click toggles it)
                            if str(path) not in self.selected_files:
                                self._toggle_file(path)  # Select it if it wasn't
                            self._ok()  # Close the dialog

                        btn.bind(
                            "<Double-1>",
                            lambda e, path=item: on_file_double_click(e, path),
                        )

        except Exception as e:
            error_label = ctk.CTkLabel(
                self.file_listbox, text=f"Error accessing folder: {e}"
            )
            error_label.pack(padx=5, pady=5)

    def _on_manual_path_entry(self, event):
        # FIX: Handle manually typing path and hitting Enter
        try:
            new_path = Path(self.path_entry.get())
            if new_path.exists() and new_path.is_dir():
                self._change_dir(new_path)
            else:
                self.status_label.configure(text="Invalid directory path")
                # Reset entry to current valid dir
                self.path_entry.delete(0, "end")
                self.path_entry.insert(0, str(self.current_dir))
        except Exception:
            pass

    def _matches_filetype(self, file_path: Path) -> bool:
        """Check if file matches any of the allowed filetypes."""
        if not self.filetypes:
            return True

        file_ext = file_path.suffix.lower().lstrip(".")

        for desc, pattern in self.filetypes:
            # Allow all files if pattern is *.*
            if pattern == "*.*":
                return True

            # Handle patterns with spaces (multiple extensions like "*.mp4 *.mkv")
            patterns = pattern.split()
            for p in patterns:
                # Remove *. prefix and compare extension
                if p.startswith("*."):
                    allowed_ext = p[2:].lower()
                    if file_ext == allowed_ext:
                        return True

        return False

    def _change_dir(self, new_dir: Path):
        self.current_dir = new_dir
        self._populate_file_list()

    def _toggle_file(self, file_path: Path):
        if str(file_path) in self.selected_files:
            self.selected_files.remove(str(file_path))
        else:
            self.selected_files.append(str(file_path))
        self._update_selection_display()

    def _select_file_single(self, file_path: Path):
        self.selected_files = [str(file_path)]
        self._update_selection_display()

    def _update_selection_display(self):
        # Update button colors to show selection
        for widget in self.file_listbox.winfo_children():
            if hasattr(widget, "file_path"):
                if str(widget.file_path) in self.selected_files:
                    widget.configure(
                        fg_color=APP_CONFIG["THEME_COLORS"]["btn_active_blue"]
                    )
                else:
                    widget.configure(fg_color=APP_CONFIG["THEME_COLORS"]["transparent"])

        self.status_label.configure(text=f"Selected: {len(self.selected_files)} files")

    def _bind_events(self):
        self.bind("<Control-a>", lambda e: self._select_all())
        self.bind("<Control-c>", lambda e: self._copy_files())
        self.bind("<Control-v>", lambda e: self._paste_files())
        self.bind("<Delete>", lambda e: self._delete_to_trash())
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self._cancel())
        self.bind(
            "<BackSpace>",
            lambda e: (
                self._change_dir(self.current_dir.parent)
                if self.current_dir.parent != self.current_dir
                else None
            ),
        )
        self.bind("<F5>", lambda e: self._refresh_all())
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<<TreeviewOpen>>", self._on_tree_expand)

    def _select_all(self):
        self.selected_files = [
            str(item)
            for item in self.current_dir.iterdir()
            if item.is_file() and self._matches_filetype(item)
        ]
        self._update_selection_display()

    def _copy_files(self):
        self.clipboard_files = self.selected_files.copy()
        self.status_label.configure(
            text=f"Copied {len(self.clipboard_files)} files to clipboard"
        )

    def _paste_files(self):
        # For now, just show a message - actual file copying would require more implementation
        if self.clipboard_files:
            self.status_label.configure(
                text=f"Would paste {len(self.clipboard_files)} files (not implemented)"
            )
        else:
            self.status_label.configure(text="No files in clipboard")

    def _delete_to_trash(self):
        # Simplified for safety
        if not self.selected_files:
            return
        if not messagebox.askyesno(
            "Delete", f"Move {len(self.selected_files)} files to trash?"
        ):
            return

        if not SEND2TRASH_AVAILABLE:
            messagebox.showerror(
                "Safe Deletion Unavailable",
                "The 'send2trash' library is missing. Safe deletion cannot be performed.",
            )
            return

        deleted = 0
        for f in self.selected_files:
            try:
                send2trash(f)
                deleted += 1
            except Exception:
                pass

        if deleted:
            self.selected_files = []
            self._populate_file_list()

    def _delete_permanently(self):
        # Permanently delete selected files
        if not self.selected_files:
            self.status_label.configure(text="No files selected for deletion")
            return

        # Confirm permanent deletion
        file_count = len(self.selected_files)
        file_names = [Path(f).name for f in self.selected_files]
        names_display = ", ".join(file_names[:3]) + (
            "..." if len(file_names) > 3 else ""
        )

        if not messagebox.askyesno(
            "Permanent Delete",
            f"Permanently delete {file_count} file(s)?\n{names_display}\n\nThis action cannot be undone!",
        ):
            return

        deleted_count = 0
        failed_files = []

        for file_path in self.selected_files:
            try:
                path_obj = Path(file_path)
                if path_obj.is_file():
                    path_obj.unlink()  # Delete file
                elif path_obj.is_dir():
                    import shutil

                    shutil.rmtree(path_obj)  # Delete directory
                deleted_count += 1
            except Exception as e:
                failed_files.append(Path(file_path).name)
                print(f"Error deleting {file_path}: {e}")

        # Update UI
        if deleted_count > 0:
            self.status_label.configure(
                text=f"Permanently deleted {deleted_count} file(s)"
            )
            # Refresh the file list
            self._populate_file_list()
            # Clear selection
            self.selected_files = []
            self._update_selection_display()
        else:
            self.status_label.configure(text="Failed to delete files")

        if failed_files:
            messagebox.showerror(
                "Delete Error",
                f"Failed to delete: {', '.join(failed_files[:5])}{'...' if len(failed_files) > 5 else ''}",
            )

    def _ok(self):
        self.result = self.selected_files
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()

    def _populate_tree(self):
        # Populate the tree view with the folder structure starting from the current directory
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Add root directory
        root_path = Path.home()
        root_node = self.tree.insert(
            "", "end", text=str(root_path), open=True, values=[str(root_path)]
        )

        # Populate the tree starting from root
        self._populate_tree_recursive(root_node, root_path)

        # Expand current directory path
        self._expand_to_current_dir()

    def _populate_tree_recursive(self, parent_node, path: Path, max_depth=2):
        # Recursively populate tree nodes with directories
        try:
            if path.exists() and path.is_dir():
                # Limit depth to prevent excessive loading
                current_depth = len(
                    self.tree.item(parent_node, "values")[0].split(os.sep)
                ) - len(str(Path.home()).split(os.sep))
                if current_depth >= max_depth:
                    return

                for item in sorted(path.iterdir()):
                    if item.is_dir() and not item.name.startswith(
                        "."
                    ):  # Skip hidden directories
                        node = self.tree.insert(
                            parent_node, "end", text=item.name, values=[str(item)]
                        )
                        # Add dummy child to make it expandable
                        self.tree.insert(node, "end", text="", values=[""])
        except (PermissionError, OSError):
            # Skip directories we can't access
            pass

    def _expand_to_current_dir(self):
        # Simplified expansion
        pass

    def _on_tree_select(self, event):
        # Handle tree selection - change directory when a folder is selected
        selected_items = self.tree.selection()
        if selected_items:
            selected_item = selected_items[0]
            item_values = self.tree.item(selected_item, "values")
            if item_values:
                selected_path = Path(item_values[0])
                if selected_path.exists() and selected_path.is_dir():
                    self._change_dir(selected_path)

    def _on_tree_expand(self, event):
        # Handle tree expansion - populate children when a node is expanded
        # Get the item that was expanded
        expanded_item = self.tree.focus()
        if expanded_item:
            item_values = self.tree.item(expanded_item, "values")
            if item_values:
                expanded_path = Path(item_values[0])
                # Check if this node has dummy children that need to be replaced
                children = self.tree.get_children(expanded_item)
                if (
                    children and not self.tree.item(children[0], "values")[0]
                ):  # Dummy child
                    # Remove dummy child
                    self.tree.delete(children[0])
                    # Populate real children
                    self._populate_tree_recursive(expanded_item, expanded_path)

    def _refresh_all(self):
        # Refresh both tree and file list
        self._populate_tree()
        self._populate_file_list()

    @classmethod
    def askopenfilenames(
        cls, parent, title="Select Files", filetypes=None, initialdir=None
    ) -> Optional[List[str]]:
        dialog = cls(parent, title, filetypes, initialdir)
        dialog.wait_window()
        return dialog.result


# DirDialog
class CustomDirectoryDialog(ctk.CTkToplevel):
    def __init__(self, parent, title: str = "Select Directory", initialdir=None):
        super().__init__(parent)
        self.title(title)
        self.geometry(APP_CONFIG["FILE_DIALOG_SIZE"])
        self.transient(parent)

        self.result: Optional[str] = None

        # FIX: Ensure initial directory is valid, otherwise fallback to Home
        init_path = Path(initialdir) if initialdir else Path.home()
        self.current_dir = init_path if init_path.exists() else Path.home()

        self._create_widgets()
        self._populate_tree()
        self._populate_dir_list()
        self._bind_events()

    def _create_widgets(self):
        # Main frame
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Top frame for path and buttons
        top_frame = ctk.CTkFrame(main_frame)
        top_frame.pack(fill="x", padx=5, pady=5)

        self.path_entry = ctk.CTkEntry(top_frame, placeholder_text="Current directory")
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))

        # FIX: Bind Enter key to handle manual path typing
        self.path_entry.bind("<Return>", self._on_manual_path_entry)

        refresh_btn = ctk.CTkButton(
            top_frame,
            text="Refresh",
            command=self._refresh_all,
            width=80,
            text_color="white",
        )
        refresh_btn.pack(side="right", padx=(5, 0))

        # Content frame with tree and dir list
        content_frame = ctk.CTkFrame(main_frame)
        content_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Tree view for folder navigation
        tree_frame = ctk.CTkFrame(content_frame, width=250)
        tree_frame.pack(side="left", fill="y", padx=(0, 5), pady=0)
        tree_frame.pack_propagate(False)

        tree_label = ctk.CTkLabel(
            tree_frame, text="Folders", font=ctk.CTkFont(weight="bold")
        )
        tree_label.pack(pady=(5, 0))

        # Create treeview using tkinter's Treeview
        from tkinter import ttk

        self.tree = ttk.Treeview(tree_frame, height=20, show="tree")
        self.tree.pack(fill="both", expand=True, padx=5, pady=5)

        # Configure tree colors to match application theme
        self._configure_tree_colors()

        # Directory list
        self.dir_listbox = ctk.CTkScrollableFrame(content_frame)
        self.dir_listbox.pack(
            side="right", fill="both", expand=True, padx=(5, 0), pady=0
        )

        # Status bar
        self.status_label = ctk.CTkLabel(
            main_frame, text="Select a directory", anchor="w"
        )
        self.status_label.pack(fill="x", padx=5, pady=(0, 5))

        # Bottom buttons
        bottom_frame = ctk.CTkFrame(
            main_frame, fg_color=APP_CONFIG["THEME_COLORS"]["transparent"]
        )
        bottom_frame.pack(fill="x", padx=5, pady=5)

        cancel_btn = ctk.CTkButton(
            bottom_frame,
            text="Cancel",
            command=self._cancel,
            fg_color=APP_CONFIG["THEME_COLORS"]["btn_cancel"],
            hover_color=APP_CONFIG["THEME_COLORS"]["btn_cancel_hover"],
        )
        cancel_btn.pack(side="right", padx=(5, 0))

        ok_btn = ctk.CTkButton(
            bottom_frame, text="OK", command=self._ok, text_color="white"
        )
        ok_btn.pack(side="right")

    def _configure_tree_colors(self):
        # Configure the treeview colors to match the application theme
        style = ttk.Style()

        # Get current theme colors
        bg_color = (
            APP_CONFIG["THEME_COLORS"]["card_bg"][1]
            if ctk.get_appearance_mode() == "Dark"
            else APP_CONFIG["THEME_COLORS"]["card_bg"][0]
        )
        fg_color = (
            APP_CONFIG["THEME_COLORS"]["text_primary"][1]
            if ctk.get_appearance_mode() == "Dark"
            else APP_CONFIG["THEME_COLORS"]["text_primary"][0]
        )
        select_bg = (
            APP_CONFIG["THEME_COLORS"]["btn_active_blue"][1]
            if ctk.get_appearance_mode() == "Dark"
            else APP_CONFIG["THEME_COLORS"]["btn_active_blue"][0]
        )

        # Configure treeview style
        style.configure(
            "Treeview",
            background=bg_color,
            foreground=fg_color,
            fieldbackground=bg_color,
            borderwidth=0,
            font=("TkDefaultFont", 10),
        )

        style.configure(
            "Treeview.Heading", background=bg_color, foreground=fg_color, borderwidth=0
        )

        style.map(
            "Treeview",
            background=[("selected", select_bg)],
            foreground=[("selected", "white")],
        )

        # Remove borders and change selection colors
        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

    def _populate_dir_list(self):
        # Clear existing widgets
        for widget in self.dir_listbox.winfo_children():
            widget.destroy()

        try:
            # FIX: Only update the entry to reflect the current dir. DO NOT read from it here.
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, str(self.current_dir))

            # Add parent directory if not root
            if self.current_dir.parent != self.current_dir:
                parent_btn = ctk.CTkButton(
                    self.dir_listbox,
                    text="..",
                    command=lambda: self._change_dir(self.current_dir.parent),
                    anchor="w",
                )
                parent_btn.pack(fill="x", padx=2, pady=1)

            # List directories
            for item in sorted(self.current_dir.iterdir()):
                if item.is_dir():
                    btn = ctk.CTkButton(
                        self.dir_listbox,
                        text=f"[DIR] {item.name}",
                        command=lambda p=item: self._select_dir(p),
                        anchor="w",
                        fg_color=APP_CONFIG["THEME_COLORS"]["transparent"],
                        hover_color=APP_CONFIG["THEME_COLORS"]["btn_inactive"],
                        text_color=APP_CONFIG["THEME_COLORS"]["text_primary"][1]
                        if ctk.get_appearance_mode() == "Dark"
                        else APP_CONFIG["THEME_COLORS"]["text_primary"][0],
                    )
                    btn.pack(fill="x", padx=2, pady=1)

        except Exception as e:
            error_label = ctk.CTkLabel(
                self.dir_listbox, text=f"Error accessing folder: {e}"
            )
            error_label.pack(padx=5, pady=5)

    def _on_manual_path_entry(self, event):
        # FIX: Handle manually typing path and hitting Enter
        try:
            new_path = Path(self.path_entry.get())
            if new_path.exists() and new_path.is_dir():
                self._change_dir(new_path)
            else:
                self.status_label.configure(text="Invalid directory path")
                # Reset entry to current valid dir
                self.path_entry.delete(0, "end")
                self.path_entry.insert(0, str(self.current_dir))
        except Exception:
            pass

    def _change_dir(self, new_dir: Path):
        self.current_dir = new_dir
        self._populate_dir_list()

    def _select_dir(self, dir_path: Path):
        self.result = str(dir_path)
        self.destroy()

    def _bind_events(self):
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self._cancel())
        self.bind(
            "<BackSpace>",
            lambda e: (
                self._change_dir(self.current_dir.parent)
                if self.current_dir.parent != self.current_dir
                else None
            ),
        )
        self.bind("<F5>", lambda e: self._refresh_all())
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<<TreeviewOpen>>", self._on_tree_expand)

    def _ok(self):
        self.result = str(self.current_dir)
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()

    def _populate_tree(self):
        # Populate the tree view with the folder structure starting from the current directory
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Add root directory
        root_path = Path.home()
        root_node = self.tree.insert(
            "", "end", text=str(root_path), open=True, values=[str(root_path)]
        )

        # Populate the tree starting from root
        self._populate_tree_recursive(root_node, root_path)

        # Expand current directory path
        self._expand_to_current_dir()

    def _populate_tree_recursive(self, parent_node, path: Path, max_depth=2):
        # Recursively populate tree nodes with directories
        try:
            if path.exists() and path.is_dir():
                # Limit depth to prevent excessive loading
                current_depth = len(
                    self.tree.item(parent_node, "values")[0].split(os.sep)
                ) - len(str(Path.home()).split(os.sep))
                if current_depth >= max_depth:
                    return

                for item in sorted(path.iterdir()):
                    if item.is_dir() and not item.name.startswith(
                        "."
                    ):  # Skip hidden directories
                        node = self.tree.insert(
                            parent_node, "end", text=item.name, values=[str(item)]
                        )
                        # Add dummy child to make it expandable
                        self.tree.insert(node, "end", text="", values=[""])
        except (PermissionError, OSError):
            # Skip directories we can't access
            pass

    def _expand_to_current_dir(self):
        # Simplified expansion
        pass

    def _on_tree_select(self, event):
        # Handle tree selection - change directory when a folder is selected
        selected_items = self.tree.selection()
        if selected_items:
            selected_item = selected_items[0]
            item_values = self.tree.item(selected_item, "values")
            if item_values:
                selected_path = Path(item_values[0])
                if selected_path.exists() and selected_path.is_dir():
                    self._change_dir(selected_path)

    def _on_tree_expand(self, event):
        # Handle tree expansion - populate children when a node is expanded
        # Get the item that was expanded
        expanded_item = self.tree.focus()
        if expanded_item:
            item_values = self.tree.item(expanded_item, "values")
            if item_values:
                expanded_path = Path(item_values[0])
                # Check if this node has dummy children that need to be replaced
                children = self.tree.get_children(expanded_item)
                if (
                    children and not self.tree.item(children[0], "values")[0]
                ):  # Dummy child
                    # Remove dummy child
                    self.tree.delete(children[0])
                    # Populate real children
                    self._populate_tree_recursive(expanded_item, expanded_path)

    def _refresh_all(self):
        # Refresh both tree and dir list
        self._populate_tree()
        self._populate_dir_list()

    @classmethod
    def askdirectory(
        cls, parent, title="Select Directory", initialdir=None
    ) -> Optional[str]:
        dialog = cls(parent, title, initialdir)
        dialog.wait_window()
        return dialog.result


# SizeDialog
class CustomSizeDialog(ctk.CTkToplevel):
    def __init__(self, parent, title: str = "Enter Custom Resolution"):
        super().__init__(parent)
        # Initializes a dialog window for entering custom image width and height.
        self.title(title)
        self.geometry(APP_CONFIG["SIZE_DIALOG_SIZE"])
        self.transient(parent)
        self.grab_set()

        self._center_window(parent)
        self.result: Optional[Tuple[str, str]] = None

        self._create_widgets()
        self._bind_events()

    def _center_window(self, parent):
        # Centers the dialog window relative to its parent.
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

    def _create_widgets(self):
        # Sets up the input fields and OK/Cancel buttons.
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        main_frame = ctk.CTkFrame(self)
        main_frame.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        main_frame.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(
            main_frame, text="WIDTH (W):", font=ctk.CTkFont(weight="bold")
        ).grid(row=0, column=0, padx=10, pady=(10, 5), sticky="w")
        self.width_entry = ctk.CTkEntry(main_frame, placeholder_text="e.g., 1920")
        self.width_entry.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")

        ctk.CTkLabel(
            main_frame, text="HEIGHT (H):", font=ctk.CTkFont(weight="bold")
        ).grid(row=0, column=1, padx=10, pady=(10, 5), sticky="w")
        self.height_entry = ctk.CTkEntry(main_frame, placeholder_text="e.g., 1920")
        self.height_entry.grid(row=1, column=1, padx=10, pady=(0, 10), sticky="ew")

        ctk.CTkButton(
            main_frame, text="OK", command=self._ok_action, text_color="white"
        ).grid(row=2, column=0, padx=10, pady=10, sticky="ew")
        ctk.CTkButton(
            main_frame,
            text="CANCEL",
            command=self._cancel_action,
            fg_color=APP_CONFIG["THEME_COLORS"]["btn_inactive"],
            hover_color=APP_CONFIG["THEME_COLORS"]["btn_hover"],
            text_color="white",
        ).grid(row=2, column=1, padx=10, pady=10, sticky="ew")

    def _bind_events(self):
        # Binds keyboard events (Enter/Escape) for action shortcuts.
        self.bind("<Return>", lambda _: self._ok_action())
        self.bind("<Escape>", lambda _: self._cancel_action())
        self.width_entry.focus_set()

    def _ok_action(self):
        # Validates input, sets result tuple, and closes the dialog.
        try:
            W = int(self.width_entry.get().strip())
            H = int(self.height_entry.get().strip())
        except ValueError:
            messagebox.showerror(
                "Invalid size",
                "Enter positive whole numbers for width and height.",
                parent=self,
            )
            return

        if W <= 0 or H <= 0:
            messagebox.showerror(
                "Invalid size",
                "Width and height must be greater than zero.",
                parent=self,
            )
            return

        self.result = (str(W), str(H))
        if self.winfo_exists():
            self.destroy()

    def _cancel_action(self):
        # Clears the result and closes the dialog.
        self.result = None
        if self.winfo_exists():
            self.destroy()

    def show(self) -> Optional[Tuple[str, str]]:
        # Displays the dialog and waits for user interaction, returning the result.
        self.wait_window()
        return self.result


class FFConverterApp(CTkDnD):
    def __init__(self):
        super().__init__()

        self.title("FFConverter")
        self.geometry(APP_CONFIG["WINDOW_SIZE"])
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=1)

        if not TKINTERDND_AVAILABLE and os.environ.get("FFCONVERTER_DEBUG"):
            print("Warning: Drag-and-drop disabled (tkinterdnd2 is not installed)")

        if not SEND2TRASH_AVAILABLE and os.environ.get("FFCONVERTER_DEBUG"):
            print("Warning: Safe deletion disabled (send2trash is not installed)")

        if not PYSTRAY_AVAILABLE and os.environ.get("FFCONVERTER_DEBUG"):
            print("Warning: System tray icon disabled (pystray/pillow missing)")

        # Vars
        default_msg = "FILE NOT SELECTED. CLICK ON BROWSE TO SELECT FILES"
        self.video_input_path = ctk.StringVar(value=default_msg)
        self.audio_input_path = ctk.StringVar(value=default_msg)
        self.image_input_path = ctk.StringVar(value=default_msg)
        self.output_dir = ctk.StringVar(value=APP_CONFIG["DEFAULT_OUTPUT_DIR"])

        # Store actual file paths for conversion (separate from display text)
        self.selected_video_files: List[str] = []
        self.selected_audio_files: List[str] = []
        self.selected_image_files: List[str] = []

        # UI variable initialization for Video, Audio, and Image conversion settings.
        self.video_format = ctk.StringVar(value=VIDEO_FORMATS[0])
        self.video_quality_mode = ctk.StringVar(value=VIDEO_QUALITY_MODES[0])
        self.video_quality_value = ctk.StringVar(value="1080P (5M)")
        self.video_frame_rate = ctk.StringVar(value="ORIGINAL (COPY)")
        self.video_keep_aspect_ratio = ctk.BooleanVar(value=True)
        self.video_deinterlace = ctk.BooleanVar(value=False)
        self.video_strip_metadata = ctk.BooleanVar(value=False)
        self.video_remove_audio = ctk.BooleanVar(value=False)
        self.video_remove_video = ctk.BooleanVar(value=False)

        self.audio_format = ctk.StringVar(value=AUDIO_FORMATS[0])
        self.audio_quality = ctk.StringVar(value="320K")
        self.audio_dithering = ctk.BooleanVar(value=False)
        self.audio_limiter = ctk.BooleanVar(value=False)
        self.audio_strip_metadata = ctk.BooleanVar(value=False)
        self.mp3_mode = ctk.StringVar(value="CBR")

        self.image_format = ctk.StringVar(value=IMAGE_FORMATS[0])
        self.image_size = ctk.StringVar(value="ORIGINAL (COPY)")
        self.custom_image_dims: Optional[Tuple[str, str]] = None
        self.image_keep_aspect_ratio = ctk.BooleanVar(value=True)
        self.image_strip_metadata = ctk.BooleanVar(value=False)
        self.image_compress = ctk.BooleanVar(value=False)
        self.image_visual_filter = ctk.StringVar(value=IMAGE_FILTERS[0])

        self.video_progress_bar = None
        self.video_convert_btn = None
        self.audio_progress_bar = None
        self.audio_convert_btn = None
        self.image_progress_bar = None
        self.image_convert_btn = None

        # State variable for current tab (replaced tab_view.get())
        self.current_tab_name = "Audio"  # Default
        self.nav_buttons = {}  # Store buttons to update colors

        # Holds the active FFmpeg subprocess (one at a time).
        self.active_conversion_process: Optional[subprocess.Popen] = None

        # Conversion state. Batch files are processed sequentially by one
        # worker thread; the UI is only updated from the Tk main thread.
        self.conversion_running = False
        self.cancel_requested = False
        self.conversion_thread: Optional[object] = None
        self.ui_queue: "queue.Queue" = queue.Queue()
        self.converted_files_count = 0
        self.total_files_to_convert = 0

        self.last_input_dir = str(Path.home())

        self.common_widgets = {tab: {} for tab in ["Video", "Audio", "Image"]}
        self.video_tab_initialized = False
        self.audio_tab_initialized = True  # Audio is default, always initialized
        self.image_tab_initialized = False

        # Optional tray icon subprocess.
        self.tray_process = None
        self.tray_dir = None
        self.tray_stop = threading.Event()
        self.tray_monitor_thread = None

        # Tab variables for drag-and-drop
        self.tab_variables = {
            "Video": {"input": self.video_input_path, "extensions": "video formats"},
            "Audio": {"input": self.audio_input_path, "extensions": "audio formats"},
            "Image": {"input": self.image_input_path, "extensions": "image formats"},
        }

        self.folder_icon = self._load_folder_icon()
        self._create_widgets()
        self.after(50, self._process_ui_queue)
        self.after(250, self._check_environment)
        if PYSTRAY_AVAILABLE:
            self.after(500, self._setup_tray_icon)

    # UI Helpers
    def _create_toggle_button(self, parent, text, variable, command=None, width=None):
        """Creates a toggle button that acts like a checkbox."""

        def toggle_action():
            # Toggle the boolean variable
            new_state = not variable.get()
            variable.set(new_state)
            update_visuals()
            if command:
                command()

        def update_visuals(*args):
            # Update color based on state
            if variable.get():
                btn.configure(
                    fg_color=APP_CONFIG["THEME_COLORS"]["btn_active_blue"],
                    hover_color=APP_CONFIG["THEME_COLORS"]["btn_hover_blue"],
                    text_color=APP_CONFIG["THEME_COLORS"]["white"],
                )
            else:
                # Use white text for inactive buttons in LIGHT mode to match active button text color
                btn.configure(
                    fg_color=APP_CONFIG["THEME_COLORS"]["btn_inactive"],
                    hover_color=APP_CONFIG["THEME_COLORS"]["btn_hover"],
                    text_color=APP_CONFIG["THEME_COLORS"]["white"],
                )

        # Initial Button Creation
        btn = ctk.CTkButton(
            parent,
            text=text,
            command=toggle_action,
            font=ctk.CTkFont(size=12, weight="bold"),
            height=32,
            corner_radius=6,
        )

        if width:
            btn.configure(width=width)

        # Set initial state
        update_visuals()

        # Trace variable changes (so if changed programmatically, button updates)
        # Note: We need to keep a reference to the trace to avoid garbage collection issues if needed,
        # but for simple UI this is usually fine.
        variable.trace_add("write", update_visuals)

        return btn

    def _create_card(self, parent, row, column, columnspan=1, rowspan=1, title=None):
        """Creates a card-like frame with an optional title."""
        card = ctk.CTkFrame(
            parent, fg_color=APP_CONFIG["THEME_COLORS"]["card_bg"], corner_radius=10
        )
        card.grid(
            row=row,
            column=column,
            columnspan=columnspan,
            rowspan=rowspan,
            padx=10,
            pady=5,
            sticky="nsew",
        )  # Reduced pady from 10 to 5

        # Grid configuration for the card itself
        card.grid_columnconfigure(0, weight=1)

        current_row = 0
        if title:
            title_label = ctk.CTkLabel(
                card,
                text=title,
                font=ctk.CTkFont(size=9, weight="bold"),
                text_color=APP_CONFIG["THEME_COLORS"]["text_primary"],
                anchor="center",
            )
            title_label.grid(
                row=0, column=0, columnspan=4, padx=15, pady=(15, 5), sticky="ew"
            )
            card.title_label = title_label
            current_row = 1

        return card, current_row

    def _create_section_header(self, parent, text, row, column, columnspan=1):
        """Creates a distinct section header."""
        label = ctk.CTkLabel(
            parent,
            text=text,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=APP_CONFIG["THEME_COLORS"]["text_primary"],
        )
        label.grid(
            row=row,
            column=column,
            columnspan=columnspan,
            padx=10,
            pady=(20, 5),
            sticky="w",
        )
        return label

    # Thread-safe UI helpers
    def _post(self, callback):
        """Queue a callback for execution in the Tk main thread."""
        self.ui_queue.put(callback)

    def _process_ui_queue(self):
        try:
            while True:
                callback = self.ui_queue.get_nowait()
                try:
                    callback()
                except Exception as exc:  # keep the event loop alive
                    print(f"[UI] callback failed: {exc}")
        except queue.Empty:
            pass
        finally:
            if self.winfo_exists():
                self.after(50, self._process_ui_queue)

    def _set_status(self, tab_name: str, message: str, is_error: bool = False):
        widgets = self.common_widgets.get(tab_name, {})
        label = widgets.get("help_text_label")
        if label is not None:
            try:
                label.configure(
                    text=message,
                    text_color=(
                        APP_CONFIG["THEME_COLORS"]["btn_cancel"]
                        if is_error
                        else APP_CONFIG["THEME_COLORS"]["text_primary"]
                    ),
                )
            except Exception:
                pass

    def _set_progress(self, tab_name: str, value: Optional[float]):
        bar = {
            "Video": self.video_progress_bar,
            "Audio": self.audio_progress_bar,
            "Image": self.image_progress_bar,
        }.get(tab_name)
        if bar is None:
            return
        try:
            if value is None:
                bar.start()
            else:
                bar.stop()
                bar.set(max(0.0, min(1.0, value)))
        except Exception:
            pass

    def _set_convert_button(self, mode: str, converting: bool):
        button = {
            "Video": self.video_convert_btn,
            "Audio": self.audio_convert_btn,
            "Image": self.image_convert_btn,
        }.get(mode)
        if button is None:
            return

        if converting:
            button.configure(
                text="CANCEL",
                command=self._cancel_conversion,
                fg_color=APP_CONFIG["THEME_COLORS"]["btn_cancel"],
                hover_color=APP_CONFIG["THEME_COLORS"]["btn_cancel_hover"],
                state="normal",
            )
        else:
            button.configure(
                text="CONVERT",
                command=lambda: self._start_conversion(mode),
                fg_color=APP_CONFIG["THEME_COLORS"]["btn_green"],
                hover_color=APP_CONFIG["THEME_COLORS"]["btn_green_hover"],
                state="normal",
            )

    def _check_environment(self):
        if not ffmpeg_available():
            message = (
                "FFmpeg was not found. Install it (sudo apt install ffmpeg / "
                "sudo dnf install ffmpeg) or use a build with bundled FFmpeg."
            )
            for tab in ("Video", "Audio", "Image"):
                self._set_status(tab, f"Status: {message}", is_error=True)
            return

        if not Path(FFPROBE_PATH).is_file() and shutil.which("ffprobe") is None:
            self._set_status(
                self.current_tab_name,
                "Status: FFmpeg found, but ffprobe is missing. "
                "Conversion works, progress percentage may be unavailable.",
            )

    def _set_selected_files(self, tab_name: str, files: List[str], message: str = ""):
        files = [str(path) for path in files]
        if tab_name == "Video":
            self.selected_video_files = files
        elif tab_name == "Audio":
            self.selected_audio_files = files
        elif tab_name == "Image":
            self.selected_image_files = files
        else:
            return

        names = [Path(path).name for path in files]
        if len(names) == 1:
            display = f"Selected: {names[0]}"
        else:
            display = f"Selected {len(names)} files: {names[0]}..."

        if len(display) > 80:
            display = display[:77] + "..."
        self.tab_variables[tab_name]["input"].set(display)

        if message:
            self._set_status(tab_name, message)
        elif files:
            self._set_status(
                tab_name,
                f"Status: {len(files)} file(s) selected for {tab_name}. Ready.",
            )

    def load_files_from_args(self, paths: List[str]):
        """Open files passed by the desktop file / command line."""
        files = [str(Path(path).expanduser()) for path in paths]
        files = [path for path in files if Path(path).is_file()]
        if not files:
            return

        first_tab = tab_for_path(files[0])
        if first_tab is None:
            messagebox.showwarning(
                "Unsupported file",
                "The file type is not supported. Open it from the appropriate "
                "Video, Audio, or Image tab instead.",
            )
            return

        valid, rejected = self._validate_files(files, first_tab)
        self._change_tab(first_tab)
        if valid:
            self._set_selected_files(first_tab, valid)
        if rejected:
            self._set_status(
                first_tab,
                f"Status: {len(rejected)} file(s) ignored because they do not "
                f"match the {first_tab} tab.",
                is_error=True,
            )

    # Load Icon
    def _load_folder_icon(self) -> Optional[ctk.CTkImage]:
        # Attempts to load a folder icon image using PIL for the 'Open Folder' button.
        try:
            from PIL import Image

            for path in (FOLDER_ICON_PATH, LOGO_PATH):
                if path.exists():
                    img = Image.open(path)
                    return ctk.CTkImage(
                        light_image=img, dark_image=img, size=(20, 20)
                    )
        except Exception as e:
            if os.environ.get("FFCONVERTER_DEBUG"):
                print(f"Warning: Could not load folder icon: {e}")
        return None

    # Create UI
    def _create_widgets(self):
        # Sets up the custom tab navigation and content frames.

        # 0. Top Header Frame (Theme Toggler)
        self.top_header = ctk.CTkFrame(
            self, fg_color=APP_CONFIG["THEME_COLORS"]["transparent"]
        )
        self.top_header.grid(row=0, column=0, padx=20, pady=(5, 15), sticky="ew")
        self.top_header.grid_columnconfigure(0, weight=1)

        # 1. Navigation Frame (Tabs)
        self.nav_frame = ctk.CTkFrame(
            self, fg_color=APP_CONFIG["THEME_COLORS"]["card_bg"], corner_radius=10
        )
        self.nav_frame.grid(row=1, column=0, padx=10, pady=(0, 5), sticky="ew")
        self.nav_frame.grid_columnconfigure(0, weight=1)
        self.nav_frame.grid_columnconfigure(1, weight=1)
        self.nav_frame.grid_columnconfigure(2, weight=1)

        # 2. Content Frame (Bottom)
        self.content_frame = ctk.CTkFrame(
            self, fg_color=APP_CONFIG["THEME_COLORS"]["transparent"]
        )
        self.content_frame.grid(row=2, column=0, padx=0, pady=(0, 0), sticky="nsew")
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(0, weight=1)

        # 3. Create Content Tabs (Frames)
        self.audio_tab = ctk.CTkFrame(
            self.content_frame,
            corner_radius=0,
            fg_color=APP_CONFIG["THEME_COLORS"]["transparent"],
        )
        self.video_tab = ctk.CTkFrame(
            self.content_frame,
            corner_radius=0,
            fg_color=APP_CONFIG["THEME_COLORS"]["transparent"],
        )
        self.image_tab = ctk.CTkFrame(
            self.content_frame,
            corner_radius=0,
            fg_color=APP_CONFIG["THEME_COLORS"]["transparent"],
        )

        # Grid all tabs once at startup (will use tkraise() for switching)
        for tab in [self.audio_tab, self.video_tab, self.image_tab]:
            tab.grid(row=0, column=0, sticky="nsew")

        # 4. Create Navigation Buttons
        # Using separate buttons for maximum control over positioning/styling
        self.btn_audio = ctk.CTkButton(
            self.nav_frame,
            text="AUDIO",
            command=lambda: self._change_tab("Audio"),
            font=ctk.CTkFont(size=14, weight="bold"),
            height=32,
            border_width=0,
            border_spacing=10,
            text_color="white",
        )
        self.btn_audio.grid(row=0, column=0, padx=(25, 5), pady=25, sticky="ew")

        self.btn_video = ctk.CTkButton(
            self.nav_frame,
            text="VIDEO",
            command=lambda: self._change_tab("Video"),
            font=ctk.CTkFont(size=14, weight="bold"),
            height=32,
            border_width=0,
            border_spacing=10,
            text_color="white",
        )
        self.btn_video.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        self.btn_image = ctk.CTkButton(
            self.nav_frame,
            text="IMAGE",
            command=lambda: self._change_tab("Image"),
            font=ctk.CTkFont(size=14, weight="bold"),
            height=32,
            border_width=0,
            border_spacing=10,
            text_color="white",
        )
        self.btn_image.grid(row=0, column=2, padx=(5, 25), pady=25, sticky="ew")

        self.nav_buttons = {
            "Audio": self.btn_audio,
            "Video": self.btn_video,
            "Image": self.btn_image,
        }

        # Grid configuration for tabs
        for tab in [self.audio_tab, self.video_tab, self.image_tab]:
            tab.grid_columnconfigure(0, weight=1)
            tab.grid_rowconfigure((0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 11), weight=0)
            tab.grid_rowconfigure(9, weight=1)

        self._setup_audio_tab()
        self.audio_tab_initialized = True  # Audio is default
        self._bind_help_text_for_tab("Audio")
        self._setup_theme_toggler()
        self._setup_drag_and_drop()

        # Note: FFmpeg check deferred to first conversion attempt for faster startup

        # Initialize with Audio tab (already set up above)
        self._change_tab("Audio")

    def _change_tab(self, tab_name: str):
        self.current_tab_name = tab_name

        # Lazy-load Video/Image tabs on first access
        if tab_name == "Video" and not self.video_tab_initialized:
            self.video_tab_initialized = True
            main_frame = ctk.CTkFrame(
                self.video_tab, fg_color=APP_CONFIG["THEME_COLORS"]["card_bg"], corner_radius=10
            )
            main_frame.grid(row=0, column=0, padx=10, pady=5, sticky="nsew")
            main_frame.grid_columnconfigure(0, weight=1)
            self._setup_video_tab_content(main_frame)
            self._bind_help_text_for_tab("Video")
        elif tab_name == "Image" and not self.image_tab_initialized:
            self.image_tab_initialized = True
            main_frame = ctk.CTkFrame(
                self.image_tab, fg_color=APP_CONFIG["THEME_COLORS"]["card_bg"], corner_radius=10
            )
            main_frame.grid(row=0, column=0, padx=10, pady=5, sticky="nsew")
            main_frame.grid_columnconfigure(0, weight=1)
            self._setup_image_tab_content(main_frame)
            self._bind_help_text_for_tab("Image")

        # Update button colors first (batch update before showing new tab)
        active_color = APP_CONFIG["THEME_COLORS"]["btn_active_blue"]
        inactive_color = APP_CONFIG["THEME_COLORS"]["btn_inactive"]

        for name, btn in self.nav_buttons.items():
            btn.configure(
                fg_color=active_color if name == tab_name else inactive_color
            )

        # Update Content using tkraise() - much faster than grid_forget()/grid()
        # as it only changes Z-order without recalculating layouts
        if tab_name == "Audio":
            self.audio_tab.tkraise()
        elif tab_name == "Video":
            self.video_tab.tkraise()
        elif tab_name == "Image":
            self.image_tab.tkraise()

    # Help Text
    def _update_help_text(self, tab_key: str, key: str):
        # Changes the text in the help/tooltip label based on hover events.
        if "help_text_label" in self.common_widgets.get(tab_key, {}):
            self.common_widgets[tab_key]["help_text_label"].configure(
                text=HELP_MESSAGES.get(key, HELP_MESSAGES["default"])
            )

    # Common Tab
    def _create_common_tab_widgets(self, tab_name, tab_frame):
        # Creates the common widgets for a specific tab: Input File card, Output Folder card, and Help frame.
        # Configure grid for the tab content
        tab_frame.grid_columnconfigure(0, weight=1)

        # --- Input Section Card ---
        input_card, r = self._create_card(
            tab_frame, row=0, column=0, title="PLEASE SELECT YOUR INPUT FILE"
        )
        input_card.grid_configure(pady=5)
        input_card.grid_columnconfigure(0, weight=1)

        # Store reference to input card
        self.common_widgets[tab_name]["input_card"] = input_card

        input_var = None
        if tab_name == "Video":
            input_var = self.video_input_path
        elif tab_name == "Audio":
            input_var = self.audio_input_path
        elif tab_name == "Image":
            input_var = self.image_input_path

        if input_var is None:
            return

        browse_button = ctk.CTkButton(
            input_card,
            text="BROWSE",
            command=self._select_input_file,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=APP_CONFIG["THEME_COLORS"]["btn_active_blue"],
            hover_color=APP_CONFIG["THEME_COLORS"]["btn_hover_blue"],
            text_color="white",
        )
        browse_button.grid(row=r, column=0, padx=15, pady=(5, 10), sticky="ew")
        self.common_widgets[tab_name]["browse_button"] = browse_button

        input_label = ctk.CTkLabel(
            input_card,
            textvariable=input_var,
            anchor="center",
            wraplength=700,
            text_color=APP_CONFIG["THEME_COLORS"]["text_secondary"],
        )
        input_label.grid(row=r + 1, column=0, padx=15, pady=(0, 15), sticky="ew")
        self.common_widgets[tab_name]["input_label"] = input_label

        # --- Output Section Card (Reordered to Row 7) ---
        output_card, r_out = self._create_card(
            tab_frame, row=7, column=0, title="OUTPUT FOLDER SETTINGS"
        )
        output_card.grid_configure(pady=5)
        output_card.grid_columnconfigure(0, weight=7)
        output_card.grid_columnconfigure(1, weight=2)
        output_card.grid_columnconfigure(2, weight=1)

        self.common_widgets[tab_name]["output_card"] = output_card

        output_entry = ctk.CTkEntry(
            output_card,
            textvariable=self.output_dir,
            state="readonly",
            fg_color=APP_CONFIG["THEME_COLORS"]["input_bg"],
            border_width=2,
            border_color=APP_CONFIG["THEME_COLORS"]["white"],
        )
        output_entry.grid(
            row=r_out, column=0, padx=(15, 5), pady=(15, 15), sticky="ew"
        )  # Increased top pady since label is gone
        self.common_widgets[tab_name]["output_entry"] = output_entry

        change_btn = ctk.CTkButton(
            output_card,
            text="CHANGE",
            command=self._select_output_directory,
            width=100,
            fg_color=APP_CONFIG["THEME_COLORS"]["btn_inactive"],
            hover_color=APP_CONFIG["THEME_COLORS"]["btn_hover"],
            text_color="white",
        )
        change_btn.grid(row=r_out, column=1, padx=(5, 5), pady=(15, 15), sticky="ew")
        self.common_widgets[tab_name]["change_btn"] = change_btn

        open_btn = ctk.CTkButton(
            output_card,
            text="OPEN" if not self.folder_icon else "",
            image=self.folder_icon if self.folder_icon else None,
            width=50,
            command=self._open_output_directory,
            fg_color=APP_CONFIG["THEME_COLORS"]["btn_open"],
            hover_color=APP_CONFIG["THEME_COLORS"]["btn_open_hover"],
            text_color=APP_CONFIG["THEME_COLORS"][
                "white"
            ],  # Keeps text readable on both pink and orange
        )
        open_btn.grid(row=r_out, column=2, padx=(5, 15), pady=(15, 15), sticky="ew")
        self.common_widgets[tab_name]["open_btn"] = open_btn

        # Help Frame (Row 9 - Just above Output)
        # We'll make this less intrusive, maybe just a status line or a small card
        help_frame = ctk.CTkFrame(
            tab_frame, fg_color=APP_CONFIG["THEME_COLORS"]["transparent"], height=30
        )
        help_frame.grid(
            row=9, column=0, columnspan=3, padx=10, pady=(5, 20), sticky="ew"
        )
        help_frame.grid_columnconfigure(0, weight=1)

        help_text_label = ctk.CTkLabel(
            help_frame,
            text=HELP_MESSAGES["default"],
            anchor="center",
            justify="center",
            wraplength=750,
            text_color=APP_CONFIG["THEME_COLORS"]["text_secondary"],
            font=ctk.CTkFont(size=12, slant="italic"),
        )
        help_text_label.grid(row=0, column=0, padx=10, pady=5, sticky="ew")
        self.common_widgets[tab_name]["help_text_label"] = help_text_label

    # Video Tab
    def _setup_video_tab(self):
        # Configures the specific widgets for video conversion options.
        # Creates main frame and defers content creation for lazy loading.
        tab_name = "Video"
        tab = self.video_tab

        main_frame = ctk.CTkFrame(
            tab, fg_color=APP_CONFIG["THEME_COLORS"]["card_bg"], corner_radius=10
        )
        main_frame.grid(row=0, column=0, padx=10, pady=5, sticky="nsew")
        main_frame.grid_columnconfigure(0, weight=1)

        self._setup_video_tab_content(main_frame)

    def _setup_video_tab_content(self, main_frame):
        # Builds video tab content into existing main_frame (for lazy loading)
        tab_name = "Video"
        # main_frame already passed in from _change_tab lazy loading

        # Create common widgets first
        self._create_common_tab_widgets(tab_name, main_frame)

        # --- Conversion Settings Card ---
        settings_card, r = self._create_card(
            main_frame,
            row=1,
            column=0,
            title="HERE ARE THE SETTINGS FOR YOUR DESIRED VIDEO OUTPUT",
        )

        # Configure columns for the settings card
        settings_card.grid_columnconfigure(0, weight=1, uniform="video")
        settings_card.grid_columnconfigure(1, weight=1, uniform="video")
        settings_card.grid_columnconfigure(2, weight=1, uniform="video")
        settings_card.grid_columnconfigure(3, weight=1, uniform="video")

        # Option menus for Format, Quality Mode, Quality Value, and Framerate.
        format_label = ctk.CTkLabel(
            settings_card,
            text="CONTAINER (CODEC):",
            text_color=APP_CONFIG["THEME_COLORS"]["text_primary"],
        )
        format_label.grid(row=r, column=0, padx=15, pady=(5, 5), sticky="w")
        self.common_widgets[tab_name]["format_label"] = format_label

        format_menu = ctk.CTkOptionMenu(
            settings_card, values=VIDEO_FORMATS, variable=self.video_format
        )
        format_menu.grid(row=r + 1, column=0, padx=(15, 5), pady=(0, 15), sticky="ew")
        self.common_widgets[tab_name]["format_menu"] = format_menu

        quality_mode_label = ctk.CTkLabel(
            settings_card,
            text="QUALITY MODE:",
            text_color=APP_CONFIG["THEME_COLORS"]["text_primary"],
        )
        quality_mode_label.grid(row=r, column=1, padx=5, pady=(5, 5), sticky="w")
        self.common_widgets[tab_name]["quality_mode_label"] = quality_mode_label

        self.video_quality_mode_menu = ctk.CTkOptionMenu(
            settings_card,
            values=VIDEO_QUALITY_MODES,
            variable=self.video_quality_mode,
            command=self._update_video_options,
        )
        self.video_quality_mode_menu.grid(
            row=r + 1, column=1, padx=5, pady=(0, 15), sticky="ew"
        )
        self.common_widgets[tab_name]["quality_mode_menu"] = (
            self.video_quality_mode_menu
        )

        self.quality_value_label = ctk.CTkLabel(
            settings_card,
            text="TARGET VALUE:",
            text_color=APP_CONFIG["THEME_COLORS"]["text_primary"],
        )
        self.quality_value_label.grid(row=r, column=2, padx=5, pady=(5, 5), sticky="w")
        self.common_widgets[tab_name]["quality_value_label"] = self.quality_value_label

        self.video_quality_value_menu = ctk.CTkOptionMenu(
            settings_card,
            values=["ORIGINAL (COPY)"] + VIDEO_QUALITY_PRESETS,
            variable=self.video_quality_value,
        )
        self.video_quality_value_menu.grid(
            row=r + 1, column=2, padx=5, pady=(0, 15), sticky="ew"
        )
        self.common_widgets[tab_name]["quality_value_menu"] = (
            self.video_quality_value_menu
        )

        self._update_video_options(None)

        framerate_label = ctk.CTkLabel(
            settings_card,
            text="FRAME RATE (FPS):",
            text_color=APP_CONFIG["THEME_COLORS"]["text_primary"],
        )
        framerate_label.grid(row=r, column=3, padx=(5, 15), pady=(5, 5), sticky="w")
        self.common_widgets[tab_name]["framerate_label"] = framerate_label

        framerate_menu = ctk.CTkOptionMenu(
            settings_card,
            values=VIDEO_FRAME_RATE_PRESETS,
            variable=self.video_frame_rate,
        )
        framerate_menu.grid(
            row=r + 1, column=3, padx=(5, 15), pady=(0, 15), sticky="ew"
        )
        self.common_widgets[tab_name]["framerate_menu"] = framerate_menu

        # --- Filters Card ---
        filters_card, r_filt = self._create_card(
            main_frame,
            row=2,
            column=0,
            title="HERE ARE SOME ADVANCED FILTERS YOU CAN CHOOSE FROM",
        )
        filters_card.title_label.grid_configure(
            columnspan=5
        )  # Update to span all 5 columns for proper centering

        filters_card.grid_columnconfigure(0, weight=1, uniform="video")
        filters_card.grid_columnconfigure(1, weight=1, uniform="video")
        filters_card.grid_columnconfigure(2, weight=1, uniform="video")
        filters_card.grid_columnconfigure(3, weight=1, uniform="video")
        filters_card.grid_columnconfigure(4, weight=1, uniform="video")

        ar_cb = self._create_toggle_button(
            filters_card, "KEEP ASPECT RATIO", self.video_keep_aspect_ratio
        )
        ar_cb.grid(row=r_filt, column=0, padx=(15, 5), pady=(10, 15), sticky="ew")
        self.common_widgets[tab_name]["ar_cb"] = ar_cb

        di_cb = self._create_toggle_button(
            filters_card, "DEINTERLACE", self.video_deinterlace
        )
        di_cb.grid(row=r_filt, column=1, padx=5, pady=(10, 15), sticky="ew")
        self.common_widgets[tab_name]["di_cb"] = di_cb

        sm_cb = self._create_toggle_button(
            filters_card, "STRIP METADATA", self.video_strip_metadata
        )
        sm_cb.grid(row=r_filt, column=2, padx=5, pady=(10, 15), sticky="ew")
        self.common_widgets[tab_name]["sm_cb"] = sm_cb

        # Remove Audio/Video - Two Separate Buttons with Mutual Exclusion (both on same row)
        ra_cb = self._create_toggle_button(
            filters_card,
            "REMOVE AUDIO",
            self.video_remove_audio,
            command=lambda: (
                self.video_remove_video.set(False)
                if self.video_remove_audio.get()
                else None
            ),
        )
        ra_cb.grid(row=r_filt, column=3, padx=5, pady=(10, 15), sticky="ew")
        self.common_widgets[tab_name]["ra_cb"] = ra_cb

        rv_cb = self._create_toggle_button(
            filters_card,
            "REMOVE VIDEO",
            self.video_remove_video,
            command=lambda: (
                self.video_remove_audio.set(False)
                if self.video_remove_video.get()
                else None
            ),
        )
        rv_cb.grid(row=r_filt, column=4, padx=(5, 15), pady=(10, 15), sticky="ew")
        self.common_widgets[tab_name]["rv_cb"] = rv_cb

        # Convert button and progress bar.
        # Moved to Row 8 (Below Filters)
        action_frame = ctk.CTkFrame(
            main_frame, fg_color=APP_CONFIG["THEME_COLORS"]["card_bg"], corner_radius=10
        )
        action_frame.grid(
            row=8, column=0, columnspan=3, padx=10, pady=(2, 10), sticky="ew"
        )
        action_frame.grid_columnconfigure(0, weight=1)

        self.video_convert_btn = ctk.CTkButton(
            action_frame,
            text="CONVERT",
            command=lambda: self._start_conversion("Video"),
            height=50,
            corner_radius=8,
            font=ctk.CTkFont(size=18, weight="bold"),
            fg_color=APP_CONFIG["THEME_COLORS"]["btn_green"],
            hover_color=APP_CONFIG["THEME_COLORS"]["btn_green_hover"],
            text_color="white",
        )  # Green for action
        self.video_convert_btn.grid(row=0, column=0, padx=15, pady=(10, 5), sticky="ew")

        self.video_progress_bar = ctk.CTkProgressBar(
            action_frame, orientation="horizontal", height=15, corner_radius=8
        )
        self.video_progress_bar.grid(
            row=1, column=0, padx=15, pady=(5, 10), sticky="ew"
        )
        self.video_progress_bar.set(0)

    # Update Video
    def _update_video_options(self, *args):
        # Adjusts the available quality options (Bitrate vs. CRF) based on the selected mode.
        selected_mode = self.video_quality_mode.get()
        current_value = self.video_quality_value.get()

        options = []
        label_text = "VALUE:"

        if selected_mode == "ORIGINAL (COPY)":
            options = ["(N/A)"]
            label_text = "COPY MODE ACTIVE:"
            self.video_quality_value_menu.configure(state="disabled")
        elif selected_mode == "BITRATE (CBR/VBR AVG)":
            options = VIDEO_QUALITY_PRESETS
            label_text = "TARGET BITRATE:"
            self.video_quality_value_menu.configure(state="normal")
        elif selected_mode == "CRF (CONSTANT QUALITY)":
            options = CRF_OPTIONS
            label_text = "CRF VALUE (LOWER = HIGHER QUALITY):"
            self.video_quality_value_menu.configure(state="normal")

        self.quality_value_label.configure(text=label_text)
        self.video_quality_value_menu.configure(values=options)

        if current_value not in options:
            if selected_mode == "ORIGINAL (COPY)":
                self.video_quality_value.set(options[0])
            elif selected_mode == "CRF (CONSTANT QUALITY)":
                self.video_quality_value.set("23 (GOOD - DEFAULT)")
            elif selected_mode == "BITRATE (CBR/VBR AVG)":
                self.video_quality_value.set(
                    "1080P (5M)"
                    if "1080P (5M)" in options
                    else options[0]
                )
            elif options:
                self.video_quality_value.set(options[0])
            else:
                self.video_quality_value.set("")

    # Audio Tab
    def _setup_audio_tab(self):
        # Configures the specific widgets for audio conversion options.
        tab_name = "Audio"
        tab = self.audio_tab

        # Create main frame for the tab content
        main_frame = ctk.CTkFrame(
            tab, fg_color=APP_CONFIG["THEME_COLORS"]["card_bg"], corner_radius=10
        )
        main_frame.grid(row=0, column=0, padx=10, pady=5, sticky="nsew")
        main_frame.grid_columnconfigure(0, weight=1)

        # Create common widgets first
        self._create_common_tab_widgets(tab_name, main_frame)

        # Reorder for audio: output below filters and above convert
        output_card = self.common_widgets[tab_name]["output_card"]
        output_card.grid_configure(row=4, pady=5)

        # --- Audio Settings Card ---
        # Note: We assign self.audio_options_frame to this card so dynamic updates work
        self.audio_options_frame, r = self._create_card(
            main_frame,
            row=2,
            column=0,
            title="HERE ARE THE SETTINGS FOR YOUR DESIRED AUDIO OUTPUT",
        )

        self.audio_options_frame.grid_columnconfigure(0, weight=1, uniform="audio")
        self.audio_options_frame.grid_columnconfigure(1, weight=1, uniform="audio")
        self.audio_options_frame.grid_columnconfigure(2, weight=1, uniform="audio")

        # Option menus for Format, MP3 Mode, and Audio Quality/Sample Rate.
        self.format_label = ctk.CTkLabel(
            self.audio_options_frame,
            text="OUTPUT FORMAT (CODEC):",
            text_color=APP_CONFIG["THEME_COLORS"]["text_primary"],
        )
        self.format_menu = ctk.CTkOptionMenu(
            self.audio_options_frame,
            values=AUDIO_FORMATS,
            variable=self.audio_format,
            command=self._update_audio_options,
        )
        self.common_widgets[tab_name]["format_label"] = self.format_label
        self.common_widgets[tab_name]["format_menu"] = self.format_menu

        self.mp3_mode_label = ctk.CTkLabel(
            self.audio_options_frame,
            text="MP3 MODE (CBR/VBR):",
            text_color=APP_CONFIG["THEME_COLORS"]["text_primary"],
        )
        self.mp3_mode_menu = ctk.CTkOptionMenu(
            self.audio_options_frame,
            values=["CBR", "VBR"],
            variable=self.mp3_mode,
            command=self._update_audio_options,
        )
        self.common_widgets[tab_name]["mp3_mode_label"] = self.mp3_mode_label
        self.common_widgets[tab_name]["mp3_mode_menu"] = self.mp3_mode_menu

        self.audio_quality_label = ctk.CTkLabel(
            self.audio_options_frame,
            text="AUDIO QUALITY:",
            text_color=APP_CONFIG["THEME_COLORS"]["text_primary"],
        )
        self.audio_quality_menu = ctk.CTkOptionMenu(
            self.audio_options_frame,
            values=MP3_CBR_OPTIONS,
            variable=self.audio_quality,
        )
        self.common_widgets[tab_name]["audio_quality_label"] = self.audio_quality_label
        self.common_widgets[tab_name]["audio_quality_menu"] = self.audio_quality_menu

        # --- Filters Card ---
        filters_card, r_filt = self._create_card(
            main_frame,
            row=3,
            column=0,
            title="HERE ARE SOME ADVANCED FILTERS YOU CAN CHOOSE FROM",
        )

        filters_card.grid_columnconfigure(0, weight=1, uniform="audio")
        filters_card.grid_columnconfigure(1, weight=1, uniform="audio")
        filters_card.grid_columnconfigure(2, weight=1, uniform="audio")

        dithering_cb = self._create_toggle_button(
            filters_card, "APPLY DITHERING", self.audio_dithering
        )
        dithering_cb.grid(
            row=r_filt, column=0, padx=(15, 5), pady=(10, 15), sticky="ew"
        )
        self.common_widgets[tab_name]["dithering_cb"] = dithering_cb

        limiter_cb = self._create_toggle_button(
            filters_card, "APPLY PEAK LIMITER", self.audio_limiter
        )
        limiter_cb.grid(row=r_filt, column=1, padx=5, pady=(10, 15), sticky="ew")
        self.common_widgets[tab_name]["limiter_cb"] = limiter_cb

        sm_cb = self._create_toggle_button(
            filters_card, "STRIP METADATA", self.audio_strip_metadata
        )
        sm_cb.grid(row=r_filt, column=2, padx=(5, 15), pady=(10, 15), sticky="ew")
        self.common_widgets[tab_name]["sm_cb"] = sm_cb

        self._update_audio_options(self.audio_format.get())

        # Convert button and progress bar.
        # Convert button and progress bar.
        action_frame = ctk.CTkFrame(
            main_frame, fg_color=APP_CONFIG["THEME_COLORS"]["card_bg"], corner_radius=10
        )
        action_frame.grid(row=5, column=0, columnspan=3, padx=10, pady=5, sticky="ew")
        action_frame.grid_columnconfigure(0, weight=1)

        self.audio_convert_btn = ctk.CTkButton(
            action_frame,
            text="CONVERT",
            command=lambda: self._start_conversion("Audio"),
            height=50,
            corner_radius=8,
            font=ctk.CTkFont(size=18, weight="bold"),
            fg_color=APP_CONFIG["THEME_COLORS"]["btn_green"],
            hover_color=APP_CONFIG["THEME_COLORS"]["btn_green_hover"],
            text_color="white",
        )
        self.audio_convert_btn.grid(row=0, column=0, padx=15, pady=(10, 5), sticky="ew")

        self.audio_progress_bar = ctk.CTkProgressBar(
            action_frame, orientation="horizontal", height=15, corner_radius=8
        )
        self.audio_progress_bar.grid(
            row=1, column=0, padx=15, pady=(5, 10), sticky="ew"
        )
        self.audio_progress_bar.set(0)

    # Update Audio
    def _update_audio_options(self, *args):
        # Updates the quality options (Bitrate/Sample Rate, CBR/VBR) and layout based on selected format.
        selected_format = self.audio_format.get()
        selected_mode = self.mp3_mode.get()

        # Always show format label and menu in consistent 3-column layout
        self.format_label.configure(
            text="OUTPUT FORMAT (CODEC):",
            text_color=APP_CONFIG["THEME_COLORS"]["text_primary"],
        )
        self.format_label.grid(row=1, column=0, padx=15, pady=(5, 5), sticky="w")

        # Handle MP3 Mode widgets visibility
        if selected_format == "MP3":
            # Show MP3 mode widgets
            self.mp3_mode_label.grid(row=1, column=1, padx=5, pady=(5, 5), sticky="w")
            self.mp3_mode_menu.grid(row=2, column=1, padx=5, pady=(0, 15), sticky="ew")
            # Format menu spans only 1 column when MP3 mode is visible
            self.format_menu.grid(
                row=2, column=0, padx=(15, 5), pady=(0, 15), sticky="ew"
            )

            label_text = (
                "CONSTANT BITRATE (CBR):"
                if selected_mode == "CBR"
                else "VARIABLE QUALITY (VBR):"
            )
            options = MP3_CBR_OPTIONS if selected_mode == "CBR" else MP3_VBR_OPTIONS
        else:
            # Hide MP3 mode widgets
            self.mp3_mode_label.grid_forget()
            self.mp3_mode_menu.grid_forget()
            # Format menu spans 2 columns when MP3 mode is hidden
            self.format_menu.grid(
                row=2, column=0, columnspan=2, padx=(15, 5), pady=(0, 15), sticky="ew"
            )

            if selected_format in AUDIO_SETTINGS:
                settings = AUDIO_SETTINGS[selected_format]
                options = settings["options"]
                label_text = (
                    "SAMPLE RATE:"
                    if settings["type"] == "samplerate"
                    else "AUDIO BITRATE:"
                )
            else:
                options = ["320K", "192K", "128K", "64K"]
                label_text = "AUDIO BITRATE:"

        # Always show quality widgets in column 2
        self.audio_quality_label.configure(
            text=label_text, text_color=APP_CONFIG["THEME_COLORS"]["text_primary"]
        )
        self.audio_quality_label.grid(
            row=1, column=2, padx=(5, 15), pady=(5, 5), sticky="w"
        )
        self.audio_quality_menu.grid(
            row=2, column=2, padx=(5, 15), pady=(0, 15), sticky="ew"
        )

        self.audio_quality_menu.configure(values=options)
        if self.audio_quality.get() not in options:
            self.audio_quality.set(options[0])

    # Image Tab
    def _setup_image_tab(self):
        # Configures the specific widgets for image conversion options.
        # Creates main frame and defers content creation for lazy loading.
        tab_name = "Image"
        tab = self.image_tab

        main_frame = ctk.CTkFrame(
            tab, fg_color=APP_CONFIG["THEME_COLORS"]["card_bg"], corner_radius=10
        )
        main_frame.grid(row=0, column=0, padx=10, pady=5, sticky="nsew")
        main_frame.grid_columnconfigure(0, weight=1)

        self._setup_image_tab_content(main_frame)

    def _setup_image_tab_content(self, main_frame):
        # Builds image tab content into existing main_frame (for lazy loading)
        tab_name = "Image"
        # main_frame already passed in from _change_tab lazy loading

        # Create common widgets first
        self._create_common_tab_widgets(tab_name, main_frame)

        # Swap output folder and conversion button for image
        output_card = self.common_widgets[tab_name]["output_card"]
        output_card.grid_configure(row=3, pady=5)

        # --- Image Settings Card ---
        settings_card, r = self._create_card(
            main_frame,
            row=1,
            column=0,
            title="HERE ARE THE SETTINGS FOR YOUR DESIRED IMAGE OUTPUT",
        )

        settings_card.grid_columnconfigure(0, weight=1, uniform="image")
        settings_card.grid_columnconfigure(1, weight=1, uniform="image")
        settings_card.grid_columnconfigure(2, weight=1, uniform="image")

        # Option menus for Format, Size, and Visual Filter.
        format_label = ctk.CTkLabel(
            settings_card,
            text="CONVERT TO:",
            text_color=APP_CONFIG["THEME_COLORS"]["text_primary"],
        )
        format_label.grid(row=r, column=0, padx=15, pady=(5, 5), sticky="w")

        size_label = ctk.CTkLabel(
            settings_card,
            text="RESIZE IMAGE:",
            text_color=APP_CONFIG["THEME_COLORS"]["text_primary"],
        )
        size_label.grid(row=r, column=1, padx=5, pady=(5, 5), sticky="w")

        vf_label = ctk.CTkLabel(
            settings_card,
            text="VISUAL FILTER:",
            text_color=APP_CONFIG["THEME_COLORS"]["text_primary"],
        )
        vf_label.grid(row=r, column=2, padx=5, pady=(5, 5), sticky="w")

        format_menu = ctk.CTkOptionMenu(
            settings_card, values=IMAGE_FORMATS, variable=self.image_format
        )
        format_menu.grid(row=r + 1, column=0, padx=(15, 5), pady=(0, 15), sticky="ew")

        self.image_size_menu = ctk.CTkOptionMenu(
            settings_card,
            values=IMAGE_SIZE_PRESETS,
            variable=self.image_size,
            command=self._handle_image_size_change,
        )
        self.image_size_menu.grid(
            row=r + 1, column=1, padx=5, pady=(0, 15), sticky="ew"
        )

        vf_menu = ctk.CTkOptionMenu(
            settings_card, values=IMAGE_FILTERS, variable=self.image_visual_filter
        )

        vf_menu.grid(row=r + 1, column=2, padx=(5, 15), pady=(0, 15), sticky="ew")

        # Store widgets for help bindings
        self.common_widgets[tab_name]["image_format_label"] = format_label
        self.common_widgets[tab_name]["image_format_menu"] = format_menu
        self.common_widgets[tab_name]["image_size_label"] = size_label
        self.common_widgets[tab_name]["image_size_menu"] = self.image_size_menu
        self.common_widgets[tab_name]["vf_label"] = vf_label
        self.common_widgets[tab_name]["vf_menu"] = vf_menu

        # --- Filters Card ---
        filters_card, r_filt = self._create_card(
            main_frame,
            row=2,
            column=0,
            title="HERE ARE SOME ADVANCED FILTERS YOU CAN CHOOSE FROM",
        )

        filters_card.grid_columnconfigure(0, weight=1, uniform="image_filter")
        filters_card.grid_columnconfigure(1, weight=1, uniform="image_filter")
        filters_card.grid_columnconfigure(2, weight=1, uniform="image_filter")

        ar_cb = self._create_toggle_button(
            filters_card, "KEEP ASPECT RATIO", self.image_keep_aspect_ratio
        )
        ar_cb.grid(row=r_filt, column=0, padx=(15, 5), pady=(10, 15), sticky="ew")

        compress_cb = self._create_toggle_button(
            filters_card, "COMPRESS (REDUCE SIZE)", self.image_compress
        )
        compress_cb.grid(row=r_filt, column=1, padx=5, pady=(10, 15), sticky="ew")

        sm_cb = self._create_toggle_button(
            filters_card, "STRIP METADATA", self.image_strip_metadata
        )
        sm_cb.grid(row=r_filt, column=2, padx=(5, 15), pady=(10, 15), sticky="ew")

        # Store toggle buttons for help bindings
        self.common_widgets[tab_name]["ar_cb"] = ar_cb
        self.common_widgets[tab_name]["compress_cb"] = compress_cb
        self.common_widgets[tab_name]["sm_cb"] = sm_cb

        # Convert button and progress bar.
        action_frame = ctk.CTkFrame(
            main_frame, fg_color=APP_CONFIG["THEME_COLORS"]["card_bg"], corner_radius=10
        )
        action_frame.grid(row=4, column=0, columnspan=3, padx=10, pady=5, sticky="ew")
        action_frame.grid_columnconfigure(0, weight=1)

        self.image_convert_btn = ctk.CTkButton(
            action_frame,
            text="CONVERT",
            command=lambda: self._start_conversion("Image"),
            height=50,
            corner_radius=8,
            font=ctk.CTkFont(size=18, weight="bold"),
            fg_color=APP_CONFIG["THEME_COLORS"]["btn_green"],
            hover_color=APP_CONFIG["THEME_COLORS"]["btn_green_hover"],
            text_color="white",
        )
        self.image_convert_btn.grid(row=0, column=0, padx=15, pady=(10, 5), sticky="ew")

        self.image_progress_bar = ctk.CTkProgressBar(
            action_frame, orientation="horizontal", height=15, corner_radius=8
        )
        self.image_progress_bar.grid(
            row=1, column=0, padx=15, pady=(5, 10), sticky="ew"
        )
        self.image_progress_bar.set(0)

    # Custom Size
    def _handle_image_size_change(self, selected_value: str):
        # Prompts the user for custom WxH dimensions if "Custom (WxH)" is selected.
        self.custom_image_dims = None

        if selected_value == "CUSTOM (WXH)":
            dialog = CustomSizeDialog(self.winfo_toplevel())
            custom_dims = dialog.show()

            if custom_dims:
                W, H = custom_dims
                self.custom_image_dims = (W, H)
                self.common_widgets["Image"]["help_text_label"].configure(
                    text=f"Status: Custom size set to {W}x{H}. Ready."
                )
            else:
                self.image_size.set("ORIGINAL (COPY)")
                self.common_widgets["Image"]["help_text_label"].configure(
                    text="Status: Custom size selection failed or cancelled. Size reset to Original (Copy)."
                )

    # Audio Filters
    def _construct_audio_filters(self) -> str:
        # Builds the complex filter string for FFmpeg audio processing (dithering, limiter).
        filters = []
        is_filtering_active = self.audio_limiter.get() or self.audio_dithering.get()

        if is_filtering_active:
            filters.append("aformat=sample_fmts=fltp")

            if self.audio_limiter.get():
                filters.append(
                    "alimiter=limit=1.0:level=disabled:attack=5:release=50,volume=-1dB"
                )

            if self.audio_dithering.get():
                filters.append("aresample=osf=s16:dither_method=shibata")

        return ",".join(filters)

    # Validate Files
    def _validate_files(
        self, file_paths: List[str], tab_name: str
    ) -> Tuple[List[str], List[str]]:
        # Validates file extensions against allowed formats for the given tab.
        # Returns (valid_files, rejected_files)

        if tab_name == "Video":
            allowed_formats = VIDEO_INPUT_FORMATS
        elif tab_name == "Audio":
            allowed_formats = AUDIO_INPUT_FORMATS
        elif tab_name == "Image":
            allowed_formats = IMAGE_INPUT_FORMATS
        else:
            allowed_formats = (
                VIDEO_INPUT_FORMATS + AUDIO_INPUT_FORMATS + IMAGE_INPUT_FORMATS
            )

        # Convert to lowercase for case-insensitive comparison
        allowed_extensions = {ext.lower() for ext in allowed_formats}

        valid_files = []
        rejected_files = []

        for file_path in file_paths:
            file_ext = Path(file_path).suffix.lower().lstrip(".")
            if file_ext in allowed_extensions:
                valid_files.append(file_path)
            else:
                rejected_files.append(file_path)

        return valid_files, rejected_files

    # File Filters
    def _get_file_dialog_filters(self, mode: str) -> List[Tuple[str, str]]:
        # Builds the list of file type tuples for the file dialog based on the current tab (mode).
        # The format is [('Description', '*.ext1 *.ext2'), ...]
        if mode == "Video":
            format_list = VIDEO_INPUT_FORMATS
            description = "Video Files"
        elif mode == "Audio":
            format_list = AUDIO_INPUT_FORMATS
            description = "Audio Files"
        elif mode == "Image":
            format_list = IMAGE_INPUT_FORMATS
            description = "Image Files"
        else:
            # Fallback for unexpected mode, ensures *.* is present
            return [("All Files", "*.*")]

        filetypes = []

        # 1. "All Supported" Filter (Combined: e.g., "All Supported Video Files (*.mp4 *.mkv)")
        all_supported_extensions = "*." + " *.".join(
            [fmt.lower() for fmt in format_list]
        )
        filetypes.append(
            (
                f"All Supported {description} ({len(format_list)} types)",
                all_supported_extensions,
            )
        )

        # 2. Individual extensions (e.g., "MP4 Files (*.mp4)")
        for fmt in format_list:
            filetypes.append((f"{fmt} Files", f"*.{fmt.lower()}"))

        # 3. "All Files" (Fallback) - Ensures all files are visible if the user needs them
        filetypes.append(("All Files", "*.*"))

        return filetypes

    # Native File
    def _native_file_dialog(self, title, initial_dir, filetypes=None):
        """
        Opens a native OS file dialog using the system's native tools.
        Returns a list of selected file paths, or None if cancelled.
        Returns empty list only if dialog was shown but no files matched.
        """
        import subprocess as sp

        native_tool_used = False  # Track if we successfully launched a native tool

        if os.name == "nt":
            # Tk uses the native Windows open dialog. The old PowerShell
            # implementation built an invalid filter string ("*.mp4 *.mkv"
            # instead of "*.mp4;*.mkv") and could show an empty file list.
            selected = filedialog.askopenfilenames(
                parent=self.winfo_toplevel(),
                title=title,
                filetypes=filetypes if filetypes else [("All Files", "*.*")],
                initialdir=initial_dir,
            )
            return list(selected) if selected else None

        elif os.uname().sysname == "Darwin":
            # macOS: Use osascript with AppleScript
            try:
                # Build filter string for AppleScript
                filter_str = ""
                if filetypes:
                    extensions = []
                    for desc, patterns in filetypes:
                        for p in patterns.split():
                            ext = p.replace("*.", "")
                            if ext not in extensions:
                                extensions.append(ext)
                    if extensions:
                        ext_quoted = ','.join(f'"{ext}"' for ext in extensions)
                        filter_str = f"of type {{{ext_quoted}}}"

                script = f'''
                set theFiles to choose file with prompt "{title}" default location POSIX file "{initial_dir}" with multiple selections allowed {filter_str}
                set thePaths to {{}}
                repeat with f in theFiles
                    set end of thePaths to POSIX path of f
                end repeat
                return thePaths as string
                '''
                result = sp.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                native_tool_used = True
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip().split(", ")
                return None  # Dialog was cancelled
            except Exception:
                pass

        else:
            # Linux: Try zenity first, then kdialog, then qarma
            initial_dir_expanded = os.path.expanduser(initial_dir)

            # Build combined filter pattern from ALL filetypes for Linux dialogs
            combined_filter = ""
            if filetypes:
                extensions = set()
                for desc, patterns in filetypes:
                    for p in patterns.split():
                        ext = p.replace("*.", "").strip()
                        if ext and ext != "*":  # Skip empty or wildcard
                            extensions.add(ext)
                if extensions:
                    combined_filter = " ".join(f"*.{ext}" for ext in sorted(extensions))

            # Try zenity (GTK-based, works on GNOME, XFCE, etc.)
            try:
                cmd = ["zenity", "--file-selection", "--multiple", "--title", title]
                if combined_filter:
                    cmd.append(f"--file-filter={combined_filter}")
                if os.path.isdir(initial_dir_expanded):
                    cmd.append(f"--filename={initial_dir_expanded}/")

                result = sp.run(cmd, capture_output=True, text=True, timeout=300)
                native_tool_used = True
                if result.returncode == 0 and result.stdout.strip():
                    # Zenity returns paths separated by |
                    paths = result.stdout.strip().split("|")
                    return [p for p in paths if os.path.isfile(p)]
                return None  # Dialog was cancelled (returncode != 0)
            except (sp.TimeoutExpired, FileNotFoundError):
                pass

            # Try kdialog (KDE)
            try:
                cmd = [
                    "kdialog",
                    "--title",
                    title,
                    "--getopenfilename",
                    initial_dir_expanded,
                ]
                if combined_filter:
                    cmd.append(f"Supported files ({combined_filter})")
                else:
                    cmd.append("*")
                cmd.append("--multiple")
                result = sp.run(cmd, capture_output=True, text=True, timeout=300)
                native_tool_used = True
                if result.returncode == 0 and result.stdout.strip():
                    # Kdialog returns paths separated by newlines
                    paths = result.stdout.strip().split("\n")
                    return [p for p in paths if os.path.isfile(p)]
                return None  # Dialog was cancelled
            except (sp.TimeoutExpired, FileNotFoundError):
                pass

            # Try qarma (GTK zenity alternative)
            try:
                cmd = ["qarma", "--file-selection", "--multiple", "--title", title]
                if combined_filter:
                    cmd.append(f"--file-filter={combined_filter}")
                if os.path.isdir(initial_dir_expanded):
                    cmd.append(f"--filename={initial_dir_expanded}/")
                result = sp.run(cmd, capture_output=True, text=True, timeout=300)
                native_tool_used = True
                if result.returncode == 0 and result.stdout.strip():
                    paths = result.stdout.strip().split("|")
                    return [p for p in paths if os.path.isfile(p)]
                return None  # Dialog was cancelled
            except (sp.TimeoutExpired, FileNotFoundError):
                pass

        # Only fall back to tkinter's built-in dialog if NO native tool was available/launched
        if not native_tool_used:
            return list(
                filedialog.askopenfilenames(
                    parent=self.winfo_toplevel(),
                    title=title,
                    filetypes=filetypes if filetypes else [("All Files", "*.*")],
                    initialdir=initial_dir,
                )
            )

        # If a native tool was used but cancelled, return None
        return None

    # Select Files
    def _select_input_file(self):
        # Opens native OS file dialog to select one or more files, filtered by the active tab's format.
        current_tab = self.current_tab_name

        filetypes = self._get_file_dialog_filters(current_tab)

        # Determine title based on tab
        if current_tab == "Video":
            title = "Select Video Files to Convert"
        elif current_tab == "Audio":
            title = "Select Audio Files to Convert"
        elif current_tab == "Image":
            title = "Select Image Files to Convert"
        else:
            title = "Select Files to Convert"

        file_paths = self._native_file_dialog(
            title=title,
            initial_dir=self.last_input_dir,
            filetypes=filetypes,
        )

        if file_paths:
            valid_files, rejected_files = self._validate_files(file_paths, current_tab)

            if valid_files:
                self.last_input_dir = str(Path(valid_files[0]).parent)
                status_msg = (
                    f"Status: {len(valid_files)} file(s) selected for {current_tab}."
                )
                if rejected_files:
                    rejected_names = [Path(f).name for f in rejected_files]
                    status_msg += (
                        f" Rejected {len(rejected_files)} invalid file(s): "
                        f"{', '.join(rejected_names[:3])}"
                        f"{'...' if len(rejected_names) > 3 else ''}."
                    )
                status_msg += " Ready."
                self._set_selected_files(current_tab, valid_files, status_msg)
            else:
                rejected_names = [Path(f).name for f in rejected_files]
                status_msg = (
                    f"Status: All {len(rejected_files)} selected file(s) are "
                    f"invalid for {current_tab} tab: "
                    f"{', '.join(rejected_names[:3])}"
                    f"{'...' if len(rejected_names) > 3 else ''}."
                )
                self._set_status(current_tab, status_msg, is_error=True)
        else:
            self._set_status(current_tab, "Status: File selection cancelled. Ready.")

    # Native Dir
    def _native_directory_dialog(self, title, initial_dir):
        """
        Opens a native OS directory/folder selection dialog using the system's native tools.
        Returns the selected directory path, or None if cancelled.
        """
        import subprocess as sp

        native_tool_used = False

        if os.name == "nt":
            # Use Tk's native Windows folder picker.
            selected = filedialog.askdirectory(
                parent=self.winfo_toplevel(),
                title=title,
                initialdir=initial_dir,
            )
            return selected or None

        elif os.uname().sysname == "Darwin":
            # macOS: Use osascript with AppleScript
            try:
                script = f'''
                set theFolder to choose folder with prompt "{title}" default location POSIX file "{initial_dir}"
                return POSIX path of theFolder
                '''
                result = sp.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                native_tool_used = True
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
                return None
            except Exception:
                pass

        else:
            # Linux: Use the same full file manager as file selection, but for directories
            initial_dir_expanded = os.path.expanduser(initial_dir)

            # Try zenity (GTK-based) - use file selection but only accept directories
            try:
                cmd = ["zenity", "--file-selection", "--directory", "--title", title]
                if os.path.isdir(initial_dir_expanded):
                    cmd.append(f"--filename={initial_dir_expanded}/")
                result = sp.run(cmd, capture_output=True, text=True, timeout=300)
                native_tool_used = True
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
                return None
            except (sp.TimeoutExpired, FileNotFoundError):
                pass

            # Try kdialog (KDE)
            try:
                cmd = [
                    "kdialog",
                    "--title",
                    title,
                    "--getexistingdirectory",
                    initial_dir_expanded,
                ]
                result = sp.run(cmd, capture_output=True, text=True, timeout=300)
                native_tool_used = True
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
                return None
            except (sp.TimeoutExpired, FileNotFoundError):
                pass

            # Try qarma
            try:
                cmd = ["qarma", "--file-selection", "--directory", "--title", title]
                if os.path.isdir(initial_dir_expanded):
                    cmd.append(f"--filename={initial_dir_expanded}/")
                result = sp.run(cmd, capture_output=True, text=True, timeout=300)
                native_tool_used = True
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
                return None
            except (sp.TimeoutExpired, FileNotFoundError):
                pass

            # Fallback: Use the same file dialog but filter for directories only
            # This gives the full file manager experience
            try:
                cmd = ["zenity", "--file-selection", "--title", title]
                if os.path.isdir(initial_dir_expanded):
                    cmd.append(f"--filename={initial_dir_expanded}/")
                result = sp.run(cmd, capture_output=True, text=True, timeout=300)
                native_tool_used = True
                if result.returncode == 0 and result.stdout.strip():
                    selected = result.stdout.strip()
                    # Only accept if it's a directory
                    if os.path.isdir(selected):
                        return selected
                    else:
                        # Show error and try again
                        sp.run(
                            [
                                "zenity",
                                "--error",
                                "--text",
                                "Please select a directory, not a file.",
                            ],
                            timeout=10,
                        )
                        return None
                return None
            except (sp.TimeoutExpired, FileNotFoundError):
                pass

        # Only fall back to tkinter if no native tool was available
        if not native_tool_used:
            return filedialog.askdirectory(
                parent=self.winfo_toplevel(),
                title=title,
                initialdir=initial_dir,
            )

        return None

    # Select Output
    def _select_output_directory(self):
        # Opens native OS directory dialog to choose the output folder.
        folder_path = self._native_directory_dialog(
            title="Select Output Folder",
            initial_dir=self.output_dir.get(),
        )
        if folder_path:
            self.output_dir.set(folder_path)
            self.common_widgets[self.current_tab_name]["help_text_label"].configure(
                text=f"Status: Output folder set to '{Path(folder_path).name}'. Ready."
            )
        else:
            self.common_widgets[self.current_tab_name]["help_text_label"].configure(
                text="Status: Output folder selection cancelled. Ready."
            )

    # Open Output
    def _open_output_directory(self):
        # Opens the selected output directory using the OS's default file explorer.
        path = self.output_dir.get()
        if not Path(path).exists():
            try:
                Path(path).mkdir(parents=True, exist_ok=True)
                self.common_widgets[self.current_tab_name]["help_text_label"].configure(
                    text=f"Status: Created missing directory: {path}"
                )
            except Exception as e:
                self.common_widgets[self.current_tab_name]["help_text_label"].configure(
                    text=f"Status: ERROR! Could not create directory: {e}"
                )
                return

        try:
            if os.name == "nt":
                os.startfile(path)
            elif os.uname().sysname == "Darwin":
                subprocess.Popen(["open", path])
            else:
                # Linux: Try xdg-open first, then fallbacks for common file managers
                try:
                    subprocess.Popen(["xdg-open", path])
                except FileNotFoundError:
                    # Fallback if xdg-open is missing (unlikely but possible)
                    file_managers = [
                        "nautilus",
                        "dolphin",
                        "nemo",
                        "thunar",
                        "pcmanfm",
                        "caja",
                    ]
                    found = False
                    for fm in file_managers:
                        try:
                            subprocess.Popen([fm, path])
                            found = True
                            break
                        except FileNotFoundError:
                            continue
                    if not found:
                        self.common_widgets[self.current_tab_name][
                            "help_text_label"
                        ].configure(
                            text=f"Status: ERROR! No file manager found to open {path}"
                        )
                        return
            self.common_widgets[self.current_tab_name]["help_text_label"].configure(
                text=f"Status: Opened output folder: {Path(path).name}"
            )
        except Exception as e:
            self.common_widgets[self.current_tab_name]["help_text_label"].configure(
                text=f"Status: ERROR! Could not open directory: {e}"
            )

    # Video Args
    def _build_video_args(self, cmd: List[str]) -> str:
        """Build video arguments and return the (lowercase) output extension."""
        output_format = self.video_format.get().lower()
        quality_mode = self.video_quality_mode.get()
        quality_value_setting = self.video_quality_value.get()

        # "Remove video" is really an audio extraction. Do it explicitly,
        # otherwise the old code still emitted a video codec and a .wav file
        # with a 32-bit float stream that many players dislike.
        if self.video_remove_video.get():
            cmd.extend(["-vn", "-c:a", "pcm_s16le", "-ar", "48000"])
            return "wav"

        no_audio = self.video_remove_audio.get() or output_format in VIDEO_NO_AUDIO
        if self.video_remove_audio.get() or output_format in VIDEO_NO_AUDIO:
            cmd.append("-an")

        video_codec = VIDEO_CODEC_MAP.get(
            output_format.upper(), "libx264"
        )

        video_filters = []
        if self.video_deinterlace.get():
            video_filters.append("yadif")

        # The bitrate presets are labelled 8K/4K/1080P/...; actually scale to
        # that resolution. Previously "KEEP ASPECT RATIO" did nothing.
        if quality_mode == "BITRATE (CBR/VBR AVG)":
            target = VIDEO_RESOLUTIONS.get(quality_value_setting)
            if target:
                width, height = target
                if self.video_keep_aspect_ratio.get():
                    video_filters.append(f"scale=-2:{height}")
                else:
                    video_filters.append(f"scale={width}:{height}")

        frame_rate = self.video_frame_rate.get()
        copy_mode = quality_mode == "ORIGINAL (COPY)"

        if copy_mode:
            if video_filters or frame_rate != "ORIGINAL (COPY)":
                raise ValueError(
                    "Original (Copy) mode cannot apply deinterlace, resizing, "
                    "or a frame rate. Choose CRF or Bitrate mode for those options."
                )
            cmd.extend(["-c:v", "copy"])
            if not no_audio:
                cmd.extend(["-c:a", "copy"])
        else:
            cmd.extend(["-c:v", video_codec])

            if quality_mode == "CRF (CONSTANT QUALITY)":
                crf_match = re.search(r"(\d+)", quality_value_setting)
                crf_value = crf_match.group(1) if crf_match else "23"
                if video_codec in CRF_ENCODERS:
                    cmd.extend(["-crf", crf_value])
                    if video_codec in PRESET_ENCODERS:
                        cmd.extend(["-preset", "medium"])
                    elif video_codec in ("libvpx", "libvpx-vp9"):
                        cmd.extend(
                            ["-b:v", "0", "-deadline", "good", "-cpu-used", "2"]
                        )
                    elif video_codec == "libaom-av1":
                        cmd.extend(["-b:v", "0"])
                else:
                    # -crf is not understood by MPEG-1/2, WMV, DV, Theora...
                    cmd.extend(["-q:v", "3"])

            elif quality_mode == "BITRATE (CBR/VBR AVG)":
                bitrate_match = re.search(r"\((\d+(?:\.\d+)?M)\)", quality_value_setting)
                if bitrate_match:
                    bitrate = bitrate_match.group(1)
                    cmd.extend(["-b:v", bitrate])
                    cmd.extend(["-maxrate", bitrate, "-bufsize", bitrate])

            if not no_audio:
                cmd.extend(
                    [
                        "-c:a",
                        VIDEO_AUDIO_CODEC.get(output_format, "aac"),
                    ]
                )

            # A widely compatible pixel format for common delivery containers.
            if output_format in {
                "mp4",
                "m4v",
                "mov",
                "mkv",
                "ts",
                "m2ts",
                "flv",
                "3gp",
                "3g2",
            }:
                cmd.extend(["-pix_fmt", "yuv420p"])

        if video_filters:
            cmd.extend(["-vf", ",".join(video_filters)])
        if frame_rate != "ORIGINAL (COPY)":
            cmd.extend(["-r", frame_rate])

        if output_format in {"mp4", "m4v", "mov"}:
            cmd.extend(["-movflags", "+faststart"])

        return output_format

    # Audio Args
    def _build_audio_args(self, cmd: List[str]) -> str:
        """Build audio arguments and return the (lowercase) output extension."""
        output_format = self.audio_format.get().lower()
        audio_filters = self._construct_audio_filters()

        codec_map = {
            "AAC": "aac",
            "M4A": "aac",
            "OGG": "libvorbis",
            "WMA": "wmav2",
            "OPUS": "libopus",
            "AC3": "ac3",
            "DTS": "dts",
            "EAC3": "eac3",
            "AMR": "libopencore_amrnb",
            "MP2": "mp2",
            "FLAC": "flac",
            "WAV": "pcm_s16le",
            "AIFF": "pcm_s16be",
            "ALAC": "alac",
            "WV": "wavpack",
            "AU": "pcm_s16be",
            "TTA": "tta",
        }

        if audio_filters:
            cmd.extend(["-af", audio_filters])

        if output_format == "mp3":
            cmd.extend(["-c:a", "libmp3lame"])
            if self.mp3_mode.get() == "VBR":
                vbr_setting = (
                    self.audio_quality.get().split(" ")[0].replace("V", "")
                )
                cmd.extend(["-q:a", vbr_setting])
            else:
                cmd.extend(["-b:a", self.audio_quality.get()])
        else:
            codec = codec_map.get(output_format.upper())
            if not codec:
                raise ValueError(f"Unsupported audio format: {output_format}")

            cmd.extend(["-c:a", codec])
            settings = AUDIO_SETTINGS.get(output_format.upper(), {})
            setting_type = settings.get("type")

            if setting_type == "bitrate":
                cmd.extend(["-b:a", self.audio_quality.get()])
            elif setting_type == "samplerate":
                samplerate = self.audio_quality.get().split(" ")[0]
                cmd.extend(["-ar", samplerate])
            # TTA ("compression") has no useful compression_level option in
            # FFmpeg; selecting the codec is enough.

            if output_format == "dts":
                cmd.extend(["-strict", "-2"])
            if output_format == "m4a":
                cmd.extend(["-movflags", "+faststart"])
            if output_format == "amr":
                # libopencore_amrnb only supports 8 kHz mono.
                cmd.extend(["-ar", "8000", "-ac", "1"])

        # ALAC is stored in an MP4/M4A container; ".alac" is not a muxer name.
        if output_format == "alac":
            return "m4a"
        return output_format

    # Image Args
    def _build_image_args(self, cmd: List[str]) -> str:
        """Build image arguments and return the (lowercase) output extension."""
        output_format = self.image_format.get().lower()
        image_filters = []

        size = self.image_size.get()
        if size == "CUSTOM (WXH)" and self.custom_image_dims:
            width, height = self.custom_image_dims
            if self.image_keep_aspect_ratio.get():
                image_filters.append(f"scale={width}:-2")
            else:
                image_filters.append(f"scale={width}:{height}")
        elif size != "ORIGINAL (COPY)":
            size_match = re.match(r"(\d+)X(\d+)", size)
            if size_match:
                width, height = size_match.groups()
                if self.image_keep_aspect_ratio.get():
                    image_filters.append(f"scale={width}:-2")
                else:
                    image_filters.append(f"scale={width}:{height}")

        visual_filter = self.image_visual_filter.get()
        if visual_filter == "GRAYSCALE (BLACK & WHITE)":
            image_filters.append("format=gray")
        elif visual_filter == "SHARPEN (BASIC)":
            image_filters.append("unsharp=5:5:0.8:5:5:0.0")
        elif visual_filter == "INVERT COLORS":
            image_filters.append("negate")

        if output_format == "ico":
            # The ICO encoder accepts at most 256x256.
            image_filters.append(
                "scale=256:256:force_original_aspect_ratio=decrease"
            )

        if image_filters:
            cmd.extend(["-vf", ",".join(image_filters)])

        # The old comparisons used lowercase strings while the UI returned
        # uppercase format names, so "COMPRESS" silently did nothing.
        if self.image_compress.get():
            if output_format in {"jpg", "jpeg", "webp", "avif"}:
                cmd.extend(["-q:v", "3"])
            elif output_format == "png":
                cmd.extend(["-compression_level", "9"])
            elif output_format in {"pcx", "sgi", "xwd", "sun"}:
                cmd.extend(["-compression_level", "9"])
            elif output_format == "qoi":
                cmd.extend(["-compression_level", "1"])

        if output_format in {"jpg", "jpeg"}:
            cmd.extend(["-pix_fmt", "yuvj420p"])
        if output_format == "gif":
            cmd.extend(["-loop", "0"])
        else:
            # Avoid the image2 muxer trying to write several frames of an
            # animated source to one filename.
            cmd.extend(["-frames:v", "1"])

        return output_format

    # Start Convert
    def _start_conversion(self, mode: str):
        """Validate the selection, build all FFmpeg commands, start one worker."""
        if self.conversion_running:
            self._set_status(
                mode,
                "Status: WARNING! A conversion is already in progress. Cancel it first.",
                is_error=True,
            )
            return

        if not ffmpeg_available():
            messagebox.showerror(
                "FFmpeg Not Found",
                "FFmpeg was not found. Install FFmpeg or use a build with a "
                "bundled FFmpeg, then restart FFConverter.",
            )
            self._set_status(
                mode,
                "Status: ERROR! FFmpeg is not installed or cannot be executed.",
                is_error=True,
            )
            return

        input_paths = {
            "Video": self.selected_video_files,
            "Audio": self.selected_audio_files,
            "Image": self.selected_image_files,
        }.get(mode)
        if not input_paths:
            self._set_status(
                mode, "Status: ERROR! Please select at least one input file.", True
            )
            return

        missing = [path for path in input_paths if not os.path.isfile(path)]
        if missing:
            self._set_status(
                mode,
                f"Status: ERROR! Input file not found: {Path(missing[0]).name}",
                is_error=True,
            )
            return

        output_dir = Path(self.output_dir.get()).expanduser()
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._set_status(
                mode, f"Status: ERROR! Cannot create output folder: {exc}", True
            )
            return

        jobs = []
        reserved = set()
        try:
            for input_path in input_paths:
                cmd = [FFMPEG_PATH, "-i", input_path, "-y"]

                strip_metadata = (
                    (mode == "Video" and self.video_strip_metadata.get())
                    or (mode == "Audio" and self.audio_strip_metadata.get())
                    or (mode == "Image" and self.image_strip_metadata.get())
                )
                if strip_metadata:
                    cmd.extend(["-map_metadata", "-1", "-map_chapters", "-1"])

                if mode == "Video":
                    output_format = self._build_video_args(cmd)
                elif mode == "Audio":
                    output_format = self._build_audio_args(cmd)
                elif mode == "Image":
                    output_format = self._build_image_args(cmd)
                else:
                    raise ValueError(f"Unknown conversion mode: {mode}")

                if not output_format:
                    raise ValueError("Please select a valid output format.")

                output_file = unique_output_path(
                    output_dir, Path(input_path).stem, output_format, reserved
                )
                cmd.append(str(output_file))

                # Ask FFmpeg for machine-readable progress on stdout. The old
                # code tried to parse the human stderr stats, which are written
                # with carriage returns and therefore never reached readline().
                cmd[-1:-1] = ["-progress", "pipe:1", "-nostats"]

                jobs.append(
                    {
                        "cmd": cmd,
                        "input_path": input_path,
                        "output_file": output_file,
                        "output_format": output_format,
                    }
                )
        except Exception as exc:
            self._set_status(
                mode, f"Status: ERROR! {exc}", is_error=True
            )
            return

        self.conversion_running = True
        self.cancel_requested = False
        self.conversion_mode = mode
        self.total_files_to_convert = len(jobs)
        self.converted_files_count = 0
        self._set_progress(mode, 0)
        self._set_convert_button(mode, True)
        self._set_status(
            mode,
            f"Status: Starting conversion of {len(jobs)} file(s)...",
        )

        self.conversion_thread = threading.Thread(
            target=self._conversion_worker,
            args=(mode, jobs),
            daemon=True,
        )
        self.conversion_thread.start()

    # Cancel
    def _cancel_conversion(self):
        if not self.conversion_running:
            return

        self.cancel_requested = True
        mode = self.conversion_mode
        self._set_status(mode, "Status: Cancelling conversion...", is_error=True)

        process = self.active_conversion_process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
            # SIGTERM is sometimes ignored while FFmpeg is writing a large
            # file; make sure the process really goes away.
            threading.Timer(3.0, self._force_kill, args=(process,)).start()

    def _force_kill(self, process):
        if process is not None and process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass

    def _conversion_worker(self, mode: str, jobs: List[dict]):
        total = len(jobs)
        completed = 0
        failures = []

        for index, job in enumerate(jobs):
            if self.cancel_requested:
                break

            input_name = Path(job["input_path"]).name
            duration = self._get_file_duration(job["input_path"])

            self._post(
                lambda i=index, n=input_name: self._set_status(
                    mode, f"Status: Converting {i + 1}/{total}: {n}"
                )
            )
            if duration is None:
                self._post(lambda: self._set_progress(mode, None))

            return_code, error_text = self._run_ffmpeg(
                job, index, total, duration, mode
            )

            if self.cancel_requested and return_code != 0:
                break

            if return_code == 0:
                completed += 1
                self._post(
                    lambda i=index: self._set_progress(
                        mode, (i + 1) / total if total else 1.0
                    )
                )
                self._post(
                    lambda c=completed, n=input_name: self._set_status(
                        mode, f"Status: Completed {c}/{total} files. Last: {n}"
                    )
                )
            else:
                # Do not leave a truncated output file behind.
                try:
                    job["output_file"].unlink(missing_ok=True)
                except OSError:
                    pass
                failures.append((job["input_path"], error_text))
                short_error = " ".join(error_text.split())[:180]
                self._post(
                    lambda n=input_name, e=short_error: self._set_status(
                        mode,
                        f"Status: FFmpeg ERROR on {n}: {e}",
                        is_error=True,
                    )
                )

        self._post(
            lambda: self._conversion_finished(mode, total, completed, failures)
        )

    def _conversion_finished(
        self, mode: str, total: int, completed: int, failures: List[Tuple[str, str]]
    ):
        self.conversion_running = False
        self.active_conversion_process = None
        self._set_convert_button(mode, False)

        if self.cancel_requested:
            self._set_progress(mode, 1.0 if completed else 0.0)
            self._set_status(
                mode,
                f"Status: Conversion cancelled. Completed {completed}/{total} file(s).",
                is_error=True,
            )
        elif failures:
            self._set_progress(mode, completed / total if total else 0.0)
            first_error = " ".join(failures[0][1].split())[:220]
            self._set_status(
                mode,
                f"Status: Finished with errors: {completed}/{total} converted. "
                f"{first_error}",
                is_error=True,
            )
        else:
            self._set_progress(mode, 1.0)
            self._set_status(
                mode,
                f"Status: Done. {completed}/{total} file(s) converted to "
                f"'{Path(self.output_dir.get()).name}'.",
            )

        self.cancel_requested = False
        self.conversion_mode = None

    # Duration
    def _get_file_duration(self, input_path: str) -> Optional[float]:
        """Use ffprobe to get media duration in seconds (None for images)."""
        try:
            result = subprocess.run(
                [
                    FFPROBE_PATH,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    input_path,
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
        return None

    # Run FFmpeg
    def _run_ffmpeg(
        self,
        job: dict,
        file_index: int,
        total_files: int,
        total_duration: Optional[float],
        mode: str,
    ) -> Tuple[int, str]:
        """Run one conversion, reading progress until the process exits."""
        try:
            process = subprocess.Popen(
                job["cmd"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            return 1, str(exc)

        self.active_conversion_process = process
        tail = deque(maxlen=50)
        last_ui_update = 0.0

        try:
            if process.stdout is not None:
                for line in process.stdout:
                    tail.append(line.rstrip())
                    info = parse_ffmpeg_progress(line)
                    if (
                        "seconds" in info
                        and total_duration
                        and total_duration > 0
                    ):
                        file_fraction = min(
                            info["seconds"] / total_duration, 1.0
                        )
                        overall = (file_index + file_fraction) / max(
                            total_files, 1
                        )
                        now = time.monotonic()
                        if now - last_ui_update >= 0.15:
                            last_ui_update = now
                            self._post(
                                lambda value=overall: self._set_progress(
                                    mode, value
                                )
                            )
                    if self.cancel_requested and process.poll() is None:
                        try:
                            process.terminate()
                        except OSError:
                            pass

            return_code = process.wait()
        except Exception as exc:
            tail.append(str(exc))
            try:
                process.kill()
            except OSError:
                pass
            try:
                return_code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                return_code = -1
        finally:
            self.active_conversion_process = None

        return return_code, "\n".join(tail)

    # Bind Help
    def _bind_help_text_for_tab(self, tab_name: str):
        # Binds help text for a specific tab (called on tab initialization)
        # This replaces the old _bind_help_text() which bound all tabs at once

        def set_help_text(tab_key, key):
            self.common_widgets[tab_key]["help_text_label"].configure(
                text=HELP_MESSAGES.get(key, HELP_MESSAGES["default"])
            )

        def bind_widget(tab_key, widget, key):
            try:
                widget.unbind("<Enter>")
                widget.unbind("<Leave>")
            except Exception:
                pass
            widget.bind("<Enter>", lambda _: set_help_text(tab_key, key))
            widget.bind("<Leave>", lambda _: set_help_text(tab_key, "default"))

        if tab_name not in self.common_widgets:
            return

        tab_widgets = self.common_widgets[tab_name]

        # Common widgets for all tabs
        bind_widget(tab_name, tab_widgets["browse_button"], "browse_files")
        bind_widget(tab_name, tab_widgets["input_label"], "browse_files")
        bind_widget(tab_name, tab_widgets["output_entry"], "output_folder")
        bind_widget(tab_name, tab_widgets["change_btn"], "change_folder")
        bind_widget(tab_name, tab_widgets["open_btn"], "open_folder")

        if tab_name == "Video":
            # Convert button
            bind_widget(tab_name, self.video_convert_btn, "convert_btn")
            
            # Format dropdowns
            if "format_label" in tab_widgets:
                bind_widget(tab_name, tab_widgets["format_label"], "video_format")
                bind_widget(tab_name, tab_widgets["format_menu"], "video_format")
            
            # Quality mode
            if "quality_mode_label" in tab_widgets:
                bind_widget(tab_name, tab_widgets["quality_mode_label"], "video_quality_mode")
                bind_widget(tab_name, tab_widgets["quality_mode_menu"], "video_quality_mode")
            
            # Quality value (bitrate/CRF)
            if "quality_value_label" in tab_widgets:
                bind_widget(tab_name, tab_widgets["quality_value_label"], "video_quality_value")
            if hasattr(self, 'video_quality_value_menu'):
                bind_widget(tab_name, self.video_quality_value_menu, "video_quality_value")
            
            # Framerate
            if "framerate_label" in tab_widgets:
                bind_widget(tab_name, tab_widgets["framerate_label"], "video_framerate")
                bind_widget(tab_name, tab_widgets["framerate_menu"], "video_framerate")
            
            # Toggle buttons
            if "ar_cb" in tab_widgets:
                bind_widget(tab_name, tab_widgets["ar_cb"], "keep_aspect_ratio")
            if "di_cb" in tab_widgets:
                bind_widget(tab_name, tab_widgets["di_cb"], "apply_deinterlace")
            if "sm_cb" in tab_widgets:
                bind_widget(tab_name, tab_widgets["sm_cb"], "strip_metadata")
            if "ra_cb" in tab_widgets:
                bind_widget(tab_name, tab_widgets["ra_cb"], "remove_audio")
            if "rv_cb" in tab_widgets:
                bind_widget(tab_name, tab_widgets["rv_cb"], "remove_video")
                
        elif tab_name == "Audio":
            # Convert button
            bind_widget(tab_name, self.audio_convert_btn, "convert_btn")
            
            # Format
            if "format_label" in tab_widgets:
                bind_widget(tab_name, tab_widgets["format_label"], "audio_format")
                bind_widget(tab_name, tab_widgets["format_menu"], "audio_format")
            
            # MP3 Mode (for MP3 format)
            if hasattr(self, 'mp3_mode_label'):
                bind_widget(tab_name, self.mp3_mode_label, "mp3_mode")
            if hasattr(self, 'mp3_mode_menu'):
                bind_widget(tab_name, self.mp3_mode_menu, "mp3_mode")
            
            # Audio Quality
            if hasattr(self, 'audio_quality_label'):
                bind_widget(tab_name, self.audio_quality_label, "audio_quality")
            if hasattr(self, 'audio_quality_menu'):
                bind_widget(tab_name, self.audio_quality_menu, "audio_quality")
            
            # Toggles
            if "dithering_cb" in tab_widgets:
                bind_widget(tab_name, tab_widgets["dithering_cb"], "apply_dithering")
            if "limiter_cb" in tab_widgets:
                bind_widget(tab_name, tab_widgets["limiter_cb"], "apply_limiter")
            if "sm_cb" in tab_widgets:
                bind_widget(tab_name, tab_widgets["sm_cb"], "strip_metadata")
                
        elif tab_name == "Image":
            # Convert button
            bind_widget(tab_name, self.image_convert_btn, "convert_btn")
            
            # Format
            if "image_format_label" in tab_widgets:
                bind_widget(tab_name, tab_widgets["image_format_label"], "image_format")
                bind_widget(tab_name, tab_widgets["image_format_menu"], "image_format")
            
            # Size
            if "image_size_label" in tab_widgets:
                bind_widget(tab_name, tab_widgets["image_size_label"], "image_size")
                bind_widget(tab_name, tab_widgets["image_size_menu"], "image_size")
            
            # Visual filter
            if "vf_label" in tab_widgets:
                bind_widget(tab_name, tab_widgets["vf_label"], "visual_filter")
                bind_widget(tab_name, tab_widgets["vf_menu"], "visual_filter")
            
            # Toggles
            if "ar_cb" in tab_widgets:
                bind_widget(tab_name, tab_widgets["ar_cb"], "image_keep_aspect_ratio")
            if "compress_cb" in tab_widgets:
                bind_widget(tab_name, tab_widgets["compress_cb"], "image_compress")
            if "sm_cb" in tab_widgets:
                bind_widget(tab_name, tab_widgets["sm_cb"], "image_strip_metadata")

        # Add dynamic traces for Video quality mode
        if tab_name == "Video":
            self.video_quality_mode.trace_add(
                "write", lambda *args: self.after(10, self._bind_video_dynamic_options)
            )
            self.after(10, self._bind_video_dynamic_options)
        elif tab_name == "Audio":
            self.audio_format.trace_add(
                "write", lambda *args: self.after(10, self._bind_audio_dynamic_options)
            )
            self.mp3_mode.trace_add(
                "write", lambda *args: self.after(10, self._bind_audio_dynamic_options)
            )
            self.after(10, self._bind_audio_dynamic_options)

    # DnD
    def _setup_drag_and_drop(self):
        """
        Registers drop targets on the entire tab area for all relevant tabs.
        This provides a larger, more intuitive drag-and-drop experience.
        """
        if not TKINTERDND_AVAILABLE:
            return
        if not getattr(self, "dnd_ready", False):
            return

        for tab_name in ["Audio", "Video", "Image"]:
            # Use the main tab frame as the drop target
            tab_frame = getattr(self, f"{tab_name.lower()}_tab")

            if tab_frame:
                # 1. Register the widget (the entire tab) as a drop target for files
                tab_frame.drop_target_register(DND_FILES)

                # 2. Bind the '<<Drop>>' event to the handler method
                tab_frame.dnd_bind(
                    "<<Drop>>",
                    lambda e, tab=tab_name, widget=tab_frame: [
                        self._handle_drop(e, tab),
                        self._reset_drop_visual(widget),
                    ],
                )

                # 3. Add visual feedback for drag over/enter/leave
                tab_frame.dnd_bind(
                    "<<DragEnter>>",
                    lambda e, widget=tab_frame: self._set_drop_visual(widget),
                )
                tab_frame.dnd_bind(
                    "<<DragLeave>>",
                    lambda e, widget=tab_frame: self._reset_drop_visual(widget),
                )

    def _set_drop_visual(self, widget):
        """Sets a border to visually indicate the widget is a valid drop target."""
        widget.configure(
            border_color=APP_CONFIG["THEME_COLORS"]["green"], border_width=3
        )

    def _reset_drop_visual(self, widget):
        """Removes the border after a drop or drag leave event."""
        # Note: You might need to check your CTkFrame/CTkTabview defaults.
        # Assuming default border_width is 0 or 1. If it's 0, use 0.
        widget.configure(border_color="transparent", border_width=0)

    def _handle_drop(self, event, tab_name: str):
        """Handle a drop, updating both the visible label and the real file list."""
        try:
            # TkinterDnD gives us a Tcl list; splitlist handles spaces and
            # braces correctly (the old regex did not handle every case).
            file_paths = list(self.tk.splitlist(event.data))
        except Exception:
            file_paths = [event.data]

        file_paths = [
            str(Path(path).expanduser())
            for path in file_paths
            if str(path).strip() and Path(path).expanduser().is_file()
        ]

        if not file_paths:
            self._set_status(
                tab_name, "Status: No files were dropped.", is_error=True
            )
            return

        valid_files, rejected_files = self._validate_files(file_paths, tab_name)
        if not valid_files:
            self._set_status(
                tab_name,
                f"Status: Dropped file(s) rejected. Only "
                f"{self.tab_variables[tab_name]['extensions']} are supported here.",
                is_error=True,
            )
            return

        status_msg = (
            f"Status: {len(valid_files)} file(s) dropped successfully. "
            "Ready for conversion."
        )
        if rejected_files:
            status_msg += (
                f" {len(rejected_files)} file(s) rejected due to format."
            )

        self.last_input_dir = str(Path(valid_files[0]).parent)
        # This is the important part the old code missed: update the stored
        # path list used by the conversion worker, not only the label.
        self._set_selected_files(tab_name, valid_files, status_msg)

    def _update_status(self, tab_name: str, message: str, is_error: bool = False):
        self._set_status(tab_name, message, is_error)

    # Bind Video
    def _bind_video_dynamic_options(self, *args):
        # Binds help text to the changing Video Quality Value label and menu.

        def unbind_widget(widget):
            try:
                widget.unbind("<Enter>")
                widget.unbind("<Leave>")
            except Exception:
                pass

        def bind_widget(widget, key):
            widget.bind("<Enter>", lambda _: self._update_help_text("Video", key))
            widget.bind("<Leave>", lambda _: self._update_help_text("Video", "default"))

        unbind_widget(self.quality_value_label)
        unbind_widget(self.video_quality_value_menu)

        selected_mode = self.video_quality_mode.get()
        if selected_mode == "BITRATE (CBR/VBR AVG)":
            bind_widget(self.quality_value_label, "video_bitrate")
            bind_widget(self.video_quality_value_menu, "video_bitrate")
        elif selected_mode == "CRF (CONSTANT QUALITY)":
            bind_widget(self.quality_value_label, "video_crf_value")
            bind_widget(self.video_quality_value_menu, "video_crf_value")

    # Bind Audio
    def _bind_audio_dynamic_options(self, *args):
        # Binds help text to the Audio Quality/MP3 Mode options, which change dynamically.

        def unbind_widget(widget):
            try:
                widget.unbind("<Enter>")
                widget.unbind("<Leave>")
            except Exception:
                pass

        def bind_widget(widget, key):
            widget.bind("<Enter>", lambda _: self._update_help_text("Audio", key))
            widget.bind("<Leave>", lambda _: self._update_help_text("Audio", "default"))

        unbind_widget(self.mp3_mode_label)
        unbind_widget(self.mp3_mode_menu)
        unbind_widget(self.audio_quality_label)
        unbind_widget(self.audio_quality_menu)

        if self.audio_format.get() == "MP3":
            bind_widget(self.mp3_mode_label, "mp3_mode")
            bind_widget(self.mp3_mode_menu, "mp3_mode")
            bind_widget(self.audio_quality_label, "audio_quality")
            bind_widget(self.audio_quality_menu, "audio_quality")
        else:
            bind_widget(self.audio_quality_label, "audio_quality")
            bind_widget(self.audio_quality_menu, "audio_quality")

    # Theme
    def _setup_theme_toggler(self):
        # Creates the Light/Dark mode toggler buttons centered in the top header
        self.theme_toggler_frame = ctk.CTkFrame(
            self.top_header, fg_color=APP_CONFIG["THEME_COLORS"]["transparent"]
        )
        # Center the frame within the top header
        self.theme_toggler_frame.grid(row=0, column=0, padx=0, pady=0)

        self.btn_light = ctk.CTkButton(
            self.theme_toggler_frame,
            text="LIGHT",
            command=lambda: self._set_theme("Light"),
            width=80,
            height=28,
            fg_color=APP_CONFIG["THEME_COLORS"]["transparent"],
            text_color="white",
            hover_color=APP_CONFIG["THEME_COLORS"]["btn_inactive"],
            font=ctk.CTkFont(size=12, weight="bold"),
        )

        self.btn_dark = ctk.CTkButton(
            self.theme_toggler_frame,
            text="DARK",
            command=lambda: self._set_theme("Dark"),
            width=80,
            height=28,
            fg_color=APP_CONFIG["THEME_COLORS"][
                "transparent"
            ],  # Initially transparent or active depending on default
            text_color=APP_CONFIG["THEME_COLORS"]["text_primary"],
            hover_color=APP_CONFIG["THEME_COLORS"]["btn_inactive"],
            font=ctk.CTkFont(size=12, weight="bold"),
        )

        self.btn_dark.grid(row=0, column=0, padx=2, pady=(10, 0))
        self.btn_light.grid(row=0, column=1, padx=2, pady=(10, 0))

        # Set default state (Dark)
        self._set_theme("Dark", initial=True)

        # Bind help text to theme buttons
        self.btn_light.bind(
            "<Enter>",
            lambda _: self._update_help_text(self.current_tab_name, "light_theme"),
        )
        self.btn_light.bind(
            "<Leave>",
            lambda _: self._update_help_text(self.current_tab_name, "default"),
        )
        self.btn_dark.bind(
            "<Enter>",
            lambda _: self._update_help_text(self.current_tab_name, "dark_theme"),
        )
        self.btn_dark.bind(
            "<Leave>",
            lambda _: self._update_help_text(self.current_tab_name, "default"),
        )

    def _set_theme(self, mode: str, initial: bool = False):
        # Switches the interface theme and updates toggler button states
        ctk.set_appearance_mode(mode)

        if mode == "Light":
            self.btn_light.configure(
                text_color=APP_CONFIG["THEME_COLORS"]["text_primary"],
                fg_color=APP_CONFIG["THEME_COLORS"]["btn_inactive"],
            )
            self.btn_dark.configure(
                text_color=APP_CONFIG["THEME_COLORS"]["text_secondary"],
                fg_color=APP_CONFIG["THEME_COLORS"]["transparent"],
            )
        else:
            self.btn_light.configure(
                text_color=APP_CONFIG["THEME_COLORS"]["text_secondary"],
                fg_color=APP_CONFIG["THEME_COLORS"]["transparent"],
            )
            self.btn_dark.configure(
                text_color=APP_CONFIG["THEME_COLORS"]["text_primary"],
                fg_color=APP_CONFIG["THEME_COLORS"]["btn_inactive"],
            )

    # Exit
    def _on_closing(self):
        """Stop background work and close the application."""
        if self.conversion_running:
            if not messagebox.askyesno(
                "Quit FFConverter",
                "A conversion is still running. Stop it and quit?",
            ):
                return
            self.cancel_requested = True
            self._force_kill(self.active_conversion_process)

        self._stop_tray()
        self.destroy()

    def _setup_tray_icon(self):
        """Start an optional tray icon in a separate process.

        pystray uses its own GLib/GTK main loop, which conflicts with Tk on
        some desktops. Keeping it in a child process avoids those crashes.
        """
        if not PYSTRAY_AVAILABLE:
            return

        icon_path = None
        for path in (
            CURRENT_DIR / "ffconverter.png",
            CURRENT_DIR / "resources" / "images" / "LOGO_256.png",
            Path("/usr/share/ffconverter/ffconverter.png"),
            Path("/usr/share/icons/hicolor/256x256/apps/ffconverter.png"),
        ):
            if path.is_file():
                icon_path = str(path)
                break

        if not icon_path:
            return

        try:
            tray_dir = Path(tempfile.mkdtemp(prefix="ffconverter-tray-"))
            script_path = tray_dir / "tray.py"
            script_path.write_text(
                """#!/usr/bin/env python3
import os
from PIL import Image
import pystray

signal_dir = os.environ["FFCONVERTER_TRAY_DIR"]
icon_path = os.environ["FFCONVERTER_ICON"]

def signal(name):
    try:
        with open(os.path.join(signal_dir, name), "w", encoding="utf-8") as fh:
            fh.write("1")
    except OSError:
        pass

def show_window(icon, item):
    signal("show")

def quit_app(icon, item):
    signal("quit")
    icon.stop()

image = Image.open(icon_path).resize((64, 64), Image.LANCZOS)
menu = pystray.Menu(
    pystray.MenuItem("Show", show_window, default=True),
    pystray.MenuItem("Quit", quit_app),
)
pystray.Icon("FFConverter", image, "FFConverter", menu).run()
""",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["FFCONVERTER_TRAY_DIR"] = str(tray_dir)
            env["FFCONVERTER_ICON"] = icon_path

            self.tray_dir = tray_dir
            self.tray_stop = threading.Event()
            self.tray_process = subprocess.Popen(
                [sys.executable, str(script_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                start_new_session=True,
            )
            self.tray_monitor_thread = threading.Thread(
                target=self._monitor_tray, daemon=True
            )
            self.tray_monitor_thread.start()
        except Exception as exc:
            print(f"Warning: system tray unavailable: {exc}")
            self._stop_tray()

    def _monitor_tray(self):
        """Watch the tray child process for Show/Quit requests."""
        assert self.tray_dir is not None
        while not self.tray_stop.wait(0.4):
            if (self.tray_dir / "show").exists():
                try:
                    (self.tray_dir / "show").unlink()
                except OSError:
                    pass
                self._post(self._show_from_tray)
            if (self.tray_dir / "quit").exists():
                try:
                    (self.tray_dir / "quit").unlink()
                except OSError:
                    pass
                self._post(self._on_closing)
                return

    def _show_from_tray(self):
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _stop_tray(self):
        if getattr(self, "tray_stop", None) is not None:
            self.tray_stop.set()
        process = getattr(self, "tray_process", None)
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    process.kill()
                except OSError:
                    pass
        self.tray_process = None

        tray_dir = getattr(self, "tray_dir", None)
        if tray_dir is not None:
            shutil.rmtree(tray_dir, ignore_errors=True)
            self.tray_dir = None


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="FFConverter",
        description="Simple video, audio, and image converter for Linux.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"FFConverter {__version__}",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="files to open (also used by the desktop launcher)",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)

    if args.smoke_test:
        # Used by CI: exercise Tk, CustomTkinter, tkdnd, bundled resources and
        # the FFmpeg binary without entering the event loop.
        app = FFConverterApp()
        app.update_idletasks()
        ok = (
            ffmpeg_available()
            and (CURRENT_DIR / "resources" / "icon.ico").is_file()
            and bool(getattr(app, "dnd_ready", False))
        )
        app.destroy()
        return 0 if ok else 1

    app = FFConverterApp()
    app.protocol("WM_DELETE_WINDOW", app._on_closing)
    if args.files:
        # Wait until the first idle cycle so lazy-loaded tabs exist.
        app.after(100, lambda: app.load_files_from_args(args.files))
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
