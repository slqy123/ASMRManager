import zipfile
from pathlib import Path

from asmrmanager.logger import logger


def zip_chosen_folder(
    folder: Path, dst: Path, ignore: set[str] | None = None
):
    assert folder.is_dir() and dst.exists() is False
    logger.info("start zipping...")
    files = [
        f
        for f in folder.iterdir()
        if not f.is_dir() and f.name not in (ignore or ())
    ]
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in files:
            zf.write(file, arcname=file.name)
