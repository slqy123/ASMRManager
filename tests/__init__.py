import atexit
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

if "asmrmanager" in sys.modules:
    raise RuntimeError(
        "Test isolation must be initialized before importing asmrmanager. "
        "Run: python -m unittest discover -s tests -t ."
    )

_environment = TemporaryDirectory(prefix="asmrmanager-tests-")
atexit.register(_environment.cleanup)
for name in ("CONFIG", "DATA", "CACHE", "STATE"):
    os.environ[f"XDG_{name}_HOME"] = str(
        Path(_environment.name) / name.lower()
    )
os.environ["ASMR_TEST"] = "1"
os.environ.pop("ASMR_DEBUG", None)
config_dir = Path(os.environ["XDG_CONFIG_HOME"]) / "asmrmanager"
config_dir.mkdir(parents=True)
config_text = (
    Path(__file__).resolve().parents[1]
    / "asmrmanager/filemanager/resources/config.example.toml"
).read_text(encoding="utf-8")
for name, original in (
    ("download", "~/Downloads/asmr"),
    ("storage", "~/Music/asmr"),
    ("view", "~/Desktop/asmr"),
):
    path = Path(_environment.name) / name
    path.mkdir()
    config_text = config_text.replace(original, path.as_posix())
(config_dir / "config.toml").write_text(config_text, encoding="utf-8")
