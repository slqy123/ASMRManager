from logger import logger
from .exceptions import SrcNotExistsException, DstItemAlreadyExistsException
from file_manager.file_zipper import zip_chosen_folder

from pathlib import Path
import os
import shutil
from typing import Literal


class FileManager:
    def __init__(self, storage_path: str, download_path, view_path):
        self.storage_path = Path(storage_path)
        self.download_path = Path(download_path)
        self.view_path = Path(view_path)

        self.storage_path_exists = True if os.path.exists(self.storage_path) else False
        self.download_path_exists = True if os.path.exists(self.download_path) else False
        self.view_path_exists = True if os.path.exists(self.view_path) else False

    def could_store(self):
        return self.storage_path_exists and self.download_path_exists

    def store(self, download_item: str, exists_ok: bool = False):
        assert self.could_store()
        if not os.path.exists(self.download_path / download_item):
            logger.warning(f'item {download_item} does not exists')
            return

        if os.path.exists(self.storage_path / download_item):
            if not exists_ok:
                logger.error(f'the item {download_item} to store already exists!')
                raise DstItemAlreadyExistsException

            logger.info(f'remove item {download_item} in storage')
            shutil.rmtree(self.storage_path / download_item)

        logger.info(f'move {self.download_path / download_item} to {self.storage_path / download_item}')
        shutil.move(self.download_path / download_item, self.storage_path / download_item)  # type: ignore

    def store_all(self, exists_ok: bool = False):
        for file in os.listdir(self.download_path):
            self.store(file, exists_ok=exists_ok)

    def could_view(self):
        """either storage_path or download_path exists ok, view path must exists"""
        return self.view_path_exists and (self.storage_path_exists or self.download_path_exists)

    def view(self, storage_item: str, replace=True):
        assert self.could_view()
        if os.path.exists(self.storage_path / storage_item):
            src = self.storage_path / storage_item
        elif os.path.exists(self.download_path / storage_item):
            src = self.download_path / storage_item
        else:
            logger.error(f'Failed to view {storage_item}, item not exists!')
            raise SrcNotExistsException

        if os.path.exists(self.view_path / storage_item):
            logger.warning(f'{storage_item} already exists!')
            if not replace:
                raise DstItemAlreadyExistsException

        os.symlink(src, self.view_path / storage_item)

    def remove_view(self, name):
        assert self.could_view()
        path = self.view_path / name
        if not path.exists():
            logger.error(f'file f{name} not exists')
            return
        assert path.is_dir() and path.is_symlink()
        os.remove(path)

    def list_(self, path: Literal['download', 'view', 'storage']):
        if path == 'download':
            p = self.download_path
        elif path == 'view':
            p = self.view_path
        elif path == 'storage':
            p = self.storage_path
        else:
            logger.error('Invalid path')
            return []

        return filter(lambda x: x.startswith('RJ'), os.listdir(p))
    
    def zip_file(self, name: str, stored: bool|None=None):
        assert self.could_view()
        if stored is None:
            src1 = self.storage_path / name
            src2 = self.download_path / name
            if src1.exists():
                src = src1
            elif src2.exists():
                src = src2
            else:
                logger.error(f"file {name} not exists, locate file failed")
                raise SrcNotExistsException
        else:
            path = self.storage_path if stored else self.download_path
            src = path / name
            assert src.exists()

        dst = self.view_path / name
        dst = dst.with_suffix('.zip')
        if dst.exists():
            logger.error(f'file {dst} already exists please remove first')
            raise DstItemAlreadyExistsException
        zip_chosen_folder(src, dst)


if __name__ == '__main__':
    from config import config

    fm = FileManager(config.storage_path, config.download_path, config.view_path)
    fm.store('RJ097514')
