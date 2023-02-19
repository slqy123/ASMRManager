from logger import logger

from pathlib import Path
import os
import shutil


class FileManager:
    def __init__(self, storage_path: str, download_path, view_path):
        self.storage_path = Path(storage_path)
        self.download_path = Path(download_path)
        self.view_path = Path(view_path)

        self.storage_path_exists = True if os.path.exists(self.storage_path) else False
        self.download_path_exists = True if os.path.exists(self.download_path) else False
        self.view_path_exists = True if os.path.exists(self.view_path) else False

        self.view_link_type = 'hard' if (self.storage_path.anchor == self.view_path.anchor) else 'sym'

    def could_store(self):
        return self.storage_path_exists and self.download_path_exists

    def store(self, download_item: str, exists_ok: bool = False):
        assert self.could_store()
        if not os.path.exists(self.download_path / download_item):
            logger.warning(f'item {download_item} does not exist')
            return

        if os.path.exists(self.storage_path / download_item):
            if not exists_ok:
                logger.error('the item to store already exists!')
                exit(-1)

            logger.info(f'remove item {download_item} in storage')
            shutil.rmtree(self.storage_path / download_item)

        shutil.move(self.download_path / download_item, self.storage_path / download_item)

    def store_all(self, exists_ok: bool = False):
        for file in os.listdir(self.download_path):
            self.store(file, exists_ok=exists_ok)


    def could_view(self):
        return self.view_path_exists and self.storage_path_exists

    def view(self, storage_item: str):
        assert self.could_view()
        if not os.path.exists(self.storage_path / storage_item):
            logger.error(f'Failed to view {storage_item}, item not exists!')
            exit(-1)

        if os.path.exists(self.view_path / storage_item):
            logger.warning('')

