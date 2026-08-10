"""Generate assets/icon.ico from the logo the app draws at runtime.

Run this only when the logo changes:

    python assets/generate_icon.py

The generated .ico is committed so the packaging step does not need Qt.
"""
from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SIZES = (16, 24, 32, 48, 64, 128, 256)


def _png_bytes(size: int) -> bytes:
    from PySide6 import QtCore, QtWidgets

    from jp2subs.gui import icons

    _app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    pixmap = icons.app_logo(size)
    # app_logo scales for the screen's DPR; force exact pixel dimensions here.
    pixmap.setDevicePixelRatio(1.0)
    image = pixmap.toImage().scaled(
        size,
        size,
        QtCore.Qt.IgnoreAspectRatio,
        QtCore.Qt.SmoothTransformation,
    )

    buffer = QtCore.QBuffer()
    buffer.open(QtCore.QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def build_ico(destination: Path) -> Path:
    """Pack PNG frames into an .ico (PNG-in-ICO, supported since Vista)."""

    frames = [(size, _png_bytes(size)) for size in SIZES]

    header = struct.pack("<HHH", 0, 1, len(frames))
    entries = b""
    payload = b""
    offset = len(header) + 16 * len(frames)

    for size, data in frames:
        dimension = 0 if size >= 256 else size
        entries += struct.pack(
            "<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(data), offset
        )
        payload += data
        offset += len(data)

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(header + entries + payload)
    return destination


if __name__ == "__main__":
    target = build_ico(ROOT / "assets" / "icon.ico")
    print(f"Wrote {target} ({target.stat().st_size:,} bytes)")
