# PyInstaller build script for jp2subs GUI
# Usage: python build_executable.py [--onefile|--onedir] [--windowed|--console]

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build jp2subs GUI executable")
    parser.add_argument(
        "--mode",
        choices=["onefile", "onedir"],
        default="onedir",
        help="Build mode: single executable or directory",
    )
    parser.add_argument(
        "--windowed",
        action="store_true",
        default=True,
        help="Windowed mode (no console window) [default]",
    )
    parser.add_argument(
        "--console",
        action="store_true",
        help="Console mode (show console window)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean build directories before building",
    )
    args = parser.parse_args()

    # Determine paths
    project_root = Path(__file__).parent.resolve()
    src_dir = project_root / "src"
    dist_dir = project_root / "dist"
    build_dir = project_root / "build"

    # Clean if requested
    if args.clean:
        print("Cleaning build directories...")
        for d in [dist_dir, build_dir]:
            if d.exists():
                shutil.rmtree(d)
                print(f"  Removed {d}")

    # Build PyInstaller command
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name=jp2subs-gui",
        f"--{args.mode}",
        "--noconfirm",
    ]

    # Windowed vs console
    if args.console:
        cmd.append("--console")
    else:
        cmd.append("--windowed")

    # Icon (if available)
    icon_path = project_root / "assets" / "icon.ico"
    if icon_path.exists():
        cmd.append(f"--icon={icon_path}")
    else:
        # Use a simple icon for macOS
        icon_path_mac = project_root / "assets" / "icon.icns"
        if icon_path_mac.exists():
            cmd.append(f"--icon={icon_path_mac}")

    # Add data files and hidden imports
    cmd.extend(
        [
            f"--add-data={src_dir / 'jp2subs'}:jp2subs",
            "--hidden-import=PySide6",
            "--hidden-import=PySide6.QtCore",
            "--hidden-import=PySide6.QtGui",
            "--hidden-import=PySide6.QtWidgets",
            "--collect-all=PySide6",
        ]
    )

    # Optimize
    cmd.extend(
        [
            "--strip" if platform.system() != "Windows" else "",
        ]
    )

    # Remove empty string from strip option on Windows
    cmd = [c for c in cmd if c]

    # Entry point script
    entry_script = src_dir / "jp2subs" / "gui" / "__main__.py"

    # If __main__.py doesn't exist or is minimal, create a proper entry script
    if not entry_script.exists() or entry_script.stat().st_size < 200:
        entry_script = project_root / "build_entry.py"
        entry_script.write_text(
            '''#!/usr/bin/env python3
"""Entry point for PyInstaller build."""
import sys
from pathlib import Path

# Add src to path
src = Path(__file__).parent / "src"
if src.exists():
    sys.path.insert(0, str(src))

from jp2subs.gui.main import launch

if __name__ == "__main__":
    launch()
'''
        )
        cmd.append(str(entry_script))
    else:
        cmd.append(str(entry_script))

    print(f"Building with command: {' '.join(cmd)}")
    print(f"Platform: {platform.system()} {platform.machine()}")
    print(f"Python: {sys.version}")
    print()

    # Run PyInstaller
    result = subprocess.run(cmd, cwd=project_root)

    if result.returncode != 0:
        print("ERROR: Build failed!")
        return result.returncode

    print()
    print("=" * 60)
    print("Build completed successfully!")
    print(f"Output location: {dist_dir}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
