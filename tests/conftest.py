import sys
from pathlib import Path
import importlib.util
import types

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Provide a light-weight fallback for the `rich` package when it is not installed
# in the execution environment.
if importlib.util.find_spec("rich") is None:
    rich_module = types.ModuleType("rich")
    console_module = types.ModuleType("rich.console")

    class Console:
        def log(self, *args, **kwargs):  # pragma: no cover - simple passthrough
            print(*args)

        def print(self, *args, **kwargs):  # pragma: no cover - simple passthrough
            print(*args)

    console_module.Console = Console
    rich_module.console = console_module
    sys.modules["rich"] = rich_module
    sys.modules["rich.console"] = console_module
