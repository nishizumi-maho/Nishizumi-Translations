"""PyInstaller build for the experimental meeting transcriber.

    python build_reuniao.py --mode onedir --clean

Produces ``dist/NishizumiReunioes/``. The Windows installer in
``installer/reuniao.iss`` packages that folder.

Kept separate from ``build_executable.py`` on purpose: the two apps ship
different entry points, different names and different optional dependencies,
and neither build should be able to break the other.
"""

from __future__ import annotations

import argparse
import importlib.util
import platform
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from reuniao import __version__  # noqa: E402
from reuniao import branding  # noqa: E402

BUNDLE_NAME = "NishizumiReunioes"

#: Qt modules the app never imports. PySide6_Addons drags in a lot of these and
#: each one costs tens of megabytes in the bundle.
EXCLUDED_QT_MODULES = (
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",
    "PySide6.QtBluetooth",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNfc",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickControls2",
    "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtSpatialAudio",
    "PySide6.QtSql",
    "PySide6.QtStateMachine",
    "PySide6.QtTest",
    "PySide6.QtTextToSpeech",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets",
)

#: This app never romanizes, translates or touches video, so the subtitle app's
#: heavier dependencies stay out of the bundle.
EXCLUDED_MODULES = ("tkinter", "matplotlib", "PIL", "pytest", "setuptools", "pykakasi")

OPTIONAL_COLLECTS = (
    ("faster_whisper", ("--collect-submodules=faster_whisper", "--collect-data=faster_whisper")),
    ("ctranslate2", ("--collect-binaries=ctranslate2", "--collect-submodules=ctranslate2")),
    ("tokenizers", ("--collect-binaries=tokenizers",)),
    ("onnxruntime", ("--collect-binaries=onnxruntime", "--collect-data=onnxruntime")),
    ("sherpa_onnx", ("--collect-binaries=sherpa_onnx", "--collect-submodules=sherpa_onnx")),
    ("av", ("--collect-binaries=av",)),
    ("huggingface_hub", ("--collect-submodules=huggingface_hub",)),
)


def _version_tuple() -> tuple[int, int, int, int]:
    parts = [int(chunk) for chunk in __version__.split(".")[:3] if chunk.isdigit()]
    while len(parts) < 3:
        parts.append(0)
    return (parts[0], parts[1], parts[2], 0)


def write_version_file(build_dir: Path) -> Path:
    """Write the VERSIONINFO resource so the .exe has proper file properties."""

    build_dir.mkdir(parents=True, exist_ok=True)
    target = build_dir / "version_info_reuniao.txt"
    numbers = _version_tuple()
    target.write_text(
        f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={numbers},
    prodvers={numbers},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', {branding.PUBLISHER!r}),
         StringStruct('FileDescription', {branding.APP_NAME!r}),
         StringStruct('FileVersion', {__version__!r}),
         StringStruct('InternalName', {BUNDLE_NAME!r}),
         StringStruct('LegalCopyright', 'MIT licensed'),
         StringStruct('OriginalFilename', {BUNDLE_NAME + '.exe'!r}),
         StringStruct('ProductName', {branding.APP_NAME!r}),
         StringStruct('ProductVersion', {__version__!r})])
    ]),
    VarFileInfo([VarStruct('Translation', [1046, 1200])])
  ]
)
""",
        encoding="utf-8",
    )
    return target


def build_command(args: argparse.Namespace, build_dir: Path) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        f"--name={BUNDLE_NAME}",
        f"--{args.mode}",
        "--noconfirm",
        f"--paths={SRC_DIR}",
        "--console" if args.console else "--windowed",
    ]

    icon = PROJECT_ROOT / "assets" / "icon.ico"
    if platform.system() == "Darwin":
        icon = PROJECT_ROOT / "assets" / "icon.icns"
    if icon.exists():
        command.append(f"--icon={icon}")

    if platform.system() == "Windows":
        command.append(f"--version-file={write_version_file(build_dir)}")

    command.extend(
        [
            "--collect-submodules=reuniao",
            # The download machinery, the component store and the widget
            # toolkit are shared with the subtitle app.
            "--collect-submodules=jp2subs.runtime",
            "--collect-submodules=jp2subs.gui",
            "--hidden-import=reuniao.gui.main",
            # The Review page plays the recording alongside the transcript.
            # The module alone is not enough: Qt loads its media backend as a
            # plugin at runtime, so that has to travel with it.
            "--hidden-import=PySide6.QtMultimedia",
            "--collect-binaries=PySide6",
            "--hidden-import=jp2subs.config",
            "--hidden-import=rich",
            "--hidden-import=typer",
        ]
    )
    command.extend(f"--exclude-module={name}" for name in EXCLUDED_QT_MODULES)
    command.extend(f"--exclude-module={name}" for name in EXCLUDED_MODULES)

    for package, options in OPTIONAL_COLLECTS:
        if importlib.util.find_spec(package):
            command.extend(options)
            print(f"  bundling optional dependency: {package}")
        else:
            print(f"  skipping absent optional dependency: {package}")

    if platform.system() != "Windows":
        command.append("--strip")

    command.append(str(SRC_DIR / "reuniao" / "gui" / "__main__.py"))
    return command


def main() -> int:
    parser = argparse.ArgumentParser(description=f"Build the {branding.APP_NAME} executable")
    parser.add_argument("--mode", choices=["onefile", "onedir"], default="onedir")
    parser.add_argument("--console", action="store_true", help="Keep a console window (useful for debugging)")
    parser.add_argument("--clean", action="store_true", help="Remove build/ and dist/ first")
    args = parser.parse_args()

    dist_dir = PROJECT_ROOT / "dist"
    build_dir = PROJECT_ROOT / "build"

    if args.clean:
        for directory in (dist_dir, build_dir):
            if directory.exists():
                shutil.rmtree(directory)
                print(f"Removed {directory}")

    command = build_command(args, build_dir)
    print(f"\n{branding.APP_NAME} {__version__}")
    print(f"Platform: {platform.system()} {platform.machine()}")
    print(f"Python:   {sys.version.split()[0]}")
    print(f"Command:  {' '.join(command)}\n")

    result = subprocess.run(command, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print("ERROR: PyInstaller failed.")
        return result.returncode

    output = dist_dir / BUNDLE_NAME
    print("\n" + "=" * 62)
    print("Build complete.")
    print(f"Output: {output}")
    if output.is_dir():
        total = sum(item.stat().st_size for item in output.rglob("*") if item.is_file())
        print(f"Size:   {total / (1024 ** 2):.0f} MB")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
