import atexit
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

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
shutil.copyfile(
    Path(__file__).resolve().parents[1]
    / "asmrmanager/filemanager/resources/config.example.toml",
    config_dir / "config.toml",
)
