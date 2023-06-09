from pathlib import Path
import zipfile

from .utils import folder_chooser
from logger import logger

def zip_chosen_folder(src: Path, dst: Path):
    assert src.is_dir() and dst.exists() == False
    folder = folder_chooser(src)[0]
    logger.info('start zipping...')
    files = [f for f in folder.iterdir() if not f.is_dir()]
    with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file in files:
            zf.write(file, arcname=file.name)




